"""Implémentations MySQL des repositories (adaptateurs de persistance).
Seule cette couche connaît SQLAlchemy ; elle convertit systématiquement
les modèles ORM en entités du domaine et inversement."""
from datetime import datetime
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.domain import entities as dom
from app.domain import ports
from app.infrastructure.db import models as m


# ------------------------------------------------------------ Mappers

def _company_to_domain(row: m.CompanyModel) -> dom.Company:
    return dom.Company(id=row.id, name=row.name, nif=row.nif, stat=row.stat,
                       address=row.address, is_active=row.is_active, logo_path=row.logo_path,
                       base_currency=row.base_currency or "MGA", chart_id=row.chart_id)


def _user_to_domain(row: m.UserModel) -> dom.User:
    return dom.User(id=row.id, email=row.email, full_name=row.full_name,
                    role=dom.Role(row.role), company_id=row.company_id,
                    is_active=row.is_active, password_hash=row.password_hash,
                    avatar_path=row.avatar_path, theme=row.theme or "auto",
                    accent=row.accent or "blue")


def _invoice_to_domain(row: m.InvoiceModel) -> dom.Invoice:
    return dom.Invoice(
        id=row.id, original_filename=row.original_filename, storage_path=row.storage_path,
        mime_type=row.mime_type, file_size=row.file_size, uploaded_by=row.uploaded_by,
        company_id=row.company_id,
        status=dom.InvoiceStatus(row.status),
        current_step=dom.PipelineStep(row.current_step) if row.current_step else None,
        document_type=dom.DocumentType(row.document_type), supplier_id=row.supplier_id,
        language=row.language, invoice_number=row.invoice_number,
        invoice_date=row.invoice_date,
        total_ht=Decimal(str(row.total_ht)) if row.total_ht is not None else None,
        total_vat=Decimal(str(row.total_vat)) if row.total_vat is not None else None,
        total_ttc=Decimal(str(row.total_ttc)) if row.total_ttc is not None else None,
        currency=row.currency,
        exchange_rate=Decimal(str(row.exchange_rate)) if row.exchange_rate is not None else None,
        arithmetic_ok=row.arithmetic_ok,
        error_message=row.error_message)


def _entry_to_domain(row: m.JournalEntryModel) -> dom.JournalEntry:
    return dom.JournalEntry(
        id=row.id, invoice_id=row.invoice_id, company_id=row.company_id,
        entry_date=row.entry_date,
        label=row.label, status=dom.EntryStatus(row.status),
        confidence_score=float(row.confidence_score) if row.confidence_score is not None else None,
        rule_code=row.rule.code if row.rule else None,
        validated_by=row.validated_by, validated_at=row.validated_at,
        currency=row.currency or "MGA", original_currency=row.original_currency,
        original_amount=(Decimal(str(row.original_amount))
                         if row.original_amount is not None else None),
        exchange_rate=(Decimal(str(row.exchange_rate))
                       if row.exchange_rate is not None else None),
        lines=[dom.EntryLine(
            id=line.id, account_id=line.account_id,
            account_code=line.account.code if line.account else "",
            label=line.label, debit=Decimal(str(line.debit)),
            credit=Decimal(str(line.credit)),
            account_confidence=float(line.account_confidence) if line.account_confidence is not None else None,
            suggested_by_ml=line.suggested_by_ml, line_order=line.line_order,
        ) for line in row.lines])


# ------------------------------------------------------- Repositories

