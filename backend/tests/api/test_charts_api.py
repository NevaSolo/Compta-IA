"""Plans comptables : catalogue (PCG français), choix obligatoire par entreprise,
isolation des comptes entre plans, génération d'écritures dans le plan choisi."""
import io
from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application import pipeline as pipeline_module
from app.catalog import installer, pcg_fr
from app.core.config import get_settings
from app.core.security import hash_password
from app.domain.entities import OperationType
from app.domain.ports import ClassificationResult
from app.infrastructure.db.models import (
    AccountModel, ChartModel, CompanyModel, EntryLineModel, InvoiceModel, JournalEntryModel, UserModel,
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
def fr_chart(db_session):
    installer.install_catalog(db_session)
    return db_session.query(ChartModel).filter_by(code="PCG_FR_2014").one()


class TestCatalogIntegrity:
    def test_french_chart_is_consistent(self):
        accounts = pcg_fr.accounts()
        codes = [a["code"] for a in accounts]
        assert len(codes) == len(set(codes)) and len(codes) > 200
        assert {a["account_class"] for a in accounts} == {1, 2, 3, 4, 5, 6, 7}
        assert all(a["parent_code"] in codes for a in accounts if a["parent_code"])

    def test_every_rule_account_exists_in_the_chart(self):
        codes = {a["code"] for a in pcg_fr.accounts()}
        for rule in pcg_fr.RULES:
            for line in rule["template"]["lines"]:
                assert line["default_account"] in codes, (rule["code"], line["default_account"])
                for candidate in line.get("candidates", []):
                    assert candidate in codes, (rule["code"], candidate)
                if line.get("candidates"):  # le défaut fait partie des candidats
                    assert line["default_account"] in line["candidates"]

    def test_french_vat_accounts_and_normal_balances(self):
        by_code = {a["code"]: a for a in pcg_fr.accounts()}
        assert by_code["44566"]["normal_balance"] == "DEBIT" and by_code["44562"]["normal_balance"] == "DEBIT"
        assert by_code["401"]["normal_balance"] == "CREDIT" and by_code["607"]["normal_balance"] == "DEBIT"
        assert by_code["512"]["normal_balance"] == "DEBIT" and by_code["706"]["normal_balance"] == "CREDIT"

    def test_rules_cover_every_operation_type_used_by_the_classifier(self):
        assert {r["operation_type"] for r in pcg_fr.RULES} >= {
            "ACHAT_MARCHANDISES", "ACHAT_SERVICES", "ACHAT_IMMOBILISATION"}

    def test_install_is_idempotent_and_completes_missing_accounts(self, db_session):
        first = installer.install_catalog(db_session)["PCG_FR_2014"]
        assert first["chart_created"] == 1 and first["accounts_added"] > 200 and first["rules_added"] == 3
        assert installer.install_catalog(db_session)["PCG_FR_2014"] == {
            "chart_created": 0, "accounts_added": 0, "rules_added": 0}
        chart = db_session.query(ChartModel).filter_by(code="PCG_FR_2014").one()
        db_session.query(AccountModel).filter_by(chart_id=chart.id, code="6226").delete()
        db_session.commit()
        assert installer.install_catalog(db_session)["PCG_FR_2014"]["accounts_added"] == 1


class TestChartChoice:
    def test_lists_available_charts(self, client, auth_headers, fr_chart, chart):
        charts = {c["code"]: c for c in client.get("/api/charts", headers=auth_headers).json()}
        assert charts["PCG_FR_2014"]["accounts_count"] > 200 and charts["PCG_FR_2014"]["country"] == "FR"
        assert "PCG_TEST" in charts

    def test_company_admin_chooses_then_profile_shows_it(self, client, db_session, boss_headers, auth_headers,
                                                          company, fr_chart):
        assert client.put(f"/api/companies/{company.id}/chart", headers=boss_headers,
                          json={"chart_id": fr_chart.id}).status_code == 200
        me = client.get("/api/auth/me", headers=auth_headers).json()
        assert me["company_chart_id"] == fr_chart.id and me["company_chart_name"] == fr_chart.name

    def test_unknown_chart_and_accountant_are_refused(self, client, boss_headers, auth_headers, company, fr_chart):
        assert client.put(f"/api/companies/{company.id}/chart", headers=boss_headers,
                          json={"chart_id": 99999}).status_code == 404
        assert client.put(f"/api/companies/{company.id}/chart", headers=auth_headers,
                          json={"chart_id": fr_chart.id}).status_code == 403

    def test_cannot_change_chart_once_entries_exist(self, client, db_session, boss_headers, company,
                                                    comptable_user, fr_chart):
        invoice = InvoiceModel(company_id=company.id, uploaded_by=comptable_user.id, original_filename="f.pdf",
                               storage_path="/tmp/f", mime_type="application/pdf", file_size=1, status="ENTRIES_PROPOSED")
        db_session.add(invoice)
        db_session.flush()
        db_session.add(JournalEntryModel(invoice_id=invoice.id, company_id=company.id,
                                         entry_date=__import__("datetime").date(2026, 1, 1), label="x"))
        db_session.commit()
        response = client.put(f"/api/companies/{company.id}/chart", headers=boss_headers,
                              json={"chart_id": fr_chart.id})
        assert response.status_code == 409 and "écritures" in response.json()["detail"]

    def test_company_without_chart_cannot_import(self, client, db_session, auth_headers, company):
        company.chart_id = None
        db_session.commit()
        response = client.post("/api/invoices", headers=auth_headers,
                               files={"file": ("f.pdf", b"%PDF-1.4 x", "application/pdf")})
        assert response.status_code == 409 and "plan comptable" in response.json()["detail"]
        assert client.get("/api/auth/me", headers=auth_headers).json()["company_chart_id"] is None


class TestAccountsAreScopedToTheChart:
    def test_each_company_only_sees_its_own_chart(self, client, db_session, auth_headers, boss_headers,
                                                  company, fr_chart, minimal_chart_of_accounts):
        mine = {a["code"] for a in client.get("/api/accounts", headers=auth_headers).json()}
        assert mine == {"607", "4456", "401"}  # plan de test
        client.put(f"/api/companies/{company.id}/chart", headers=boss_headers, json={"chart_id": fr_chart.id})
        french = {a["code"] for a in client.get("/api/accounts", headers=auth_headers).json()}
        assert "44566" in french and "4456" in french and len(french) > 200

    def test_no_accounts_until_a_chart_is_chosen(self, client, db_session, auth_headers, company):
        company.chart_id = None
        db_session.commit()
        assert client.get("/api/accounts", headers=auth_headers).json() == []

    def test_correction_resolves_accounts_in_the_company_chart(
            self, client, db_session, auth_headers, boss_headers, company, comptable_user, fr_chart):
        client.put(f"/api/companies/{company.id}/chart", headers=boss_headers, json={"chart_id": fr_chart.id})
        accounts = {a.code: a for a in db_session.query(AccountModel).filter_by(chart_id=fr_chart.id)}
        invoice = InvoiceModel(company_id=company.id, uploaded_by=comptable_user.id, original_filename="f.pdf",
                               storage_path="/tmp/f", mime_type="application/pdf", file_size=1,
                               status="ENTRIES_PROPOSED")
        db_session.add(invoice)
        db_session.flush()
        entry = JournalEntryModel(invoice_id=invoice.id, company_id=company.id,
                                  entry_date=__import__("datetime").date(2026, 1, 1), label="x", status="PROPOSED")
        entry.lines = [EntryLineModel(account_id=accounts["604"].id, label="a", debit=100, credit=0, line_order=0),
                       EntryLineModel(account_id=accounts["401"].id, label="b", debit=0, credit=100, line_order=1)]
        db_session.add(entry)
        db_session.commit()
        line_id = entry.lines[0].id
        ok = client.put(f"/api/entries/{entry.id}", headers=auth_headers, json={
            "corrections": [{"line_id": line_id, "field": "account_code", "new_value": "6226"}]})
        assert ok.status_code == 200 and ok.json()["lines"][0]["account_code"] == "6226"
        unknown = client.put(f"/api/entries/{entry.id}", headers=auth_headers, json={
            "corrections": [{"line_id": line_id, "field": "account_code", "new_value": "99999"}]})
        assert unknown.status_code == 422


# ------------------------------------------------ Pipeline avec le PCG français
def _invoice_pdf(description: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    rows = [(40, 60, "SOCIETE EXEMPLE SAS", 16), (400, 60, "FACTURE", 14),
            (400, 95, "Facture No: FAC-FR-001", 10), (400, 110, "Date: 05/10/2026", 10),
            (40, 150, description, 10),
            (40, 170, "Conditions de reglement a trente jours, merci de votre confiance et de votre fidelite", 10),
            (380, 600, "Total HT", 10), (500, 600, "1 000,00", 10),
            (380, 620, "TVA 20 %", 10), (500, 620, "200,00", 10),
            (380, 640, "Total TTC", 10), (500, 640, "1 200,00", 10)]
    for x, y, text, size in rows:
        pdf.setFont("Helvetica", size)
        pdf.drawString(x, height - y, text)
    pdf.save()
    return buffer.getvalue()


def _fake_classifier(operation):
    class _Classifier:
        def classify(self, text, supplier_name, total):
            return ClassificationResult(operation, 0.9, {}, "test")
    return _Classifier()


@pytest.fixture()
def french_company(client, db_session, tmp_path, monkeypatch, boss_headers, company, fr_chart):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    client.put(f"/api/companies/{company.id}/chart", headers=boss_headers, json={"chart_id": fr_chart.id})
    return company


def _entry(client, headers, description, operation, monkeypatch):
    monkeypatch.setattr(pipeline_module, "load_active_classifier", lambda: _fake_classifier(operation))
    response = client.post("/api/invoices", headers=headers,
                           files={"file": ("f.pdf", _invoice_pdf(description), "application/pdf")})
    assert response.status_code == 202
    invoice_id = response.json()["id"]
    assert client.get(f"/api/invoices/{invoice_id}", headers=headers).json()["status"] == "ENTRIES_PROPOSED"
    entry = client.get(f"/api/entries/by-invoice/{invoice_id}", headers=headers).json()[0]
    return {l["account_code"]: Decimal(l["debit"] or 0) + Decimal(l["credit"] or 0) for l in entry["lines"]}, entry


class TestFrenchChartPipeline:
    def test_merchandise_purchase(self, client, auth_headers, french_company, monkeypatch):
        lines, entry = _entry(client, auth_headers, "Achat de marchandises destinees a la revente en boutique",
                              OperationType.ACHAT_MARCHANDISES, monkeypatch)
        assert lines == {"607": Decimal("1000"), "44566": Decimal("200"), "401": Decimal("1200")}
        assert entry["rule_code"] == "R-FR-ACHAT-MARCH-01"

    def test_service_purchase_uses_a_french_service_account(self, client, auth_headers, french_company, monkeypatch):
        lines, _ = _entry(client, auth_headers, "Honoraires d'expert-comptable et conseil juridique du trimestre",
                          OperationType.ACHAT_SERVICES, monkeypatch)
        assert lines == {"6226": Decimal("1000"), "44566": Decimal("200"), "401": Decimal("1200")}

    @pytest.mark.parametrize("description, expected", [
        ("Abonnement internet fibre et telephone mobile, forfait mensuel", "6262"),
        ("Reparation et entretien du vehicule de societe, atelier agree", "6155"),
        ("Fourniture de papier, cartouche et toner pour le bureau", "6064"),
        ("Prestation de service generale pour le client, sans precision particuliere", "604"),
    ])
    def test_service_keywords_pick_the_right_french_account(self, client, auth_headers, french_company,
                                                            monkeypatch, description, expected):
        lines, _ = _entry(client, auth_headers, description, OperationType.ACHAT_SERVICES, monkeypatch)
        assert expected in lines and "44566" in lines and "401" in lines

    def test_fixed_asset_uses_asset_vat_and_asset_supplier_accounts(self, client, auth_headers, french_company,
                                                                    monkeypatch):
        lines, _ = _entry(client, auth_headers, "Achat d'un ordinateur portable et d'un ecran pour le bureau",
                          OperationType.ACHAT_IMMOBILISATION, monkeypatch)
        # 2183 = matériel informatique en France (et non 2182 = matériel de transport)
        assert lines == {"2183": Decimal("1000"), "44562": Decimal("200"), "404": Decimal("1200")}

    def test_vehicle_is_transport_equipment(self, client, auth_headers, french_company, monkeypatch):
        lines, _ = _entry(client, auth_headers, "Achat d'un vehicule utilitaire neuf pour les livraisons",
                          OperationType.ACHAT_IMMOBILISATION, monkeypatch)
        assert "2182" in lines

    def test_the_entry_is_balanced(self, client, auth_headers, french_company, monkeypatch):
        _, entry = _entry(client, auth_headers, "Prestation de conseil", OperationType.ACHAT_SERVICES, monkeypatch)
        assert Decimal(entry["total_debit"]) == Decimal(entry["total_credit"]) == Decimal("1200")


class TestMalagasyChartKeepsItsOwnMeaning:
    def test_company_on_another_chart_is_not_affected(self, client, auth_headers, tmp_path, monkeypatch,
                                                      minimal_chart_of_accounts):
        monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
        lines, entry = _entry(client, auth_headers, "Achat de marchandises destinees a la revente en boutique",
                              OperationType.ACHAT_MARCHANDISES, monkeypatch)
        assert set(lines) == {"607", "4456", "401"}  # plan de test : pas de 44566


class TestCompanyWithoutChartStopsTheTreatment:
    def test_pipeline_reports_a_clear_error(self, client, db_session, auth_headers, company, comptable_user):
        invoice = InvoiceModel(company_id=company.id, uploaded_by=comptable_user.id, original_filename="f.pdf",
                               storage_path="/tmp/f", mime_type="application/pdf", file_size=1, status="ERROR")
        db_session.add(invoice)
        company.chart_id = None
        db_session.commit()
        assert client.post(f"/api/invoices/{invoice.id}/reprocess", headers=auth_headers).status_code == 202
        db_session.refresh(invoice)
        assert invoice.status == "ERROR" and "plan comptable" in invoice.error_message
