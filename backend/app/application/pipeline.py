"""Use case central : ProcessInvoicePipelineUseCase.

Orchestre le pipeline IA complet (Phase 6) en tâche de fond :
prétraitement → OCR (fallback) → langue → extraction → cohérence →
classification → moteur de règles + suggestion → score de confiance →
écriture PROPOSED. Chaque étape persiste son résultat ET le statut :
en cas de panne, on sait exactement où la facture s'est arrêtée."""
import logging
from datetime import date
from decimal import Decimal

from app.core.config import get_settings
from app.core.currency import convert_amounts
from app.domain.entities import (
    DocumentType, ExtractedEntity, Invoice, InvoiceStatus, PipelineStep, Supplier,
)
from app.domain.ports import (
    AccountRepository, CompanyRepository, EntityExtractor, EntryRepository,
    ExchangeRateRepository, InvoiceRepository, OcrResult, RuleRepository, SupplierRepository,
)
from app.domain.rules import VATCalculator
from app.infrastructure.ml.classifiers import ConstrainedAccountSuggester, load_active_classifier
from app.infrastructure.nlp.extractor import detect_document_type, detect_language
from app.infrastructure.ocr.engines import OcrOrchestrator
from app.infrastructure.ocr.pdf_text import read_pdf_text_layer
from app.infrastructure.ocr.preprocessing import pdf_to_images, preprocess_image
from app.infrastructure.rules.rule_engine import RuleEngine, RuleEngineError

logger = logging.getLogger(__name__)


