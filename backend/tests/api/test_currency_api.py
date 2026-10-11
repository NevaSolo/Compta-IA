"""Devise de l'entreprise, taux de change et conversion des factures en devise
étrangère (écriture dans la devise de l'entreprise, origine conservée)."""
import io
from datetime import date
from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application import pipeline as pipeline_module
from app.core.config import get_settings
from app.core.currency import convert_amounts
from app.core.security import hash_password
from app.domain.entities import OperationType
from app.domain.ports import ClassificationResult
from app.infrastructure.db.models import (
    CompanyModel, EntryLineModel, ExchangeRateModel, InvoiceModel, JournalEntryModel, UserModel,
)


def _login(client, email, password):
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def boss_headers(client, db_session, company):
    db_session.add(UserModel(email="boss@test.mg", full_name="Chef", role="ENTREPRISE_ADMIN",
                             company_id=company.id, password_hash=hash_password("Boss12345!")))
    db_session.commit()
    return _login(client, "boss@test.mg", "Boss12345!")


@pytest.fixture()
def other_boss_headers(client, db_session):
    other = CompanyModel(name="Autre Société")
    db_session.add(other)
    db_session.commit()
    db_session.add(UserModel(email="other@test.mg", full_name="Autre", role="ENTREPRISE_ADMIN",
                             company_id=other.id, password_hash=hash_password("Other12345!")))
    db_session.commit()
    return _login(client, "other@test.mg", "Other12345!")


class TestConvertAmounts:
    def test_converts_and_keeps_ht_plus_vat_equal_to_ttc(self):
        ht, vat, ttc = convert_amounts(Decimal("100.00"), Decimal("20.00"), Decimal("120.00"), Decimal("4950"))
        assert (ht, vat, ttc) == (Decimal("495000.00"), Decimal("99000.00"), Decimal("594000.00"))

    def test_rounding_cent_goes_to_the_vat_so_the_entry_stays_balanced(self):
        # 33,33 × 1,2345 = 41,1458 → 41,15 ; 6,67 × 1,2345 = 8,2341 → 8,23 ; 40,00 × 1,2345 = 49,38
        ht, vat, ttc = convert_amounts(Decimal("33.33"), Decimal("6.67"), Decimal("40.00"), Decimal("1.2345"))
        assert ht + vat == ttc == Decimal("49.38")

    def test_a_real_inconsistency_is_not_hidden_by_the_rounding_fix(self):
        ht, vat, ttc = convert_amounts(Decimal("100"), Decimal("5"), Decimal("120"), Decimal("2"))
        assert vat == Decimal("10.00") and ht + vat != ttc  # TVA lue ≠ TTC − HT : on ne la « corrige » pas

    def test_missing_amounts_stay_missing(self):
        assert convert_amounts(None, None, Decimal("10"), Decimal("2")) == (None, None, Decimal("20.00"))


class TestCompanyCurrency:
    def test_default_is_mga_and_exposed_on_the_profile(self, client, auth_headers):
        assert client.get("/api/auth/me", headers=auth_headers).json()["company_currency"] == "MGA"

    def test_company_admin_changes_currency(self, client, boss_headers, auth_headers, company):
        response = client.patch(f"/api/companies/{company.id}/currency", headers=boss_headers,
                                json={"base_currency": "EUR"})
        assert response.status_code == 200 and response.json()["base_currency"] == "EUR"
        assert client.get("/api/auth/me", headers=auth_headers).json()["company_currency"] == "EUR"

    def test_unsupported_currency_is_rejected(self, client, boss_headers, company):
        assert client.patch(f"/api/companies/{company.id}/currency", headers=boss_headers,
                            json={"base_currency": "XXX"}).status_code == 422

    def test_accountant_and_other_company_cannot_change_it(
            self, client, auth_headers, other_boss_headers, company):
        assert client.patch(f"/api/companies/{company.id}/currency", headers=auth_headers,
                            json={"base_currency": "EUR"}).status_code == 403
        assert client.patch(f"/api/companies/{company.id}/currency", headers=other_boss_headers,
                            json={"base_currency": "EUR"}).status_code == 404

    def test_currency_is_locked_once_entries_are_validated(
            self, client, db_session, boss_headers, comptable_user, company):
        invoice = InvoiceModel(company_id=company.id, uploaded_by=comptable_user.id,
                               original_filename="f.pdf", storage_path="/tmp/f", mime_type="application/pdf",
                               file_size=1, status="VALIDATED")
        db_session.add(invoice)
        db_session.flush()
        db_session.add(JournalEntryModel(invoice_id=invoice.id, company_id=company.id,
                                         entry_date=date(2026, 1, 1), label="x", status="VALIDATED"))
        db_session.commit()
        response = client.patch(f"/api/companies/{company.id}/currency", headers=boss_headers,
                                json={"base_currency": "EUR"})
        assert response.status_code == 409 and "validées" in response.json()["detail"]
        # re-sélectionner la devise actuelle reste permis
        assert client.patch(f"/api/companies/{company.id}/currency", headers=boss_headers,
                            json={"base_currency": "MGA"}).status_code == 200