class MySQLCompanyRepository(ports.CompanyRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, company: dom.Company) -> dom.Company:
        row = m.CompanyModel(name=company.name, nif=company.nif, stat=company.stat,
                             address=company.address, is_active=company.is_active)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _company_to_domain(row)

    def get_by_id(self, company_id: int) -> dom.Company | None:
        row = self.db.get(m.CompanyModel, company_id)
        return _company_to_domain(row) if row else None

    def list_all(self) -> list[dom.Company]:
        rows = self.db.scalars(select(m.CompanyModel).order_by(m.CompanyModel.name)).all()
        return [_company_to_domain(r) for r in rows]

    def set_active(self, company_id: int, is_active: bool) -> dom.Company | None:
        row = self.db.get(m.CompanyModel, company_id)
        if row is None:
            return None
        row.is_active = is_active
        self.db.commit()
        self.db.refresh(row)
        return _company_to_domain(row)

    def set_base_currency(self, company_id: int, currency: str) -> dom.Company | None:
        row = self.db.get(m.CompanyModel, company_id)
        if row is None:
            return None
        row.base_currency = currency
        self.db.commit()
        self.db.refresh(row)
        return _company_to_domain(row)

    def set_chart(self, company_id: int, chart_id: int | None) -> dom.Company | None:
        row = self.db.get(m.CompanyModel, company_id)
        if row is None:
            return None
        row.chart_id = chart_id
        self.db.commit()
        self.db.refresh(row)
        return _company_to_domain(row)

    def update_branding(self, company_id: int, **fields) -> dom.Company | None:
        unknown = set(fields) - {"name", "logo_path"}
        if unknown:
            raise ValueError(f"Champs non modifiables : {sorted(unknown)}")
        row = self.db.get(m.CompanyModel, company_id)
        if row is None:
            return None
        for name, value in fields.items():
            setattr(row, name, value)
        self.db.commit()
        self.db.refresh(row)
        return _company_to_domain(row)


class MySQLChartRepository(ports.ChartRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, row: m.ChartModel, counts: dict[int, int]) -> dom.Chart:
        return dom.Chart(id=row.id, code=row.code, name=row.name, country=row.country,
                         version=row.version, description=row.description,
                         accounts_count=counts.get(row.id, 0))

    def _counts(self) -> dict[int, int]:
        rows = self.db.execute(
            select(m.AccountModel.chart_id, func.count(m.AccountModel.id))
            .where(m.AccountModel.is_active.is_(True)).group_by(m.AccountModel.chart_id)).all()
        return {chart_id: count for chart_id, count in rows if chart_id is not None}

    def list_active(self) -> list[dom.Chart]:
        counts = self._counts()
        rows = self.db.scalars(select(m.ChartModel).where(m.ChartModel.is_active.is_(True))
                               .order_by(m.ChartModel.country, m.ChartModel.name)).all()
        return [self._to_domain(r, counts) for r in rows]

    def get_by_id(self, chart_id: int) -> dom.Chart | None:
        row = self.db.get(m.ChartModel, chart_id)
        return self._to_domain(row, self._counts()) if row else None


class MySQLExchangeRateRepository(ports.ExchangeRateRepository):
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_domain(row: m.ExchangeRateModel) -> dom.ExchangeRate:
        return dom.ExchangeRate(id=row.id, company_id=row.company_id, currency=row.currency,
                                rate=Decimal(str(row.rate)), effective_date=row.effective_date)

    def list_for_company(self, company_id: int) -> list[dom.ExchangeRate]:
        rows = self.db.scalars(
            select(m.ExchangeRateModel).where(m.ExchangeRateModel.company_id == company_id)
            .order_by(m.ExchangeRateModel.currency, m.ExchangeRateModel.effective_date.desc())).all()
        return [self._to_domain(r) for r in rows]

    def upsert(self, company_id: int, currency: str, rate: Decimal,
               effective_date) -> dom.ExchangeRate:
        """Un seul taux par (devise, date) : en saisir un second le remplace."""
        row = self.db.scalar(select(m.ExchangeRateModel).where(
            m.ExchangeRateModel.company_id == company_id,
            m.ExchangeRateModel.currency == currency,
            m.ExchangeRateModel.effective_date == effective_date))
        if row is None:
            row = m.ExchangeRateModel(company_id=company_id, currency=currency,
                                      effective_date=effective_date, rate=rate)
            self.db.add(row)
        else:
            row.rate = rate
        self.db.commit()
        self.db.refresh(row)
        return self._to_domain(row)

    def delete(self, company_id: int, rate_id: int) -> bool:
        row = self.db.get(m.ExchangeRateModel, rate_id)
        if row is None or row.company_id != company_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def find_applicable(self, company_id: int, currency: str, on_date,
                        allow_later: bool = False) -> dom.ExchangeRate | None:
        """Le taux le plus récent dont la date d'effet est antérieure ou égale à la date demandée.
        Si aucun n'existe et `allow_later`, le plus proche taux postérieur (le plus ancien
        enregistré après cette date) : mieux vaut un taux voisin, signalé et modifiable sur la
        facture, que bloquer le traitement parce qu'un taux a été saisi à une date d'effet récente."""
        base = select(m.ExchangeRateModel).where(
            m.ExchangeRateModel.company_id == company_id,
            m.ExchangeRateModel.currency == currency)
        row = self.db.scalar(base.where(m.ExchangeRateModel.effective_date <= on_date)
                             .order_by(m.ExchangeRateModel.effective_date.desc()).limit(1))
        if row is None and allow_later:
            row = self.db.scalar(base.where(m.ExchangeRateModel.effective_date > on_date)
                                 .order_by(m.ExchangeRateModel.effective_date.asc()).limit(1))
        return self._to_domain(row) if row else None