class ProcessInvoicePipelineUseCase:
    def __init__(self, invoices: InvoiceRepository, entries: EntryRepository,
                 accounts: AccountRepository, suppliers: SupplierRepository,
                 rules: RuleRepository, extractor: EntityExtractor,
                 ocr: OcrOrchestrator | None = None, classifier=None,
                 account_code_by_id: dict[int, str] | None = None,
                 companies: CompanyRepository | None = None,
                 rates: ExchangeRateRepository | None = None):
        self.companies = companies
        self.rates = rates
        self.invoices = invoices
        self.entries = entries
        self.accounts = accounts
        self.suppliers = suppliers
        self.rules = rules
        self.extractor = extractor
        self.ocr = ocr or OcrOrchestrator()
        self.classifier = classifier
        self.settings = get_settings()
        self.account_code_by_id = account_code_by_id or {
            a.id: a.code for a in accounts.list_active()}

    # ------------------------------------------------------------ Pipeline
    def execute(self, invoice_id: int) -> None:
        """Aucune exception ne doit s'échapper de cette méthode : c'est une
        tâche de fond, il n'y a personne pour la rattraper. Même un incident
        survenant dès la lecture initiale (ex. panne BDD passagère) doit être
        journalisé plutôt que de faire planter le worker."""
        try:
            invoice = self.invoices.get_by_id(invoice_id)
            if invoice is None:
                logger.error("Facture %s introuvable", invoice_id)
                return
            self._run(invoice)
        except Exception as exc:
            logger.exception("Pipeline en échec pour la facture %s", invoice_id)
            try:
                invoice = self.invoices.get_by_id(invoice_id)
                if invoice is not None:
                    invoice.status = InvoiceStatus.ERROR
                    invoice.error_message = str(exc)[:500]
                    self.invoices.update(invoice)
            except Exception:
                logger.exception(
                    "Impossible de marquer la facture %s en erreur "
                    "(panne persistante) — intervention manuelle nécessaire",
                    invoice_id)

    def _run(self, invoice: Invoice) -> None:
        # Relance : repart d'un état propre (résultats et propositions précédents).
        self.invoices.reset_pipeline_results(invoice.id)
        self.entries.delete_unvalidated_by_invoice(invoice.id)

        # --- 1. Prétraitement ---------------------------------------------
        invoice.status = InvoiceStatus.PREPROCESSING
        invoice.current_step = PipelineStep.PREPROCESSING
        self.invoices.update(invoice)
        # PDF numérique : le texte est déjà dans le fichier, avec ses
        # coordonnées. On le lit directement (toutes les pages, sans
        # rasterisation ni OCR) ; scans et photos suivent le chemin OCR.
        text_layer = (read_pdf_text_layer(invoice.storage_path)
                      if invoice.mime_type == "application/pdf" else None)
        prepared = None
        if text_layer is None:
            image_paths = ([invoice.storage_path] if invoice.mime_type != "application/pdf"
                           else pdf_to_images(invoice.storage_path))
            prepared, _meta = preprocess_image(image_paths[0])  # page 1 (v1 mono-page)

        # --- 2. OCR avec fallback ------------------------------------------
        invoice.current_step = PipelineStep.OCR
        self.invoices.update(invoice)
        ocr_result = (text_layer if text_layer is not None
                      else self.ocr.run(prepared, self.settings.ocr_language_list))
        if ocr_result is None:
            invoice.status = InvoiceStatus.ERROR
            invoice.error_message = ("Facture illisible : confiance OCR insuffisante "
                                     "sur les deux moteurs. Saisie manuelle recommandée.")
            self.invoices.update(invoice)
            return
        self.invoices.save_ocr_result(
            invoice.id, ocr_result.engine, ocr_result.raw_text,
            ocr_result.mean_confidence,
            [{"text": b.text, "bbox": b.bbox, "confidence": b.confidence}
             for b in ocr_result.blocks],
            ocr_result.duration_ms)
        invoice.status = InvoiceStatus.OCR_DONE
        self.invoices.update(invoice)

        # --- 3. Langue + type de document -----------------------------------
        invoice.current_step = PipelineStep.LANGUAGE_DETECTION
        self.invoices.update(invoice)
        invoice.language = detect_language(ocr_result.raw_text) or "fr"
        # Une facture d'avoir (note de crédit fournisseur) génère une écriture
        # au sens inversé par rapport à un achat normal (cf. étape 7).
        invoice.document_type = detect_document_type(ocr_result.raw_text)

        # --- 4. Extraction d'entités ----------------------------------------
        invoice.current_step = PipelineStep.ENTITY_EXTRACTION
        self.invoices.update(invoice)
        entities = self.extractor.extract(ocr_result, invoice.language)
        self.invoices.save_entities(invoice.id, entities)
        self._apply_entities(invoice, entities)

        # --- 5. Cohérence arithmétique + auto-résolution ---------------------
        invoice.current_step = PipelineStep.COHERENCE_CHECK
        self.invoices.update(invoice)
        # Une mention de TVA repérée sur la facture (même sans montant
        # exploitable) signale une extraction incomplète ; son absence totale
        # signale plutôt une facture exonérée — on ne fabrique alors aucune
        # taxe (cf. VATCalculator.resolve_missing).
        vat_evidence_found = any(e.entity_type == "TOTAL_VAT" for e in entities)
        vat_calc = VATCalculator(Decimal(str(self.settings.default_vat_rate)))
        resolved = vat_calc.resolve_missing(invoice.total_ht, invoice.total_vat,
                                            invoice.total_ttc,
                                            vat_evidence_found=vat_evidence_found)
        if resolved:
            invoice.total_ht, invoice.total_vat, invoice.total_ttc = resolved
        invoice.arithmetic_ok = invoice.check_arithmetic()
        invoice.status = InvoiceStatus.ANALYZED
        self.invoices.update(invoice)

        if invoice.total_ttc is None:
            invoice.status = InvoiceStatus.ERROR
            invoice.error_message = ("Aucun montant exploitable extrait : "
                                     "vérification manuelle nécessaire.")
            self.invoices.update(invoice)
            return

        # --- 5 bis. Devise : conversion vers la devise de l'entreprise ---------
        base_currency = self._base_currency(invoice.company_id)
        rate = None
        if invoice.currency == base_currency:
            invoice.exchange_rate = None
        else:
            rate = invoice.exchange_rate or self._lookup_rate(invoice, base_currency)
            if rate is None:
                invoice.status = InvoiceStatus.ERROR
                invoice.error_message = (
                    f"Taux de change {invoice.currency} → {base_currency} manquant : "
                    "renseignez-le sur la facture ou dans les paramètres de l'entreprise, "
                    "puis relancez le traitement.")
                self.invoices.update(invoice)
                return
            invoice.exchange_rate = rate
        self.invoices.update(invoice)

        # --- 6. Classification ------------------------------------------------
        invoice.current_step = PipelineStep.CLASSIFICATION
        self.invoices.update(invoice)
        supplier = (self.suppliers.get_by_id(invoice.supplier_id)
                    if invoice.supplier_id else None)
        classifier = self.classifier or load_active_classifier()
        classification = classifier.classify(
            ocr_result.raw_text, supplier.name if supplier else None,
            float(invoice.total_ttc))
        self.invoices.save_classification(
            invoice.id, classification.operation_type.value,
            classification.probability, classification.probabilities,
            classification.model_version)

        # --- 7. Moteur de règles + suggestion des comptes -----------------------
        invoice.current_step = PipelineStep.RULE_ENGINE
        self.invoices.update(invoice)
        rule = self.rules.get_active_for_operation(classification.operation_type.value)
        if rule is None:
            rule = self.rules.get_active_for_operation("ACHAT_SERVICES")  # défaut prudent
        if rule is None:
            invoice.status = InvoiceStatus.ERROR
            invoice.error_message = "Aucune règle comptable active applicable."
            self.invoices.update(invoice)
            return

        ht, vat, ttc = invoice.total_ht, invoice.total_vat, invoice.total_ttc
        if rate is not None:
            ht, vat, ttc = convert_amounts(ht, vat, ttc, rate)
        entry_amounts = {"HT": ht, "VAT": vat, "TTC": ttc}

        engine = RuleEngine(self.accounts,
                            ConstrainedAccountSuggester(self.account_code_by_id))
        document_label = "Avoir" if invoice.document_type == DocumentType.AVOIR else "Facture"
        label = f"{document_label} {invoice.invoice_number or invoice.id} — " \
                f"{supplier.name if supplier else 'fournisseur inconnu'}"
        try:
            entry = engine.generate_entry(
                rule=rule, invoice_id=invoice.id, company_id=invoice.company_id,
                entry_date=invoice.invoice_date or date.today(), label=label[:255],
                amounts=entry_amounts,
                invoice_text=ocr_result.raw_text, supplier=supplier,
                reverse_sides=invoice.document_type == DocumentType.AVOIR)
        except RuleEngineError as exc:
            invoice.status = InvoiceStatus.ERROR
            invoice.error_message = f"Génération d'écriture impossible : {exc}"
            self.invoices.update(invoice)
            return

        # --- 8. Score de confiance global ---------------------------------------
        invoice.current_step = PipelineStep.CONFIDENCE_SCORING
        self.invoices.update(invoice)
        entry.currency = base_currency
        if rate is not None:
            entry.original_currency = invoice.currency
            entry.original_amount = invoice.total_ttc
            entry.exchange_rate = rate
        entry.confidence_score = self._confidence_score(
            ocr_result, entities, classification.probability, entry,
            supplier_known=supplier is not None,
            arithmetic_ok=bool(invoice.arithmetic_ok))
        self.entries.create(entry)
        invoice.status = InvoiceStatus.ENTRIES_PROPOSED
        invoice.current_step = PipelineStep.DONE
        self.invoices.update(invoice)
        logger.info("Facture %s : écriture proposée (confiance %.2f)",
                    invoice.id, entry.confidence_score)

    # ------------------------------------------------------------- Helpers
    def _base_currency(self, company_id: int) -> str:
        company = self.companies.get_by_id(company_id) if self.companies else None
        return company.base_currency if company else self.settings.default_currency

    def _lookup_rate(self, invoice: Invoice, base_currency: str) -> Decimal | None:
        """Taux paramétré par l'entreprise à la date de la facture (à défaut, aujourd'hui)."""
        if self.rates is None:
            return None
        found = self.rates.find_applicable(
            invoice.company_id, invoice.currency, invoice.invoice_date or date.today())
        return found.rate if found else None

    def _apply_entities(self, invoice: Invoice, entities: list[ExtractedEntity]) -> None:
        """Copie les entités critiques sur la facture (dénormalisation de
        lecture assumée — extracted_entities reste la source de vérité)."""
        by_type = {e.entity_type: e for e in entities}

        def dec(entity_type: str) -> Decimal | None:
            entity = by_type.get(entity_type)
            if entity and entity.normalized_value:
                try:
                    return Decimal(entity.normalized_value)
                except Exception:
                    return None
            return None

        invoice.total_ht = dec("TOTAL_HT")
        invoice.total_vat = dec("TOTAL_VAT")
        invoice.total_ttc = dec("TOTAL_TTC")
        if "INVOICE_NUMBER" in by_type:
            invoice.invoice_number = by_type["INVOICE_NUMBER"].normalized_value
        if "CURRENCY" in by_type and by_type["CURRENCY"].normalized_value:
            invoice.currency = by_type["CURRENCY"].normalized_value
        if "INVOICE_DATE" in by_type and by_type["INVOICE_DATE"].normalized_value:
            try:
                invoice.invoice_date = date.fromisoformat(
                    by_type["INVOICE_DATE"].normalized_value)
            except ValueError:
                pass
        # Rapprochement fournisseur (flou) puis création si inconnu
        if "SUPPLIER_NAME" in by_type:
            name = by_type["SUPPLIER_NAME"].raw_value.strip()
            matched = self.suppliers.find_by_fuzzy_name(name, invoice.company_id)
            if matched is None:
                nif = by_type.get("NIF")
                stat = by_type.get("STAT")
                matched = self.suppliers.get_or_create(Supplier(
                    id=None, company_id=invoice.company_id, name=name,
                    normalized_name=name.upper(),
                    nif=nif.normalized_value if nif else None,
                    stat=stat.normalized_value if stat else None))
            invoice.supplier_id = matched.id

    def _confidence_score(self, ocr: OcrResult, entities: list[ExtractedEntity],
                          classification_proba: float, entry,
                          supplier_known: bool, arithmetic_ok: bool) -> float:
        """Formule validée en Phase 6 :
        w1·C_ocr + w2·C_extraction + w3·C_classif + w4·C_comptes − pénalités."""
        s = self.settings
        critical = [e for e in entities if e.entity_type in
                    ("SUPPLIER_NAME", "INVOICE_DATE", "TOTAL_HT", "TOTAL_VAT", "TOTAL_TTC")]
        # champs manquants comptés à zéro (5 champs critiques attendus)
        c_extraction = sum(e.confidence for e in critical) / 5
        ml_lines = [l.account_confidence for l in entry.lines
                    if l.account_confidence is not None]
        c_accounts = sum(ml_lines) / len(ml_lines) if ml_lines else 0.5

        score = (s.confidence_w_ocr * ocr.mean_confidence
                 + s.confidence_w_extraction * c_extraction
                 + s.confidence_w_classification * classification_proba
                 + s.confidence_w_accounts * c_accounts)
        if not arithmetic_ok:
            score -= 0.15
        if not supplier_known:
            score -= 0.10
        if ocr.engine == "TESSERACT":
            score -= 0.10
        return round(max(0.0, min(1.0, score)), 4)