class TestExchangeRates:
    def _add(self, client, headers, company, **fields):
        payload = {"currency": "EUR", "rate": "4950", "effective_date": "2026-10-01", **fields}
        return client.post(f"/api/companies/{company.id}/rates", headers=headers, json=payload)

    def test_add_list_replace_delete(self, client, boss_headers, auth_headers, company):
        assert self._add(client, boss_headers, company).status_code == 201
        assert self._add(client, boss_headers, company, rate="5000").status_code == 201  # même date : remplace
        rates = client.get(f"/api/companies/{company.id}/rates", headers=auth_headers).json()  # un comptable lit
        assert len(rates) == 1 and Decimal(rates[0]["rate"]) == Decimal("5000")
        assert client.delete(f"/api/companies/{company.id}/rates/{rates[0]['id']}",
                             headers=boss_headers).status_code == 204
        assert client.get(f"/api/companies/{company.id}/rates", headers=auth_headers).json() == []

    @pytest.mark.parametrize("fields", [{"rate": "0"}, {"rate": "-3"}, {"currency": "ABC"}])
    def test_invalid_rates_are_rejected(self, client, boss_headers, company, fields):
        assert self._add(client, boss_headers, company, **fields).status_code == 422

    def test_no_rate_for_the_base_currency_itself(self, client, boss_headers, company):
        assert self._add(client, boss_headers, company, currency="MGA").status_code == 422

    def test_accountant_cannot_write_and_other_company_cannot_read(
            self, client, auth_headers, other_boss_headers, company):
        assert self._add(client, auth_headers, company).status_code == 403
        assert client.get(f"/api/companies/{company.id}/rates", headers=other_boss_headers).status_code == 404


class TestInvoiceExchangeRate:
    def _invoice(self, db, user, **fields):
        row = InvoiceModel(**{**dict(company_id=user.company_id, uploaded_by=user.id, original_filename="f.pdf",
                                     storage_path="/tmp/f", mime_type="application/pdf", file_size=1,
                                     status="ERROR", currency="EUR", invoice_date=date(2026, 10, 5)), **fields})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_sets_the_rate(self, client, db_session, comptable_user, auth_headers):
        invoice = self._invoice(db_session, comptable_user)
        response = client.put(f"/api/invoices/{invoice.id}/exchange-rate", headers=auth_headers,
                              json={"rate": "4900.5"})
        assert response.status_code == 200 and Decimal(response.json()["exchange_rate"]) == Decimal("4900.5")

    def test_only_an_admin_can_save_it_for_the_company(
            self, client, db_session, comptable_user, auth_headers, boss_headers, company):
        invoice = self._invoice(db_session, comptable_user)
        client.put(f"/api/invoices/{invoice.id}/exchange-rate", headers=auth_headers,
                   json={"rate": "4900", "save_for_company": True})
        assert db_session.query(ExchangeRateModel).count() == 0  # un comptable ne paramètre pas l'entreprise
        client.put(f"/api/invoices/{invoice.id}/exchange-rate", headers=boss_headers,
                   json={"rate": "4900", "save_for_company": True})
        saved = db_session.query(ExchangeRateModel).one()
        assert (saved.currency, saved.effective_date) == ("EUR", date(2026, 10, 5))

    def test_refused_for_base_currency_or_validated_invoice(self, client, db_session, comptable_user, auth_headers):
        assert client.put(f"/api/invoices/{self._invoice(db_session, comptable_user, currency='MGA').id}/exchange-rate",
                          headers=auth_headers, json={"rate": "2"}).status_code == 422
        validated = self._invoice(db_session, comptable_user, status="VALIDATED")
        assert client.put(f"/api/invoices/{validated.id}/exchange-rate", headers=auth_headers,
                          json={"rate": "2"}).status_code == 409