class MySQLUserRepository(ports.UserRepository):
    # Champs modifiables par l'utilisateur lui-même (jamais le rôle ni l'entreprise).
    PROFILE_FIELDS = {"full_name", "theme", "accent", "avatar_path", "password_hash"}

    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> dom.User | None:
        row = self.db.scalar(select(m.UserModel).where(m.UserModel.email == email))
        return _user_to_domain(row) if row else None

    def get_by_id(self, user_id: int) -> dom.User | None:
        row = self.db.get(m.UserModel, user_id)
        return _user_to_domain(row) if row else None

    def create(self, user: dom.User) -> dom.User:
        row = m.UserModel(email=user.email, password_hash=user.password_hash,
                          full_name=user.full_name, role=user.role.value,
                          company_id=user.company_id, is_active=user.is_active)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _user_to_domain(row)

    def list_all(self, company_id: int | None = None) -> list[dom.User]:
        query = select(m.UserModel).order_by(m.UserModel.id)
        if company_id is not None:
            query = query.where(m.UserModel.company_id == company_id)
        rows = self.db.scalars(query).all()
        return [_user_to_domain(r) for r in rows]

    def set_active(self, user_id: int, is_active: bool) -> dom.User | None:
        row = self.db.get(m.UserModel, user_id)
        if row is None:
            return None
        row.is_active = is_active
        self.db.commit()
        self.db.refresh(row)
        return _user_to_domain(row)

    def update_profile(self, user_id: int, **fields) -> dom.User | None:
        unknown = set(fields) - self.PROFILE_FIELDS
        if unknown:
            raise ValueError(f"Champs non modifiables : {sorted(unknown)}")
        row = self.db.get(m.UserModel, user_id)
        if row is None:
            return None
        for name, value in fields.items():
            setattr(row, name, value)
        self.db.commit()
        self.db.refresh(row)
        return _user_to_domain(row)


class MySQLSupplierRepository(ports.SupplierRepository):
    def __init__(self, db: Session):
        self.db = db

    def find_by_fuzzy_name(self, name: str, company_id: int,
                           threshold: int = 90) -> dom.Supplier | None:
        """Rapprochement flou (RapidFuzz) avec les fournisseurs connus de
        CETTE entreprise — robuste aux erreurs OCR sur le nom, et cloisonné
        par company_id (un fournisseur d'une autre entreprise ne doit
        jamais être rapproché par erreur)."""
        normalized = name.strip().upper()
        best_row, best_score = None, 0
        for row in self.db.scalars(select(m.SupplierModel)
                                   .where(m.SupplierModel.company_id == company_id)).all():
            score = fuzz.ratio(normalized, row.normalized_name)
            if score > best_score:
                best_row, best_score = row, score
        if best_row and best_score >= threshold:
            return self._to_domain(best_row)
        return None

    def get_or_create(self, supplier: dom.Supplier) -> dom.Supplier:
        existing = self.db.scalar(select(m.SupplierModel).where(
            m.SupplierModel.company_id == supplier.company_id,
            m.SupplierModel.normalized_name == supplier.normalized_name))
        if existing:
            return self._to_domain(existing)
        row = m.SupplierModel(company_id=supplier.company_id, name=supplier.name,
                              normalized_name=supplier.normalized_name,
                              nif=supplier.nif, stat=supplier.stat, address=supplier.address)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_domain(row)

    def get_by_id(self, supplier_id: int) -> dom.Supplier | None:
        row = self.db.get(m.SupplierModel, supplier_id)
        return self._to_domain(row) if row else None

    @staticmethod
    def _to_domain(row: m.SupplierModel) -> dom.Supplier:
        return dom.Supplier(id=row.id, company_id=row.company_id, name=row.name,
                            normalized_name=row.normalized_name,
                            nif=row.nif, stat=row.stat, address=row.address,
                            default_account_id=row.default_account_id)


