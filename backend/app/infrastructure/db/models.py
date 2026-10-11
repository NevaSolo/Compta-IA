"""Modèles ORM SQLAlchemy — projection exacte du MPD validé en Phase 5
(database/schema.sql). Les contraintes fortes (CHECK, FK, DECIMAL) vivent
dans le schéma SQL ; l'ORM ne fait que s'y conformer."""
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base


class ChartModel(Base):
    """Plan comptable (catalogue) : regroupe des comptes et des règles d'écriture."""
    __tablename__ = "charts"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyModel(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    nif: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stat: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="MGA")
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("charts.id", ondelete="RESTRICT"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    theme: Mapped[str] = mapped_column(String(10), default="auto")
    accent: Mapped[str] = mapped_column(String(10), default="blue")
    role: Mapped[str] = mapped_column(
        Enum("ADMIN", "ENTREPRISE_ADMIN", "COMPTABLE"), default="COMPTABLE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccountModel(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("chart_id", "code", name="uq_accounts_chart_code"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("charts.id", ondelete="RESTRICT"), nullable=True)
    code: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(255))
    account_class: Mapped[int] = mapped_column(SmallInteger)
    parent_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    normal_balance: Mapped[str] = mapped_column(Enum("DEBIT", "CREDIT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierModel(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("company_id", "normalized_name",
                                       name="uq_suppliers_company_normalized"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    nif: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stat: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InvoiceModel(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="RESTRICT"))
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("UPLOADED", "PREPROCESSING", "OCR_DONE", "ANALYZED",
             "ENTRIES_PROPOSED", "VALIDATED", "REJECTED", "ERROR"),
        default="UPLOADED")
    current_step: Mapped[str | None] = mapped_column(
        Enum("PREPROCESSING", "OCR", "LANGUAGE_DETECTION", "ENTITY_EXTRACTION",
             "COHERENCE_CHECK", "CLASSIFICATION", "RULE_ENGINE",
             "CONFIDENCE_SCORING", "DONE"),
        nullable=True)
    document_type: Mapped[str] = mapped_column(
        Enum("FACTURE", "AVOIR"), default="FACTURE")
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    total_ht: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    total_vat: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    total_ttc: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="MGA")
    exchange_rate: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    arithmetic_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier = relationship("SupplierModel", lazy="joined")


class OcrResultModel(Base):
    __tablename__ = "ocr_results"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"), unique=True)
    engine: Mapped[str] = mapped_column(Enum("EASYOCR", "TESSERACT", "PDF_TEXT"))
    raw_text: Mapped[str] = mapped_column(Text)
    mean_confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    blocks: Mapped[dict] = mapped_column(JSON)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExtractedEntityModel(Base):
    __tablename__ = "extracted_entities"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(50))
    raw_value: Mapped[str] = mapped_column(String(500))
    normalized_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    extraction_method: Mapped[str] = mapped_column(Enum("REGEX", "NER"))
    source_block: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelVersionModel(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(20))
    algorithm: Mapped[str] = mapped_column(String(100))
    artifact_path: Mapped[str] = mapped_column(String(500))
    accuracy: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    training_samples: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClassificationModel(Base):
    __tablename__ = "classifications"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"), unique=True)
    model_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model_versions.id"))
    operation_type: Mapped[str] = mapped_column(
        Enum("ACHAT_MARCHANDISES", "ACHAT_SERVICES", "ACHAT_IMMOBILISATION", "AUTRE"))
    probability: Mapped[float] = mapped_column(Numeric(5, 4))
    probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccountingRuleModel(Base):
    __tablename__ = "accounting_rules"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("charts.id", ondelete="RESTRICT"), nullable=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    operation_type: Mapped[str] = mapped_column(
        Enum("ACHAT_MARCHANDISES", "ACHAT_SERVICES", "ACHAT_IMMOBILISATION", "AUTRE"))
    description: Mapped[str] = mapped_column(String(500))
    template: Mapped[dict] = mapped_column(JSON)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JournalEntryModel(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="RESTRICT"))
    invoice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("invoices.id"))
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounting_rules.id", ondelete="SET NULL"), nullable=True)
    entry_date: Mapped[Date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="MGA")
    original_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    original_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("PROPOSED", "CORRECTED", "VALIDATED"), default="PROPOSED")
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    validated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lines = relationship("EntryLineModel", cascade="all, delete-orphan", lazy="joined",
                         order_by="EntryLineModel.line_order")
    rule = relationship("AccountingRuleModel", lazy="joined")


class EntryLineModel(Base):
    __tablename__ = "entry_lines"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"))
    label: Mapped[str] = mapped_column(String(255))
    debit: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    account_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    suggested_by_ml: Mapped[bool] = mapped_column(Boolean, default=False)
    line_order: Mapped[int] = mapped_column(SmallInteger, default=0)

    account = relationship("AccountModel", lazy="joined")


class CorrectionModel(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="CASCADE"))
    entry_line_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("entry_lines.id", ondelete="SET NULL"), nullable=True)
    corrected_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    field_name: Mapped[str] = mapped_column(String(50))
    original_value: Mapped[str] = mapped_column(String(500))
    corrected_value: Mapped[str] = mapped_column(String(500))
    used_for_training: Mapped[bool] = mapped_column(Boolean, default=False)
    corrected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExchangeRateModel(Base):
    """Taux de change d'une entreprise : 1 unité de `currency` = `rate` unités
    de sa devise de tenue de comptabilité, à partir de `effective_date`."""
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("company_id", "currency", "effective_date",
                                       name="uq_rate_company_currency_date"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"))
    currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float] = mapped_column(Numeric(18, 6))
    effective_date: Mapped[Date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
