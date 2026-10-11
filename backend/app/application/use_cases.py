"""Use cases applicatifs (hors pipeline) : upload, validation/correction
des écritures, authentification. Un use case = un cas d'utilisation UML."""
import logging
from datetime import datetime
from decimal import Decimal

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.domain.entities import EntryStatus, Invoice, InvoiceStatus, JournalEntry
from app.domain.ports import (
    AccountRepository, AuditRepository, EntryRepository, FileStorage,
    InvoiceRepository, UserRepository,
)
from app.domain.rules import BalanceValidator, UnbalancedEntryError

logger = logging.getLogger(__name__)


class UseCaseError(Exception):
    """Erreur métier remontée en 4xx par la couche présentation."""


# ------------------------------------------------------------------- Auth

class AuthenticateUserUseCase:
    def __init__(self, users: UserRepository):
        self.users = users

    def execute(self, email: str, password: str) -> dict:
        user = self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise UseCaseError("Identifiants invalides")
        token = create_access_token(str(user.id), user.role.value)
        return {"access_token": token, "token_type": "bearer",
                "user": {"id": user.id, "email": user.email,
                         "full_name": user.full_name, "role": user.role.value,
                         "company_id": user.company_id}}


# ------------------------------------------------------------------ Upload

class UploadInvoiceUseCase:
    def __init__(self, invoices: InvoiceRepository, storage: FileStorage,
                 audit: AuditRepository):
        self.invoices = invoices
        self.storage = storage
        self.audit = audit
        self.settings = get_settings()

    def execute(self, content: bytes, filename: str, mime_type: str,
                user_id: int, company_id: int) -> Invoice:
        if mime_type not in self.settings.allowed_mime_types:
            raise UseCaseError(f"Type de fichier non autorisé : {mime_type}. "
                               "Formats acceptés : PDF, JPG, PNG.")
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise UseCaseError(f"Fichier trop volumineux "
                               f"(max {self.settings.max_upload_size_mb} Mo).")
        if len(content) == 0:
            raise UseCaseError("Fichier vide.")

        path = self.storage.save(content, filename)
        invoice = self.invoices.create(Invoice(
            id=None, original_filename=filename, storage_path=path,
            mime_type=mime_type, file_size=len(content), uploaded_by=user_id,
            company_id=company_id, currency=self.settings.default_currency))
        self.audit.log(user_id, "INVOICE_UPLOADED", "invoice", invoice.id,
                       new_value={"filename": filename, "size": len(content)})
        return invoice


# ------------------------------------------------- Validation / correction

class CorrectEntryUseCase:
    """Corrige une écriture proposée. Chaque champ modifié est historisé
    dans `corrections` : c'est la matière première du réentraînement."""

    def __init__(self, entries: EntryRepository, accounts: AccountRepository,
                 audit: AuditRepository):
        self.entries = entries
        self.accounts = accounts
        self.audit = audit

    def execute(self, entry_id: int, user_id: int, corrections: list[dict]) -> JournalEntry:
        entry = self.entries.get_by_id(entry_id)
        if entry is None:
            raise UseCaseError("Écriture introuvable")
        if entry.status == EntryStatus.VALIDATED:
            raise UseCaseError("Écriture déjà validée : correction impossible "
                               "(intangibilité des enregistrements, PCG art. 420-4)")

        lines_by_id = {line.id: line for line in entry.lines}
        for correction in corrections:
            line = lines_by_id.get(correction.get("line_id"))
            field = correction["field"]
            new_value = correction["new_value"]
            if line is None:
                raise UseCaseError(f"Ligne {correction.get('line_id')} inconnue")

            if field == "account_code":
                # Le compte doit appartenir au plan comptable de l'entreprise de l'écriture
                account = self.accounts.get_by_code_for_company(str(new_value), entry.company_id)
                if account is None:
                    raise UseCaseError(f"Compte {new_value} absent du plan comptable")
                old = line.account_code
                line.account_id, line.account_code = account.id, account.code
            elif field in ("debit", "credit"):
                old = str(getattr(line, field))
                setattr(line, field, Decimal(str(new_value)))
            elif field == "label":
                old = line.label
                line.label = str(new_value)[:255]
            else:
                raise UseCaseError(f"Champ non corrigeable : {field}")

            self.entries.save_correction(entry.id, line.id, user_id, field,
                                         old, str(new_value))

        try:
            BalanceValidator.validate(entry)
        except UnbalancedEntryError as exc:
            raise UseCaseError(str(exc)) from exc

        entry.status = EntryStatus.CORRECTED
        updated = self.entries.update(entry)
        self.audit.log(user_id, "ENTRY_CORRECTED", "journal_entry", entry.id,
                       new_value={"corrections": len(corrections)})
        return updated


class ValidateEntryUseCase:
    """Validation définitive par le comptable. Re-vérifie l'équilibre
    (le comptable a pu modifier des montants) — second point de contrôle."""

    def __init__(self, entries: EntryRepository, invoices: InvoiceRepository,
                 audit: AuditRepository):
        self.entries = entries
        self.invoices = invoices
        self.audit = audit

    def execute(self, entry_id: int, user_id: int) -> JournalEntry:
        entry = self.entries.get_by_id(entry_id)
        if entry is None:
            raise UseCaseError("Écriture introuvable")
        if entry.status == EntryStatus.VALIDATED:
            raise UseCaseError("Écriture déjà validée")

        try:
            BalanceValidator.validate(entry)  # invariant re-vérifié
        except UnbalancedEntryError as exc:
            raise UseCaseError(str(exc)) from exc

        entry.status = EntryStatus.VALIDATED
        entry.validated_by = user_id
        entry.validated_at = datetime.utcnow()
        updated = self.entries.update(entry)

        invoice = self.invoices.get_by_id(entry.invoice_id)
        if invoice:
            invoice.status = InvoiceStatus.VALIDATED
            self.invoices.update(invoice)

        self.audit.log(user_id, "ENTRY_VALIDATED", "journal_entry", entry.id,
                       new_value={"total_debit": str(entry.total_debit()),
                                  "total_credit": str(entry.total_credit())})
        return updated


class RejectInvoiceUseCase:
    def __init__(self, invoices: InvoiceRepository, audit: AuditRepository):
        self.invoices = invoices
        self.audit = audit

    def execute(self, invoice_id: int, user_id: int, reason: str) -> Invoice:
        invoice = self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise UseCaseError("Facture introuvable")
        invoice.status = InvoiceStatus.REJECTED
        invoice.error_message = reason[:500]
        updated = self.invoices.update(invoice)
        self.audit.log(user_id, "INVOICE_REJECTED", "invoice", invoice_id,
                       new_value={"reason": reason})
        return updated