class MySQLAccountRepository(ports.AccountRepository):
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_domain(row: m.AccountModel) -> dom.Account:
        return dom.Account(id=row.id, code=row.code, label=row.label,
                           account_class=row.account_class,
                           normal_balance=row.normal_balance,
                           parent_code=row.parent_code, is_active=row.is_active)

    def get_by_code(self, code: str, chart_id: int | None = None) -> dom.Account | None:
        """Compte d'un plan donné. Sans plan (anciens appels), le premier compte de ce code."""
        query = select(m.AccountModel).where(m.AccountModel.code == code)
        if chart_id is not None:
            query = query.where(m.AccountModel.chart_id == chart_id)
        row = self.db.scalars(query.order_by(m.AccountModel.id).limit(1)).first()
        return self._to_domain(row) if row else None

    def get_by_code_for_company(self, code: str, company_id: int) -> dom.Account | None:
        company = self.db.get(m.CompanyModel, company_id)
        return self.get_by_code(code, company.chart_id if company else None)

    def list_active(self, chart_id: int | None = None) -> list[dom.Account]:
        query = select(m.AccountModel).where(m.AccountModel.is_active.is_(True))
        if chart_id is not None:
            query = query.where(m.AccountModel.chart_id == chart_id)
        rows = self.db.scalars(query.order_by(m.AccountModel.code)).all()
        return [self._to_domain(r) for r in rows]


