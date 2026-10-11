"""Schémas Pydantic (contrats de l'API REST). Miroirs typés des entités
du domaine — la validation stricte des données financières se joue ici."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


# --------------------------------------------------------------- Auth
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    company_id: int | None = None
    company_name: str | None = None
    is_active: bool = True
    # Personnalisation. Les *_version (horodatage du fichier) servent de clé de
    # cache : l'image n'est retéléchargée que si elle a changé.
    theme: str = "auto"
    accent: str = "blue"
    avatar_version: int | None = None
    company_logo_version: int | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    theme: str | None = Field(default=None, pattern="^(auto|light|dark)$")
    accent: str | None = Field(default=None, pattern="^(blue|emerald|violet|rose|amber|slate)$")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class CompanyBrandingUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class UserActiveUpdate(BaseModel):
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=150)
    role: str = Field(pattern="^(ADMIN|ENTREPRISE_ADMIN|COMPTABLE)$")
    # Obligatoire pour ENTREPRISE_ADMIN/COMPTABLE (ignoré/forcé selon
    # l'appelant — voir routers/auth.py::create_user).
    company_id: int | None = None


# ------------------------------------------------------------ Entreprises
class CompanyOut(BaseModel):
    id: int
    name: str
    nif: str | None = None
    stat: str | None = None
    address: str | None = None
    is_active: bool = True
    logo_version: int | None = None


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    nif: str | None = Field(default=None, max_length=50)
    stat: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)


class CompanyActiveUpdate(BaseModel):
    is_active: bool


# ------------------------------------------------------------ Factures
class InvoiceOut(BaseModel):
    id: int
    company_id: int | None = None
    company_name: str | None = None
    original_filename: str
    status: str
    current_step: str | None = None
    document_type: str = "FACTURE"
    supplier_id: int | None = None
    supplier_name: str | None = None
    language: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    total_ht: Decimal | None = None
    total_vat: Decimal | None = None
    total_ttc: Decimal | None = None
    currency: str = "MGA"
    arithmetic_ok: bool | None = None
    error_message: str | None = None
    # Id d'une facture plus ancienne qui semble être la même (même TTC et même
    # n° ou même fournisseur/date) : calculé à la lecture, rien n'est stocké.
    duplicate_of: int | None = None


class PaginatedInvoices(BaseModel):
    items: list[InvoiceOut]
    total: int
    page: int
    size: int


class ExtractedEntityOut(BaseModel):
    entity_type: str
    raw_value: str
    normalized_value: str | None
    confidence: float
    method: str
    source_block: dict | None = None


class OcrResultOut(BaseModel):
    engine: str
    raw_text: str
    mean_confidence: float
    duration_ms: int
    blocks: list


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ------------------------------------------------------------ Écritures
class EntryLineOut(BaseModel):
    id: int | None
    account_code: str
    label: str
    debit: Decimal
    credit: Decimal
    account_confidence: float | None = None
    suggested_by_ml: bool = False


class EntryOut(BaseModel):
    id: int
    invoice_id: int
    entry_date: date
    label: str
    status: str
    confidence_score: float | None = None
    rule_code: str | None = None
    validated_at: datetime | None = None
    total_debit: Decimal
    total_credit: Decimal
    lines: list[EntryLineOut]


class BatchValidateRequest(BaseModel):
    entry_ids: list[int] = Field(min_length=1, max_length=200)


class BatchValidateItem(BaseModel):
    id: int
    ok: bool
    error: str | None = None


class BatchValidateResult(BaseModel):
    validated: int
    failed: int
    results: list[BatchValidateItem]


class PaginatedEntries(BaseModel):
    items: list[EntryOut]
    total: int
    page: int
    size: int


class LineCorrection(BaseModel):
    line_id: int
    field: str = Field(pattern="^(account_code|debit|credit|label)$")
    new_value: str


class CorrectEntryRequest(BaseModel):
    corrections: list[LineCorrection] = Field(min_length=1)


# --------------------------------------------------------------- Divers
class AccountOut(BaseModel):
    code: str
    label: str
    account_class: int
    normal_balance: str


class MonthlyVolumePoint(BaseModel):
    month: str  # "YYYY-MM"
    invoice_count: int
    total_ttc: float


class DashboardStats(BaseModel):
    total_invoices: int
    pending_review: int
    validated: int
    errors: int
    validated_without_correction_rate: float | None
    average_confidence: float | None
    invoices_by_status: dict
    operations_by_type: dict[str, int]
    monthly_volume: list[MonthlyVolumePoint]
    recent_invoices: list[InvoiceOut]
