"""Suppression d'une facture NON validée : tout disparaît (fichier, traitement, écritures
proposées) ; une facture validée est intouchable ; cloisonnement entre entreprises."""
import io
from datetime import date

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application import pipeline as pipeline_module
from app.core.config import get_settings
from app.core.security import hash_password
from app.domain.entities import OperationType
from app.domain.ports import ClassificationResult
from app.infrastructure.db import models as m
from app.infrastructure.storage.local_storage import LocalFileStorage


def _login(client, email, password):
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _invoice(db, user, tmp_path, status="ENTRIES_PROPOSED", with_file=True, **fields):
    path = tmp_path / f"{status}-{fields.get('original_filename', 'f.pdf')}"
    if with_file:
        path.write_bytes(b"%PDF-1.4 contenu")
    row = m.InvoiceModel(**{**dict(company_id=user.company_id, uploaded_by=user.id, original_filename="f.pdf",
                                   storage_path=str(path), mime_type="application/pdf", file_size=10,
                                   status=status), **fields})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, path


def _entry(db, invoice, accounts, status="PROPOSED"):
    by_code = {a.code: a for a in accounts}
    entry = m.JournalEntryModel(invoice_id=invoice.id, company_id=invoice.company_id, entry_date=date(2026, 1, 15),
                                label="Facture", status=status)
    if status == "VALIDATED":
        entry.validated_by = invoice.uploaded_by
        entry.validated_at = __import__("datetime").datetime(2026, 1, 16)
    entry.lines = [
        m.EntryLineModel(account_id=by_code["607"].id, label="Achat", debit=100, credit=0, line_order=0),
        m.EntryLineModel(account_id=by_code["401"].id, label="Fournisseur", debit=0, credit=100, line_order=1),
    ]
    db.add(entry)
    db.commit()
    return entry


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))


class TestDeleteUnvalidatedInvoice:
    def test_removes_invoice_file_entries_and_lines(self, client, db_session, comptable_user, auth_headers,
                                                    minimal_chart_of_accounts, tmp_path):
        invoice, path = _invoice(db_session, comptable_user, tmp_path)
        entry = _entry(db_session, invoice, minimal_chart_of_accounts)
        db_session.add(m.CorrectionModel(entry_id=entry.id, corrected_by=comptable_user.id, field_name="debit",
                                         original_value="1", corrected_value="2"))
        db_session.commit()
        invoice_id, entry_id = invoice.id, entry.id

        assert client.delete(f"/api/invoices/{invoice_id}", headers=auth_headers).status_code == 204

        db_session.expire_all()
        assert db_session.get(m.InvoiceModel, invoice_id) is None
        assert db_session.get(m.JournalEntryModel, entry_id) is None
        assert db_session.query(m.EntryLineModel).filter_by(entry_id=entry_id).count() == 0
        assert db_session.query(m.CorrectionModel).filter_by(entry_id=entry_id).count() == 0
        assert not path.exists()
        assert client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).status_code == 404

    def test_the_deletion_is_audited(self, client, db_session, comptable_user, auth_headers, tmp_path):
        invoice, _ = _invoice(db_session, comptable_user, tmp_path, original_filename="achat.pdf",
                              invoice_number="FAC-9")
        client.delete(f"/api/invoices/{invoice.id}", headers=auth_headers)
        log = db_session.query(m.AuditLogModel).filter_by(action="INVOICE_DELETED", entity_id=invoice.id).one()
        assert log.user_id == comptable_user.id
        assert log.old_value["filename"] == "achat.pdf" and log.old_value["invoice_number"] == "FAC-9"

    @pytest.mark.parametrize("status", ["UPLOADED", "PREPROCESSING", "ERROR", "REJECTED", "ENTRIES_PROPOSED"])
    def test_every_non_validated_status_can_be_deleted(self, client, db_session, comptable_user, auth_headers,
                                                       tmp_path, status):
        # y compris une facture bloquée en cours de traitement (sinon elle serait indélébile)
        invoice, _ = _invoice(db_session, comptable_user, tmp_path, status=status)
        assert client.delete(f"/api/invoices/{invoice.id}", headers=auth_headers).status_code == 204

    def test_a_missing_file_on_disk_does_not_prevent_the_deletion(self, client, db_session, comptable_user,
                                                                  auth_headers, tmp_path):
        invoice, _ = _invoice(db_session, comptable_user, tmp_path, with_file=False)
        assert client.delete(f"/api/invoices/{invoice.id}", headers=auth_headers).status_code == 204

    def test_unknown_invoice_is_a_404(self, client, auth_headers):
        assert client.delete("/api/invoices/424242", headers=auth_headers).status_code == 404

    def test_requires_authentication(self, client):
        assert client.delete("/api/invoices/1").status_code == 401