class MySQLInvoiceRepository(ports.InvoiceRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, invoice: dom.Invoice) -> dom.Invoice:
        row = m.InvoiceModel(
            company_id=invoice.company_id,
            uploaded_by=invoice.uploaded_by, original_filename=invoice.original_filename,
            storage_path=invoice.storage_path, mime_type=invoice.mime_type,
            file_size=invoice.file_size, status=invoice.status.value,
            currency=invoice.currency)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _invoice_to_domain(row)

    def update(self, invoice: dom.Invoice) -> dom.Invoice:
        row = self.db.get(m.InvoiceModel, invoice.id)
        row.status = invoice.status.value
        row.current_step = invoice.current_step.value if invoice.current_step else None
        row.document_type = invoice.document_type.value
        row.supplier_id = invoice.supplier_id
        row.language = invoice.language
        row.invoice_number = invoice.invoice_number
        row.invoice_date = invoice.invoice_date
        row.total_ht = invoice.total_ht
        row.total_vat = invoice.total_vat
        row.total_ttc = invoice.total_ttc
        row.currency = invoice.currency
        row.exchange_rate = invoice.exchange_rate
        row.arithmetic_ok = invoice.arithmetic_ok
        row.error_message = invoice.error_message
        self.db.commit()
        self.db.refresh(row)
        return _invoice_to_domain(row)

    def get_by_id(self, invoice_id: int) -> dom.Invoice | None:
        row = self.db.get(m.InvoiceModel, invoice_id)
        return _invoice_to_domain(row) if row else None

    def list_paginated(self, status: str | None, page: int, size: int,
                       company_id: int | None = None, search: str | None = None,
                       date_from=None, date_to=None, min_amount=None, max_amount=None):
        query = select(m.InvoiceModel)
        if status:
            query = query.where(m.InvoiceModel.status == status)
        if company_id is not None:
            query = query.where(m.InvoiceModel.company_id == company_id)
        if search and search.strip():
            term = search.strip().lower()
            query = query.outerjoin(
                m.SupplierModel, m.SupplierModel.id == m.InvoiceModel.supplier_id).where(or_(
                    func.lower(m.InvoiceModel.original_filename).contains(term, autoescape=True),
                    func.lower(m.InvoiceModel.invoice_number).contains(term, autoescape=True),
                    func.lower(m.SupplierModel.name).contains(term, autoescape=True)))
        if date_from is not None:
            query = query.where(m.InvoiceModel.invoice_date >= date_from)
        if date_to is not None:
            query = query.where(m.InvoiceModel.invoice_date <= date_to)
        if min_amount is not None:
            query = query.where(m.InvoiceModel.total_ttc >= min_amount)
        if max_amount is not None:
            query = query.where(m.InvoiceModel.total_ttc <= max_amount)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(query.order_by(m.InvoiceModel.id.desc())
                               .offset((page - 1) * size).limit(size)).all()
        return [_invoice_to_domain(r) for r in rows], total or 0

    def find_duplicate_id(self, invoice: dom.Invoice) -> int | None:
        """Plus ancienne facture non rejetée de la même entreprise qui porte le
        même TTC et soit le même n° de facture, soit le même fournisseur à la
        même date. Seule la plus récente est signalée comme doublon."""
        if invoice.total_ttc is None or invoice.id is None:
            return None
        same_document = []
        if invoice.invoice_number:
            same_document.append(m.InvoiceModel.invoice_number == invoice.invoice_number)
        if invoice.supplier_id and invoice.invoice_date:
            same_document.append(and_(m.InvoiceModel.supplier_id == invoice.supplier_id,
                                      m.InvoiceModel.invoice_date == invoice.invoice_date))
        if not same_document:
            return None
        return self.db.scalar(
            select(m.InvoiceModel.id)
            .where(m.InvoiceModel.company_id == invoice.company_id,
                   m.InvoiceModel.id < invoice.id,
                   m.InvoiceModel.status != "REJECTED",
                   m.InvoiceModel.total_ttc == invoice.total_ttc,
                   or_(*same_document))
            .order_by(m.InvoiceModel.id).limit(1))

    def reset_pipeline_results(self, invoice_id: int) -> None:
        """Efface OCR, entités et classification d'un passage précédent : le
        pipeline les recrée, et leurs clés d'unicité (une ligne par facture)
        interdisent sinon de relancer le traitement."""
        for model in (m.OcrResultModel, m.ExtractedEntityModel, m.ClassificationModel):
            self.db.execute(delete(model).where(model.invoice_id == invoice_id))
        self.db.commit()

    def delete(self, invoice_id: int) -> None:
        """Supprime la facture et ses résultats de traitement (OCR, entités, classification).
        Les écritures doivent avoir été supprimées avant (clé étrangère protégée)."""
        self.reset_pipeline_results(invoice_id)
        row = self.db.get(m.InvoiceModel, invoice_id)
        if row is not None:
            self.db.delete(row)
            self.db.commit()

    def save_ocr_result(self, invoice_id, engine, raw_text, mean_confidence, blocks, duration_ms):
        self.db.add(m.OcrResultModel(invoice_id=invoice_id, engine=engine,
                                     raw_text=raw_text, mean_confidence=mean_confidence,
                                     blocks=blocks, duration_ms=duration_ms))
        self.db.commit()

    def get_ocr_result(self, invoice_id: int) -> dict | None:
        row = self.db.scalar(select(m.OcrResultModel)
                             .where(m.OcrResultModel.invoice_id == invoice_id))
        if not row:
            return None
        return {"engine": row.engine, "raw_text": row.raw_text,
                "mean_confidence": float(row.mean_confidence),
                "blocks": row.blocks, "duration_ms": row.duration_ms}

    def save_entities(self, invoice_id: int, entities: list[dom.ExtractedEntity]) -> None:
        for e in entities:
            self.db.add(m.ExtractedEntityModel(
                invoice_id=invoice_id, entity_type=e.entity_type, raw_value=e.raw_value[:500],
                normalized_value=(e.normalized_value or "")[:500] or None,
                confidence=e.confidence, extraction_method=e.method.value,
                source_block=e.source_block))
        self.db.commit()

    def get_entities(self, invoice_id: int) -> list[dict]:
        rows = self.db.scalars(select(m.ExtractedEntityModel)
                               .where(m.ExtractedEntityModel.invoice_id == invoice_id)).all()
        return [{"entity_type": r.entity_type, "raw_value": r.raw_value,
                 "normalized_value": r.normalized_value, "confidence": float(r.confidence),
                 "method": r.extraction_method, "source_block": r.source_block}
                for r in rows]

    def save_classification(self, invoice_id, operation_type, probability,
                            probabilities, model_version):
        version_row = self.db.scalar(
            select(m.ModelVersionModel)
            .where(m.ModelVersionModel.name == "operation_classifier",
                   m.ModelVersionModel.version == model_version))
        if not version_row:
            version_row = m.ModelVersionModel(
                name="operation_classifier", version=model_version,
                algorithm="keyword" if model_version.startswith("keyword") else "sklearn",
                artifact_path="builtin", is_active=True)
            self.db.add(version_row)
            self.db.flush()
        self.db.add(m.ClassificationModel(
            invoice_id=invoice_id, model_version_id=version_row.id,
            operation_type=operation_type, probability=probability,
            probabilities=probabilities))
        self.db.commit()