# ------------------------------------------------ Pipeline de bout en bout
def _eur_invoice_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    lines = [
        (40, 60, "HELIOS DIGITAL SAS", 16), (400, 60, "FACTURE", 14),
        (400, 95, "Facture No: FAC-EUR-001"), (400, 110, "Date: 05/10/2026"),
        (40, 150, "Prestation de conseil en strategie numerique pour le client, mission du mois d'octobre"),
        (40, 170, "Accompagnement, formation des equipes et livrables associes a la mission convenue"),
        (380, 600, "Total HT"), (500, 600, "1 000,00 EUR"),
        (380, 620, "TVA 20 %"), (500, 620, "200,00 EUR"),
        (380, 640, "Total TTC"), (500, 640, "1 200,00 EUR"),
    ]
    for item in lines:
        x, y, text = item[:3]
        pdf.setFont("Helvetica", item[3] if len(item) > 3 else 10)
        pdf.drawString(x, height - y, text)
    pdf.save()
    return buffer.getvalue()


class _FakeClassifier:
    def classify(self, text, supplier_name, total):
        return ClassificationResult(OperationType.ACHAT_MARCHANDISES, 0.9, {}, "test")


@pytest.fixture()
def pipeline_env(tmp_path, monkeypatch, minimal_chart_of_accounts):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    monkeypatch.setattr(pipeline_module, "load_active_classifier", lambda: _FakeClassifier())


def _upload(client, headers):
    response = client.post("/api/invoices", headers=headers,
                           files={"file": ("eur.pdf", _eur_invoice_pdf(), "application/pdf")})
    assert response.status_code == 202
    return response.json()["id"]


def _entry_of(client, headers, invoice_id):
    entries = client.get(f"/api/entries/by-invoice/{invoice_id}", headers=headers).json()
    return entries[0] if entries else None


