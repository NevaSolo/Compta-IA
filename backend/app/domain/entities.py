"""Entités du domaine métier.

Couche la plus interne de la Clean Architecture : aucune dépendance vers
un framework, une base de données ou une bibliothèque IA. Uniquement des
structures de données et des invariants métier.
Les montants sont TOUJOURS des Decimal (jamais de float en comptabilité).
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


# ---------------------------------------------------------------- Enums

class Role(str, Enum):
    ADMIN = "ADMIN"              # administrateur global de la plateforme (toutes entreprises)
    ENTREPRISE_ADMIN = "ENTREPRISE_ADMIN"  # admin d'une entreprise (gère ses propres comptables)
    COMPTABLE = "COMPTABLE"


class InvoiceStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PREPROCESSING = "PREPROCESSING"
    OCR_DONE = "OCR_DONE"
    ANALYZED = "ANALYZED"
    ENTRIES_PROPOSED = "ENTRIES_PROPOSED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class PipelineStep(str, Enum):
    """Étape courante du pipeline IA (Phase 6, docs/ia/pipeline-ia.md),
    affichée en temps réel côté frontend pendant le traitement — plus fine
    que InvoiceStatus, qui regroupe plusieurs étapes sous un même statut."""
    PREPROCESSING = "PREPROCESSING"
    OCR = "OCR"
    LANGUAGE_DETECTION = "LANGUAGE_DETECTION"
    ENTITY_EXTRACTION = "ENTITY_EXTRACTION"
    COHERENCE_CHECK = "COHERENCE_CHECK"
    CLASSIFICATION = "CLASSIFICATION"
    RULE_ENGINE = "RULE_ENGINE"
    CONFIDENCE_SCORING = "CONFIDENCE_SCORING"
    DONE = "DONE"


class DocumentType(str, Enum):
    """Nature du document comptable : une facture d'avoir (note de crédit
    fournisseur) doit générer une écriture au sens inversé par rapport à
    une facture d'achat normale (cf. RuleEngine.generate_entry)."""
    FACTURE = "FACTURE"
    AVOIR = "AVOIR"


class EntryStatus(str, Enum):
    PROPOSED = "PROPOSED"
    CORRECTED = "CORRECTED"
    VALIDATED = "VALIDATED"


class OperationType(str, Enum):
    ACHAT_MARCHANDISES = "ACHAT_MARCHANDISES"
    ACHAT_SERVICES = "ACHAT_SERVICES"
    ACHAT_IMMOBILISATION = "ACHAT_IMMOBILISATION"
    AUTRE = "AUTRE"


class ExtractionMethod(str, Enum):
    REGEX = "REGEX"
    NER = "NER"


# ------------------------------------------------------------- Entités

@dataclass
class Company:
    """Une entreprise cliente (tenant) : ses factures, écritures et
    fournisseurs sont cloisonnés des autres entreprises par company_id."""
    id: int | None
    name: str
    nif: str | None = None
    stat: str | None = None
    address: str | None = None
    is_active: bool = True


@dataclass
class User:
    id: int | None
    email: str
    full_name: str
    role: Role
    # None uniquement pour l'ADMIN global (aucune entreprise) ; obligatoire
    # pour ENTREPRISE_ADMIN et COMPTABLE.
    company_id: int | None = None
    is_active: bool = True
    password_hash: str = ""


@dataclass
class Supplier:
    id: int | None
    company_id: int
    name: str
    normalized_name: str
    nif: str | None = None
    stat: str | None = None
    address: str | None = None
    default_account_id: int | None = None


@dataclass
class ExtractedEntity:
    """Une information extraite de la facture, avec sa traçabilité complète :
    méthode d'extraction, confiance, et zone source sur l'image."""
    entity_type: str
    raw_value: str
    normalized_value: str | None
    confidence: float
    method: ExtractionMethod
    source_block: dict | None = None


@dataclass
class Invoice:
    id: int | None
    original_filename: str
    storage_path: str
    mime_type: str
    file_size: int
    uploaded_by: int
    company_id: int
    status: InvoiceStatus = InvoiceStatus.UPLOADED
    current_step: PipelineStep | None = None
    document_type: DocumentType = DocumentType.FACTURE
    supplier_id: int | None = None
    language: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    total_ht: Decimal | None = None
    total_vat: Decimal | None = None
    total_ttc: Decimal | None = None
    currency: str = "MGA"
    arithmetic_ok: bool | None = None
    error_message: str | None = None

    def check_arithmetic(self, tolerance: Decimal = Decimal("1")) -> bool | None:
        """Contrôle HT + TVA = TTC (tolérance d'arrondi d'une unité monétaire).
        Retourne None si les montants ne sont pas tous disponibles."""
        if self.total_ht is None or self.total_vat is None or self.total_ttc is None:
            return None
        return abs((self.total_ht + self.total_vat) - self.total_ttc) <= tolerance


@dataclass
class Account:
    id: int | None
    code: str
    label: str
    account_class: int
    normal_balance: str  # 'DEBIT' | 'CREDIT'
    parent_code: str | None = None
    is_active: bool = True


@dataclass
class EntryLine:
    account_id: int
    account_code: str
    label: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    account_confidence: float | None = None
    suggested_by_ml: bool = False
    line_order: int = 0
    id: int | None = None

    def is_valid_side(self) -> bool:
        """Une ligne est soit au débit, soit au crédit — jamais les deux ni aucun."""
        return (self.debit > 0 and self.credit == 0) or (self.credit > 0 and self.debit == 0)


@dataclass
class JournalEntry:
    """Écriture comptable. Invariant fondamental : équilibre débit/crédit,
    porté par l'entité elle-même (le métier se protège tout seul)."""
    invoice_id: int
    company_id: int
    entry_date: date
    label: str
    lines: list[EntryLine] = field(default_factory=list)
    status: EntryStatus = EntryStatus.PROPOSED
    confidence_score: float | None = None
    rule_code: str | None = None
    id: int | None = None
    validated_by: int | None = None
    validated_at: datetime | None = None

    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0"))

    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0"))

    def is_balanced(self) -> bool:
        return self.total_debit() == self.total_credit()