class MySQLEntryRepository(ports.EntryRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, entry: dom.JournalEntry) -> dom.JournalEntry:
        rule_id = None
        if entry.rule_code:
            rule = self.db.scalar(select(m.AccountingRuleModel)
                                  .where(m.AccountingRuleModel.code == entry.rule_code))
            rule_id = rule.id if rule else None
        row = m.JournalEntryModel(
            invoice_id=entry.invoice_id, company_id=entry.company_id,
            rule_id=rule_id, entry_date=entry.entry_date,
            label=entry.label, status=entry.status.value,
            confidence_score=entry.confidence_score, currency=entry.currency,
            original_currency=entry.original_currency,
            original_amount=entry.original_amount, exchange_rate=entry.exchange_rate)
        for line in entry.lines:
            row.lines.append(m.EntryLineModel(
                account_id=line.account_id, label=line.label, debit=line.debit,
                credit=line.credit, account_confidence=line.account_confidence,
                suggested_by_ml=line.suggested_by_ml, line_order=line.line_order))
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _entry_to_domain(row)

    def update(self, entry: dom.JournalEntry) -> dom.JournalEntry:
        row = self.db.get(m.JournalEntryModel, entry.id)
        row.status = entry.status.value
        row.label = entry.label
        row.validated_by = entry.validated_by
        row.validated_at = entry.validated_at
        # Mise à jour des lignes existantes (correction du comptable)
        lines_by_id = {line.id: line for line in entry.lines if line.id}
        for line_row in row.lines:
            if line_row.id in lines_by_id:
                src = lines_by_id[line_row.id]
                line_row.account_id = src.account_id
                line_row.label = src.label
                line_row.debit = src.debit
                line_row.credit = src.credit
        self.db.commit()
        self.db.refresh(row)
        return _entry_to_domain(row)

    def get_by_id(self, entry_id: int) -> dom.JournalEntry | None:
        row = self.db.get(m.JournalEntryModel, entry_id)
        return _entry_to_domain(row) if row else None

    def list_by_invoice(self, invoice_id: int) -> list[dom.JournalEntry]:
        rows = self.db.scalars(select(m.JournalEntryModel)
                               .where(m.JournalEntryModel.invoice_id == invoice_id)).unique().all()
        return [_entry_to_domain(r) for r in rows]

    def list_paginated(self, status: str | None, page: int, size: int,
                       company_id: int | None = None):
        query = select(m.JournalEntryModel)
        if status:
            query = query.where(m.JournalEntryModel.status == status)
        if company_id is not None:
            query = query.where(m.JournalEntryModel.company_id == company_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(query.order_by(m.JournalEntryModel.id.desc())
                               .offset((page - 1) * size).limit(size)).unique().all()
        return [_entry_to_domain(r) for r in rows], total or 0

    def delete_unvalidated_by_invoice(self, invoice_id: int) -> int:
        """Supprime les écritures proposées/corrigées d'une facture avant d'en
        générer une nouvelle : sans cela, chaque relance ajouterait un doublon.
        Les écritures validées ne sont jamais touchées."""
        rows = self.db.scalars(select(m.JournalEntryModel).where(
            m.JournalEntryModel.invoice_id == invoice_id,
            m.JournalEntryModel.status != "VALIDATED")).unique().all()
        for row in rows:
            self.db.execute(delete(m.CorrectionModel).where(m.CorrectionModel.entry_id == row.id))
            self.db.delete(row)
        self.db.commit()
        return len(rows)

    def has_validated_for_invoice(self, invoice_id: int) -> bool:
        return (self.db.scalar(select(func.count()).select_from(m.JournalEntryModel).where(
            m.JournalEntryModel.invoice_id == invoice_id,
            m.JournalEntryModel.status == "VALIDATED")) or 0) > 0

    def count_for_company(self, company_id: int) -> int:
        return self.db.scalar(select(func.count()).select_from(m.JournalEntryModel).where(
            m.JournalEntryModel.company_id == company_id)) or 0

    def count_validated(self, company_id: int) -> int:
        return self.db.scalar(select(func.count()).select_from(m.JournalEntryModel).where(
            m.JournalEntryModel.company_id == company_id,
            m.JournalEntryModel.status == "VALIDATED")) or 0

    def save_correction(self, entry_id, line_id, user_id, field_name, original, corrected):
        self.db.add(m.CorrectionModel(
            entry_id=entry_id, entry_line_id=line_id, corrected_by=user_id,
            field_name=field_name, original_value=str(original)[:500],
            corrected_value=str(corrected)[:500]))
        self.db.commit()


class MySQLRuleRepository(ports.RuleRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_active_for_operation(self, operation_type: str, chart_id: int | None = None) -> dict | None:
        query = select(m.AccountingRuleModel).where(
            m.AccountingRuleModel.operation_type == operation_type,
            m.AccountingRuleModel.is_active.is_(True))
        if chart_id is not None:
            query = query.where(m.AccountingRuleModel.chart_id == chart_id)
        row = self.db.scalars(query.order_by(m.AccountingRuleModel.priority).limit(1)).first()
        if not row:
            return None
        return {"id": row.id, "code": row.code, "description": row.description,
                "template": row.template, "operation_type": row.operation_type}

    def list_all(self) -> list[dict]:
        rows = self.db.scalars(select(m.AccountingRuleModel)
                               .order_by(m.AccountingRuleModel.code)).all()
        return [{"id": r.id, "code": r.code, "description": r.description,
                 "operation_type": r.operation_type, "template": r.template,
                 "priority": r.priority, "is_active": r.is_active} for r in rows]


class MySQLAuditRepository(ports.AuditRepository):
    def __init__(self, db: Session):
        self.db = db

    def log(self, user_id, action, entity_type, entity_id, old_value=None, new_value=None):
        self.db.add(m.AuditLogModel(user_id=user_id, action=action,
                                    entity_type=entity_type, entity_id=entity_id,
                                    old_value=old_value, new_value=new_value))
        self.db.commit()

    def list_paginated(self, page: int, size: int):
        total = self.db.scalar(select(func.count(m.AuditLogModel.id)))
        rows = self.db.execute(
            select(m.AuditLogModel, m.UserModel.full_name)
            .outerjoin(m.UserModel, m.UserModel.id == m.AuditLogModel.user_id)
            .order_by(m.AuditLogModel.id.desc())
            .offset((page - 1) * size).limit(size)).all()
        return [{"id": r.id, "user_id": r.user_id,
                 "user_name": user_name,  # null pour les actions système (pipeline IA)
                 "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
                 "old_value": r.old_value, "new_value": r.new_value,
                 "created_at": r.created_at.isoformat()} for r, user_name in rows], total or 0
