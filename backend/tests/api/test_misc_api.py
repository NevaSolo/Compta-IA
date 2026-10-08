"""Tests d'intégration des routes transverses — ici le tableau de bord,
en particulier ses agrégats utilisés pour les graphiques du front
(répartition par type d'opération, volume mensuel)."""
from datetime import date

from app.infrastructure.db.models import (
    ClassificationModel, InvoiceModel, JournalEntryModel, EntryLineModel, ModelVersionModel,
    OcrResultModel,
)


def _get_or_create_model_version(db_session) -> int:
    version = db_session.query(ModelVersionModel).first()
    if version:
        return version.id
    version = ModelVersionModel(name="operation_classifier", version="keyword-0.1.0",
                                algorithm="keyword", artifact_path="builtin", is_active=True)
    db_session.add(version)
    db_session.flush()
    return version.id


def _create_classified_invoice(db_session, comptable_user, accounts, operation_type, total_ttc):
    by_code = {a.code: a for a in accounts}
    invoice = InvoiceModel(company_id=comptable_user.company_id, uploaded_by=comptable_user.id,
                           original_filename="f.pdf",
                           storage_path="/tmp/f.pdf", mime_type="application/pdf",
                           file_size=10, status="ENTRIES_PROPOSED", total_ttc=total_ttc)
    db_session.add(invoice)
    db_session.flush()

    db_session.add(OcrResultModel(invoice_id=invoice.id, engine="EASYOCR", raw_text="x",
                                  mean_confidence=0.9, blocks=[], duration_ms=10))
    db_session.add(ClassificationModel(invoice_id=invoice.id, operation_type=operation_type,
                                       probability=0.8,
                                       model_version_id=_get_or_create_model_version(db_session)))
    entry = JournalEntryModel(invoice_id=invoice.id, company_id=comptable_user.company_id,
                              entry_date=date(2026, 1, 15),
                              label="Facture test", status="PROPOSED", confidence_score=0.62)
    entry.lines = [
        EntryLineModel(account_id=by_code["607"].id, label="Achat",
                      debit=100, credit=0, line_order=0),
        EntryLineModel(account_id=by_code["401"].id, label="Fournisseur",
                      debit=0, credit=100, line_order=1),
    ]
    db_session.add(entry)
    db_session.commit()
    return invoice


def test_dashboard_returns_operation_breakdown_and_monthly_volume(
        client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts):
    _create_classified_invoice(db_session, comptable_user, minimal_chart_of_accounts,
                               "ACHAT_MARCHANDISES", 120)
    _create_classified_invoice(db_session, comptable_user, minimal_chart_of_accounts,
                               "ACHAT_SERVICES", 50)

    response = client.get("/api/dashboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["operations_by_type"]["ACHAT_MARCHANDISES"] == 1
    assert body["operations_by_type"]["ACHAT_SERVICES"] == 1
    assert len(body["monthly_volume"]) >= 1
    latest = body["monthly_volume"][-1]
    assert latest["invoice_count"] == 2
    assert latest["total_ttc"] == 170.0


def test_dashboard_with_no_invoices_returns_empty_breakdowns(client, auth_headers):
    response = client.get("/api/dashboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["operations_by_type"] == {}
    assert body["monthly_volume"] == []


class TestAuditLog:
    """Journal d'audit (Admin) — enrichi du nom de l'auteur pour être
    lisible dans l'interface plutôt qu'un simple user_id numérique."""

    def _admin_headers(self, client):
        login = client.post("/api/auth/login", json={
            "email": "admin@test.mg", "password": "Admin1234!"})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    def test_comptable_cannot_access_audit_log(self, client, auth_headers):
        assert client.get("/api/audit", headers=auth_headers).status_code == 403

    def test_admin_sees_audit_entries_with_user_name(
            self, client, db_session, admin_user, comptable_user,
            auth_headers, minimal_chart_of_accounts):
        # Une action tracée : upload d'une facture par le comptable.
        client.post("/api/invoices", headers=auth_headers,
                   files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")})

        headers = self._admin_headers(client)
        response = client.get("/api/audit", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        entry = next(i for i in body["items"] if i["action"] == "INVOICE_UPLOADED")
        assert entry["user_name"] == "Comptable Test"