class TestValidatedInvoiceIsProtected:
    def test_a_validated_invoice_cannot_be_deleted(self, client, db_session, comptable_user, auth_headers,
                                                   minimal_chart_of_accounts, tmp_path):
        invoice, path = _invoice(db_session, comptable_user, tmp_path, status="VALIDATED")
        entry = _entry(db_session, invoice, minimal_chart_of_accounts, status="VALIDATED")
        response = client.delete(f"/api/invoices/{invoice.id}", headers=auth_headers)
        assert response.status_code == 409 and "validée" in response.json()["detail"]
        db_session.expire_all()
        assert db_session.get(m.InvoiceModel, invoice.id) is not None
        assert db_session.get(m.JournalEntryModel, entry.id) is not None
        assert path.exists()

    def test_an_invoice_with_a_validated_entry_is_protected_even_if_its_status_is_stale(
            self, client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts, tmp_path):
        invoice, _ = _invoice(db_session, comptable_user, tmp_path, status="ENTRIES_PROPOSED")
        _entry(db_session, invoice, minimal_chart_of_accounts, status="VALIDATED")
        assert client.delete(f"/api/invoices/{invoice.id}", headers=auth_headers).status_code == 409

    def test_even_the_platform_admin_cannot_delete_a_validated_invoice(
            self, client, db_session, comptable_user, admin_user, minimal_chart_of_accounts, tmp_path):
        invoice, _ = _invoice(db_session, comptable_user, tmp_path, status="VALIDATED")
        headers = _login(client, "admin@test.mg", "Admin1234!")
        assert client.delete(f"/api/invoices/{invoice.id}", headers=headers).status_code == 409


class TestTenantIsolation:
    def test_another_company_cannot_delete_it(self, client, db_session, comptable_user, tmp_path):
        other = m.CompanyModel(name="Autre")
        db_session.add(other)
        db_session.commit()
        db_session.add(m.UserModel(email="o@test.mg", full_name="Autre", role="COMPTABLE", company_id=other.id,
                                   password_hash=hash_password("Other12345!")))
        db_session.commit()
        invoice, path = _invoice(db_session, comptable_user, tmp_path)
        headers = _login(client, "o@test.mg", "Other12345!")
        assert client.delete(f"/api/invoices/{invoice.id}", headers=headers).status_code == 404
        db_session.expire_all()
        assert db_session.get(m.InvoiceModel, invoice.id) is not None and path.exists()

    def test_platform_admin_can_delete_any_unvalidated_invoice(self, client, db_session, comptable_user, admin_user,
                                                               tmp_path):
        invoice, _ = _invoice(db_session, comptable_user, tmp_path)
        headers = _login(client, "admin@test.mg", "Admin1234!")
        assert client.delete(f"/api/invoices/{invoice.id}", headers=headers).status_code == 204


class TestProcessedInvoiceLeavesNothingBehind:
    def test_ocr_entities_classification_and_entries_are_all_removed(self, client, db_session, auth_headers,
                                                                     minimal_chart_of_accounts, tmp_path, monkeypatch):
        class _Classifier:
            def classify(self, text, supplier_name, total):
                return ClassificationResult(OperationType.ACHAT_MARCHANDISES, 0.9, {}, "test")
        monkeypatch.setattr(pipeline_module, "load_active_classifier", lambda: _Classifier())

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        for x, y, text in [(40, 60, "SOCIETE EXEMPLE SAS"), (400, 95, "Facture No: FAC-77"), (400, 110, "Date: 05/10/2026"),
                           (40, 150, "Achat de marchandises destinees a la revente en boutique, merci de votre confiance"),
                           (380, 600, "Total HT"), (500, 600, "1 000,00"), (380, 620, "TVA 20 %"), (500, 620, "200,00"),
                           (380, 640, "Total TTC"), (500, 640, "1 200,00")]:
            pdf.drawString(x, A4[1] - y, text)
        pdf.save()
        response = client.post("/api/invoices", headers=auth_headers,
                               files={"file": ("f.pdf", buffer.getvalue(), "application/pdf")})
        invoice_id = response.json()["id"]
        db_session.expire_all()
        invoice = db_session.get(m.InvoiceModel, invoice_id)
        stored = invoice.storage_path
        assert invoice.status == "ENTRIES_PROPOSED" and db_session.query(m.OcrResultModel).filter_by(invoice_id=invoice_id).count() == 1

        assert client.delete(f"/api/invoices/{invoice_id}", headers=auth_headers).status_code == 204

        db_session.expire_all()
        for model in (m.OcrResultModel, m.ExtractedEntityModel, m.ClassificationModel, m.JournalEntryModel):
            assert db_session.query(model).filter_by(invoice_id=invoice_id).count() == 0, model.__name__
        assert db_session.get(m.InvoiceModel, invoice_id) is None
        assert not __import__("pathlib").Path(stored).exists()


class TestStorageNeverDeletesOutsideItsFolder:
    def test_path_outside_the_storage_directory_is_left_alone(self, tmp_path):
        storage_dir = tmp_path / "storage"
        outside = tmp_path / "precieux.txt"
        outside.write_text("à conserver")
        LocalFileStorage(str(storage_dir)).delete(str(outside))
        assert outside.exists()

    def test_file_inside_the_storage_directory_is_deleted(self, tmp_path):
        storage = LocalFileStorage(str(tmp_path / "storage"))
        stored = storage.save(b"x", "a.pdf")
        storage.delete(stored)
        assert not __import__("pathlib").Path(stored).exists()
