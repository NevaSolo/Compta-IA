"""Recherche/filtres de l'historique, détection de doublons et validation en lot."""
from datetime import date
from decimal import Decimal

from app.infrastructure.db.models import (
    EntryLineModel, InvoiceModel, JournalEntryModel, SupplierModel,
)


def _invoice(db, user, **fields):
    defaults = dict(company_id=user.company_id, uploaded_by=user.id, original_filename="f.pdf",
                    storage_path="/tmp/f.pdf", mime_type="application/pdf", file_size=10,
                    status="ENTRIES_PROPOSED")
    row = InvoiceModel(**{**defaults, **fields})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _supplier(db, user, name):
    row = SupplierModel(company_id=user.company_id, name=name, normalized_name=name.lower())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestSearchAndFilters:
    def _seed(self, db, user):
        helios = _supplier(db, user, "Helios Conseil")
        nova = _supplier(db, user, "Studio Nova")
        _invoice(db, user, original_filename="a.pdf", supplier_id=helios.id, invoice_number="FAC-001",
                 invoice_date=date(2026, 1, 10), total_ttc=Decimal("100.00"))
        _invoice(db, user, original_filename="b.pdf", supplier_id=nova.id, invoice_number="2026-77",
                 invoice_date=date(2026, 3, 5), total_ttc=Decimal("5000.00"))

    def _names(self, client, headers, **params):
        response = client.get("/api/invoices", headers=headers, params=params)
        assert response.status_code == 200
        return sorted(i["original_filename"] for i in response.json()["items"])

    def test_search_by_supplier_number_and_filename(self, client, db_session, comptable_user, auth_headers):
        self._seed(db_session, comptable_user)
        assert self._names(client, auth_headers, q="helios") == ["a.pdf"]
        assert self._names(client, auth_headers, q="2026-77") == ["b.pdf"]
        assert self._names(client, auth_headers, q="b.pdf") == ["b.pdf"]
        assert self._names(client, auth_headers, q="introuvable") == []

    def test_percent_in_search_is_literal(self, client, db_session, comptable_user, auth_headers):
        self._seed(db_session, comptable_user)
        assert self._names(client, auth_headers, q="%") == []

    def test_date_and_amount_filters(self, client, db_session, comptable_user, auth_headers):
        self._seed(db_session, comptable_user)
        assert self._names(client, auth_headers, date_from="2026-02-01") == ["b.pdf"]
        assert self._names(client, auth_headers, date_to="2026-02-01") == ["a.pdf"]
        assert self._names(client, auth_headers, min_amount="1000") == ["b.pdf"]
        assert self._names(client, auth_headers, max_amount="1000") == ["a.pdf"]

    def test_total_counts_filtered_rows(self, client, db_session, comptable_user, auth_headers):
        self._seed(db_session, comptable_user)
        body = client.get("/api/invoices", headers=auth_headers, params={"q": "nova"}).json()
        assert body["total"] == 1


class TestDuplicateDetection:
    def _flag(self, client, headers, invoice):
        return client.get(f"/api/invoices/{invoice.id}", headers=headers).json()["duplicate_of"]

    def test_same_number_and_amount_flags_the_later_invoice_only(
            self, client, db_session, comptable_user, auth_headers):
        first = _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        second = _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        assert self._flag(client, auth_headers, first) is None
        assert self._flag(client, auth_headers, second) == first.id

    def test_same_supplier_and_date_without_number(self, client, db_session, comptable_user, auth_headers):
        supplier = _supplier(db_session, comptable_user, "Claire Moreau")
        fields = dict(supplier_id=supplier.id, invoice_date=date(2026, 2, 2), total_ttc=Decimal("920.00"))
        first = _invoice(db_session, comptable_user, **fields)
        second = _invoice(db_session, comptable_user, **fields)
        assert self._flag(client, auth_headers, second) == first.id

    def test_different_amount_is_not_a_duplicate(self, client, db_session, comptable_user, auth_headers):
        _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        other = _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("121.00"))
        assert self._flag(client, auth_headers, other) is None

    def test_rejected_original_is_ignored(self, client, db_session, comptable_user, auth_headers):
        _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"),
                 status="REJECTED")
        again = _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        assert self._flag(client, auth_headers, again) is None

    def test_missing_identifiers_never_match(self, client, db_session, comptable_user, auth_headers):
        _invoice(db_session, comptable_user, total_ttc=Decimal("120.00"))
        other = _invoice(db_session, comptable_user, total_ttc=Decimal("120.00"))
        assert self._flag(client, auth_headers, other) is None

    def test_list_exposes_duplicate_flag(self, client, db_session, comptable_user, auth_headers):
        first = _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        _invoice(db_session, comptable_user, invoice_number="FAC-9", total_ttc=Decimal("120.00"))
        items = client.get("/api/invoices", headers=auth_headers).json()["items"]
        assert [i["duplicate_of"] for i in items] == [first.id, None]  # id décroissant


class TestBatchValidation:
    def _entry(self, db, user, accounts, credit=120):
        by_code = {a.code: a for a in accounts}
        invoice = _invoice(db, user)
        entry = JournalEntryModel(invoice_id=invoice.id, company_id=user.company_id,
                                  entry_date=date(2026, 1, 15), label="Facture", status="PROPOSED",
                                  confidence_score=0.9)
        entry.lines = [
            EntryLineModel(account_id=by_code["607"].id, label="Achat", debit=100, credit=0, line_order=0),
            EntryLineModel(account_id=by_code["4456"].id, label="TVA", debit=20, credit=0, line_order=1),
            EntryLineModel(account_id=by_code["401"].id, label="Fournisseur", debit=0, credit=credit,
                           line_order=2),
        ]
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def test_validates_each_entry_and_reports_failures(
            self, client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts):
        good = self._entry(db_session, comptable_user, minimal_chart_of_accounts)
        unbalanced = self._entry(db_session, comptable_user, minimal_chart_of_accounts, credit=999)
        response = client.post("/api/entries/validate-batch", headers=auth_headers,
                               json={"entry_ids": [good.id, unbalanced.id, 424242]})
        assert response.status_code == 200
        body = response.json()
        assert (body["validated"], body["failed"]) == (1, 2)
        by_id = {r["id"]: r for r in body["results"]}
        assert by_id[good.id]["ok"] is True
        assert by_id[unbalanced.id]["ok"] is False
        assert by_id[424242]["error"] == "Écriture introuvable"
        assert client.get(f"/api/entries/{good.id}", headers=auth_headers).json()["status"] == "VALIDATED"
        assert client.get(f"/api/entries/{unbalanced.id}", headers=auth_headers).json()["status"] == "PROPOSED"

    def test_already_validated_entry_is_reported_not_crashing(
            self, client, db_session, comptable_user, auth_headers, minimal_chart_of_accounts):
        entry = self._entry(db_session, comptable_user, minimal_chart_of_accounts)
        client.post(f"/api/entries/{entry.id}/validate", headers=auth_headers)
        body = client.post("/api/entries/validate-batch", headers=auth_headers,
                           json={"entry_ids": [entry.id, entry.id]}).json()
        assert len(body["results"]) == 1 and body["failed"] == 1  # id répété compté une fois

    def test_empty_list_is_rejected(self, client, auth_headers):
        assert client.post("/api/entries/validate-batch", headers=auth_headers,
                           json={"entry_ids": []}).status_code == 422