class TestPipelineConversion:
    def test_missing_rate_stops_with_an_actionable_error(self, client, auth_headers, pipeline_env):
        invoice = client.get(f"/api/invoices/{_upload(client, auth_headers)}", headers=auth_headers).json()
        assert invoice["currency"] == "EUR" and invoice["status"] == "ERROR"
        assert "Taux de change EUR → MGA manquant" in invoice["error_message"]

    def test_company_rate_converts_the_entry_and_keeps_the_origin(
            self, client, db_session, auth_headers, boss_headers, company, pipeline_env):
        client.post(f"/api/companies/{company.id}/rates", headers=boss_headers,
                    json={"currency": "EUR", "rate": "4950", "effective_date": "2026-09-30"})
        invoice_id = _upload(client, auth_headers)
        invoice = client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).json()
        assert invoice["status"] == "ENTRIES_PROPOSED" and Decimal(invoice["exchange_rate"]) == Decimal("4950")
        entry = _entry_of(client, auth_headers, invoice_id)
        assert entry["currency"] == "MGA" and entry["original_currency"] == "EUR"
        assert Decimal(entry["original_amount"]) == Decimal("1200") and Decimal(entry["exchange_rate"]) == Decimal("4950")
        assert Decimal(entry["total_debit"]) == Decimal(entry["total_credit"]) == Decimal("5940000")  # 1 200 × 4 950
        by_account = {l["account_code"]: Decimal(l["debit"] or 0) + Decimal(l["credit"] or 0) for l in entry["lines"]}
        assert by_account == {"607": Decimal("4950000"), "4456": Decimal("990000"), "401": Decimal("5940000")}

    def test_a_later_rate_is_used_when_no_earlier_one_exists(
            self, client, auth_headers, boss_headers, company, pipeline_env):
        # Taux saisi « aujourd'hui » pour une facture plus ancienne : à défaut de taux
        # antérieur, on prend le plus proche au lieu de bloquer le traitement.
        client.post(f"/api/companies/{company.id}/rates", headers=boss_headers,
                    json={"currency": "EUR", "rate": "5100", "effective_date": "2026-12-01"})
        invoice = client.get(f"/api/invoices/{_upload(client, auth_headers)}", headers=auth_headers).json()
        assert invoice["status"] == "ENTRIES_PROPOSED" and Decimal(invoice["exchange_rate"]) == Decimal("5100")

    def test_an_earlier_rate_wins_over_a_later_one(
            self, client, auth_headers, boss_headers, company, pipeline_env):
        for date_, rate in (("2026-09-01", "4900"), ("2026-12-01", "5100")):
            client.post(f"/api/companies/{company.id}/rates", headers=boss_headers,
                        json={"currency": "EUR", "rate": rate, "effective_date": date_})
        invoice = client.get(f"/api/invoices/{_upload(client, auth_headers)}", headers=auth_headers).json()
        assert Decimal(invoice["exchange_rate"]) == Decimal("4900")  # facture du 05/10/2026

    def test_the_nearest_later_rate_is_chosen(
            self, client, auth_headers, boss_headers, company, pipeline_env):
        for date_, rate in (("2027-03-01", "5300"), ("2026-12-01", "5100")):
            client.post(f"/api/companies/{company.id}/rates", headers=boss_headers,
                        json={"currency": "EUR", "rate": rate, "effective_date": date_})
        invoice = client.get(f"/api/invoices/{_upload(client, auth_headers)}", headers=auth_headers).json()
        assert Decimal(invoice["exchange_rate"]) == Decimal("5100")

    def test_rate_entered_on_the_invoice_then_reprocess(self, client, auth_headers, pipeline_env):
        invoice_id = _upload(client, auth_headers)
        assert client.put(f"/api/invoices/{invoice_id}/exchange-rate", headers=auth_headers,
                          json={"rate": "4800"}).status_code == 200
        assert client.post(f"/api/invoices/{invoice_id}/reprocess", headers=auth_headers).status_code == 202
        entry = _entry_of(client, auth_headers, invoice_id)
        assert Decimal(entry["total_debit"]) == Decimal("5760000")  # 1 200 × 4 800

    def test_reprocessing_replaces_the_proposal_instead_of_duplicating_it(self, client, auth_headers, pipeline_env):
        invoice_id = _upload(client, auth_headers)
        client.put(f"/api/invoices/{invoice_id}/exchange-rate", headers=auth_headers, json={"rate": "4800"})
        for _ in range(2):  # deux relances successives
            assert client.post(f"/api/invoices/{invoice_id}/reprocess", headers=auth_headers).status_code == 202
        entries = client.get(f"/api/entries/by-invoice/{invoice_id}", headers=auth_headers).json()
        assert len(entries) == 1
        assert client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).json()["status"] == "ENTRIES_PROPOSED"

    def test_a_validated_invoice_cannot_be_reprocessed(self, client, auth_headers, pipeline_env):
        invoice_id = _upload(client, auth_headers)
        client.put(f"/api/invoices/{invoice_id}/exchange-rate", headers=auth_headers, json={"rate": "4800"})
        client.post(f"/api/invoices/{invoice_id}/reprocess", headers=auth_headers)
        entry = _entry_of(client, auth_headers, invoice_id)
        client.post(f"/api/entries/{entry['id']}/validate", headers=auth_headers)
        assert client.post(f"/api/invoices/{invoice_id}/reprocess", headers=auth_headers).status_code == 409

    def test_company_in_eur_needs_no_rate_for_an_eur_invoice(
            self, client, db_session, auth_headers, boss_headers, company, pipeline_env):
        client.patch(f"/api/companies/{company.id}/currency", headers=boss_headers, json={"base_currency": "EUR"})
        invoice_id = _upload(client, auth_headers)
        entry = _entry_of(client, auth_headers, invoice_id)
        assert entry["currency"] == "EUR" and entry["original_currency"] is None
        assert Decimal(entry["total_debit"]) == Decimal("1200")

    def test_exports_show_currency_and_origin(self, client, db_session, auth_headers, boss_headers, company,
                                              pipeline_env):
        client.post(f"/api/companies/{company.id}/rates", headers=boss_headers,
                    json={"currency": "EUR", "rate": "4950", "effective_date": "2026-09-30"})
        entry = _entry_of(client, auth_headers, _upload(client, auth_headers))
        assert client.post(f"/api/entries/{entry['id']}/validate", headers=auth_headers).status_code == 200
        csv_text = client.get("/api/entries/export/csv", headers=auth_headers).content.decode("utf-8-sig")
        header, first = csv_text.splitlines()[:2]
        assert header.endswith("Devise;Montant d'origine;Devise d'origine;Taux")
        assert first.split(";")[-4:] == ["MGA", "1200.0", "EUR", "4950.0"]
        assert client.get("/api/entries/export/pdf", headers=auth_headers).status_code == 200
