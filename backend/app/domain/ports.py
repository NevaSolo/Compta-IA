"""Ports du domaine (interfaces abstraites).

Principe d'inversion de dépendances (SOLID « D ») : le domaine DÉFINIT les
interfaces, l'infrastructure les IMPLÉMENTE. Le métier ne connaît ni MySQL,
ni EasyOCR, ni scikit-learn — uniquement ces contrats.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.domain.entities import (
    Account, Company, ExtractedEntity, Invoice, JournalEntry, OperationType, Supplier, User,
)


# ------------------------------------------------------ Résultats typés

@dataclass
class OcrBlock:
    text: str
    bbox: list  # 4 points [[x,y],...]
    confidence: float


@dataclass
class OcrResult:
    engine: str
    raw_text: str
    mean_confidence: float
    blocks: list[OcrBlock] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class ClassificationResult:
    operation_type: OperationType
    probability: float
    probabilities: dict[str, float] = field(default_factory=dict)
    model_version: str = "keyword-0.1.0"


@dataclass
class AccountSuggestion:
    account_code: str
    confidence: float
    suggested_by_ml: bool


# --------------------------------------------------------- Ports IA

class OCREngine(ABC):
    """Contrat d'un moteur OCR. Implémentations : EasyOCR (principal),
    Tesseract (fallback)."""

    @abstractmethod
    def extract_text(self, image_path: str, languages: list[str]) -> OcrResult: ...


class EntityExtractor(ABC):
    """Contrat d'extraction d'entités depuis un résultat OCR."""

    @abstractmethod
    def extract(self, ocr_result: OcrResult, language: str | None) -> list[ExtractedEntity]: ...


class OperationClassifier(ABC):
    """Contrat de classification du type d'opération comptable."""

    @abstractmethod
    def classify(self, text: str, supplier_name: str | None,
                 amount: float | None) -> ClassificationResult: ...


class AccountSuggester(ABC):
    """Contrat de suggestion du compte précis, RESTREINT à une liste de
    candidats issus de la règle comptable (le ML n'impute jamais hors PCG)."""

    @abstractmethod
    def suggest(self, text: str, supplier: Supplier | None,
                candidates: list[str], default: str) -> AccountSuggestion: ...


class FileStorage(ABC):
    @abstractmethod
    def save(self, content: bytes, filename: str) -> str: ...

    @abstractmethod
    def read(self, path: str) -> bytes: ...


# ------------------------------------------------------ Repositories

class CompanyRepository(ABC):
    @abstractmethod
    def create(self, company: Company) -> Company: ...
    @abstractmethod
    def get_by_id(self, company_id: int) -> Company | None: ...
    @abstractmethod
    def list_all(self) -> list[Company]: ...
    @abstractmethod
    def set_active(self, company_id: int, is_active: bool) -> Company | None: ...
    @abstractmethod
    def update_branding(self, company_id: int, **fields) -> Company | None: ...


class UserRepository(ABC):
    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...
    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...
    @abstractmethod
    def create(self, user: User) -> User: ...
    @abstractmethod
    def list_all(self, company_id: int | None = None) -> list[User]: ...
    @abstractmethod
    def set_active(self, user_id: int, is_active: bool) -> User | None: ...
    @abstractmethod
    def update_profile(self, user_id: int, **fields) -> User | None: ...


class SupplierRepository(ABC):
    @abstractmethod
    def find_by_fuzzy_name(self, name: str, company_id: int,
                           threshold: int = 90) -> Supplier | None: ...
    @abstractmethod
    def get_or_create(self, supplier: Supplier) -> Supplier: ...
    @abstractmethod
    def get_by_id(self, supplier_id: int) -> Supplier | None: ...


class AccountRepository(ABC):
    @abstractmethod
    def get_by_code(self, code: str) -> Account | None: ...
    @abstractmethod
    def list_active(self) -> list[Account]: ...


class InvoiceRepository(ABC):
    @abstractmethod
    def create(self, invoice: Invoice) -> Invoice: ...
    @abstractmethod
    def update(self, invoice: Invoice) -> Invoice: ...
    @abstractmethod
    def get_by_id(self, invoice_id: int) -> Invoice | None: ...
    @abstractmethod
    def list_paginated(self, status: str | None, page: int, size: int,
                       company_id: int | None = None, search: str | None = None,
                       date_from=None, date_to=None, min_amount=None,
                       max_amount=None) -> tuple[list[Invoice], int]: ...
    @abstractmethod
    def find_duplicate_id(self, invoice: Invoice) -> int | None: ...
    @abstractmethod
    def save_ocr_result(self, invoice_id: int, engine: str, raw_text: str,
                        mean_confidence: float, blocks: list, duration_ms: int) -> None: ...
    @abstractmethod
    def get_ocr_result(self, invoice_id: int) -> dict | None: ...
    @abstractmethod
    def save_entities(self, invoice_id: int, entities: list[ExtractedEntity]) -> None: ...
    @abstractmethod
    def get_entities(self, invoice_id: int) -> list[dict]: ...
    @abstractmethod
    def save_classification(self, invoice_id: int, operation_type: str,
                            probability: float, probabilities: dict,
                            model_version: str) -> None: ...


class EntryRepository(ABC):
    @abstractmethod
    def create(self, entry: JournalEntry) -> JournalEntry: ...
    @abstractmethod
    def update(self, entry: JournalEntry) -> JournalEntry: ...
    @abstractmethod
    def get_by_id(self, entry_id: int) -> JournalEntry | None: ...
    @abstractmethod
    def list_by_invoice(self, invoice_id: int) -> list[JournalEntry]: ...
    @abstractmethod
    def list_paginated(self, status: str | None, page: int, size: int,
                       company_id: int | None = None) -> tuple[list[JournalEntry], int]: ...
    @abstractmethod
    def save_correction(self, entry_id: int, line_id: int | None, user_id: int,
                        field_name: str, original: str, corrected: str) -> None: ...


class RuleRepository(ABC):
    @abstractmethod
    def get_active_for_operation(self, operation_type: str) -> dict | None: ...
    @abstractmethod
    def list_all(self) -> list[dict]: ...


class AuditRepository(ABC):
    @abstractmethod
    def log(self, user_id: int | None, action: str, entity_type: str,
            entity_id: int, old_value: dict | None = None,
            new_value: dict | None = None) -> None: ...
    @abstractmethod
    def list_paginated(self, page: int, size: int) -> tuple[list[dict], int]: ...
