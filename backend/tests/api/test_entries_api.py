"""Tests d'intégration de la validation/correction d'écritures — le cœur
du contrôle métier exposé par l'API (équilibre re-vérifié, historisation
des corrections pour le réentraînement)."""
from datetime import date

from app.infrastructure.db.models import (
    InvoiceModel, JournalEntryModel, EntryLineModel,
)


def _create_proposed_entry(db_session, comptable_user, accounts):
    by_code = {a.code: a for a in accounts}
    invoice = InvoiceModel(company_id=comptable_user.company_id, uploaded_by=comptable_user.id,
                           original_filename="f.pdf",
                           storage_path="/tmp/f.pdf", mime_type="application/pdf",
                           file_size=10, status="ENTRIES_PROPOSED")
    db_session.add(invoice)
    db_session.flush()

    entry = JournalEntryModel(invoice_id=invoice.id, company_id=comptable_user.company_id,
                              entry_date=date(2026, 1, 15),
                              label="Facture test", status="PROPOSED",
                              confidence_score=0.62)
    entry.lines = [
        EntryLineModel(account_id=by_code["607"].id, label="Achat",
                      debit=100, credit=0, line_order=0),
        EntryLineModel(account_id=by_code["4456"].id, label="TVA",
                      debit=20, credit=0, line_order=1),
        EntryLineModel(account_id=by_code["401"].id, label="Fournisseur",
                      debit=0, credit=120, line_order=2),
    ]
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_validate_balanced_entry_succeeds(client, db_session, comptable_user,
                                          auth_headers, minimal_chart_of_accounts):
    entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
    response = client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "VALIDATED"


def test_cannot_correct_already_validated_entry(client, db_session, comptable_user,
                                                auth_headers, minimal_chart_of_accounts):
    entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
    client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)

    line_id = entry.lines[0].id
    response = client.put(f"/api/entries/{entry.id}", headers=auth_headers, json={
        "corrections": [{"line_id": line_id, "field": "debit", "new_value": "150"}]})
    assert response.status_code == 422
    assert "intangibilité" in response.json()["detail"].lower() or \
           "déjà validée" in response.json()["detail"].lower()


def test_correction_breaking_balance_is_rejected(client, db_session, comptable_user,
                                                 auth_headers, minimal_chart_of_accounts):
    entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
    line_id = entry.lines[0].id  # ligne débit 100 -> on la monte à 500 sans ajuster le reste
    response = client.put(f"/api/entries/{entry.id}", headers=auth_headers, json={
        "corrections": [{"line_id": line_id, "field": "debit", "new_value": "500"}]})
    assert response.status_code == 422


def test_correction_is_historized_for_ml_training(client, db_session, comptable_user,
                                                  auth_headers, minimal_chart_of_accounts):
    """La correction d'un compte doit rester équilibrée (même montant) et
    être historisée dans `corrections` — matière première du réentraînement."""
    entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
    line_id = entry.lines[0].id
    response = client.put(f"/api/entries/{entry.id}", headers=auth_headers, json={
        "corrections": [{"line_id": line_id, "field": "label",
                         "new_value": "Achat corrigé par le comptable"}]})
    assert response.status_code == 200
    assert response.json()["status"] == "CORRECTED"

    from app.infrastructure.db.models import CorrectionModel
    corrections = db_session.query(CorrectionModel).filter_by(entry_id=entry.id).all()
    assert len(corrections) == 1
    assert corrections[0].field_name == "label"
    assert corrections[0].used_for_training is False


def test_get_entry_not_found(client, auth_headers):
    assert client.get("/api/entries/9999", headers=auth_headers).status_code == 404


class TestExports:
    """Exports Excel/CSV/PDF du journal des écritures validées."""

    def test_export_excel_returns_valid_workbook(self, client, db_session, comptable_user,
                                                  auth_headers, minimal_chart_of_accounts):
        entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
        client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)

        response = client.get("/api/entries/export/excel", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert len(response.content) > 0

    def test_export_csv_contains_validated_entry_and_accented_labels(
            self, client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts):
        entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
        client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)

        response = client.get("/api/entries/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        text = response.content.decode("utf-8-sig")  # tolère le BOM ajouté pour Excel
        assert "Fournisseur" in text
        assert str(entry.id) in text

    def test_export_pdf_returns_valid_pdf_document(
            self, client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts):
        entry = _create_proposed_entry(db_session, comptable_user, minimal_chart_of_accounts)
        client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)

        response = client.get("/api/entries/export/pdf", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_export_pdf_with_no_validated_entries_still_succeeds(self, client, auth_headers):
        """Aucune écriture validée : le PDF doit rester généré sans planter,
        avec un message plutôt qu'un tableau vide."""
        response = client.get("/api/entries/export/pdf", headers=auth_headers)
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")

    def test_exports_require_authentication(self, client):
        for fmt in ("excel", "csv", "pdf"):
            response = client.get(f"/api/entries/export/{fmt}")
            assert response.status_code == 401
