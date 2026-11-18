"""Lignes de détail extraites par le pipeline, de bout en bout (vrai PDF) :
elles sont enregistrées et consultables, SANS changer l'écriture générée
(étape 1 de la ventilation par ligne), et une panne de l'extraction des
lignes ne fait jamais échouer le traitement."""
import io
from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application import pipeline as pipeline_module
from app.catalog import installer
from app.core.config import get_settings
from app.domain.entities import OperationType
from app.domain.ports import ClassificationResult
from app.infrastructure.db.models import ChartModel
from app.infrastructure.nlp.line_items import TableLineExtractor

# Facture multi-nature : 9 lignes, deux taux de TVA (20 % et 0 %)
ROWS = [
    ("Honoraires mission conseil strategique", "1", "2 400,00", "20%", "2 400,00"),
    ("Location salle de reunion", "2", "350,00", "20%", "700,00"),
    ("Abonnement logiciel SaaS annuel", "12", "49,90", "20%", "598,80"),
    ("Nettoyage des locaux", "1", "420,00", "20%", "420,00"),
    ("Publicite en ligne campagne", "1", "1 150,00", "20%", "1 150,00"),
    ("Fournitures de bureau", "1", "186,60", "20%", "186,60"),
    ("Ordinateur portable Dell 15", "1", "1 390,00", "20%", "1 390,00"),
    ("Frais de deplacement", "1", "980,00", "20%", "980,00"),
    ("Affranchissement", "1", "125,00", "0%", "125,00"),
]


def _multi_line_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]

    def text(x, y, value, size=10):
        pdf.setFont("Helvetica", size)
        pdf.drawString(x, height - y, value)

    text(40, 60, "CABINET ALTITUDE CONSEIL", 16)
    text(400, 60, "FACTURE", 14)
    text(400, 95, "Facture No: FAC-2026-118")
    text(400, 110, "Date: 05/10/2026")
    text(40, 150, "Conditions de reglement a trente jours, merci de votre confiance et fidelite")
    for x, label in ((40, "Designation"), (300, "Qte"), (350, "P.U. HT"), (430, "TVA"), (490, "Montant HT")):
        text(x, 200, label)
    for i, (designation, qty, pu, vat, amount) in enumerate(ROWS):
        y = 225 + i * 20
        for x, value in ((40, designation), (300, qty), (350, pu), (430, vat), (490, amount)):
            text(x, y, value)
    text(380, 450, "Total HT")
    text(490, 450, "7 950,40 €")
    text(380, 470, "Total TVA")
    text(490, 470, "1 565,08 €")
    text(380, 490, "Total TTC")
    text(490, 490, "9 515,48 €")
    pdf.save()
    return buffer.getvalue()


def _fake_classifier(operation):
    class _Classifier:
        def classify(self, text, supplier_name, total):
            return ClassificationResult(operation, 0.9, {}, "test")
    return _Classifier()


@pytest.fixture()
def french_company(db_session, tmp_path, monkeypatch, company):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    installer.install_catalog(db_session)
    company.chart_id = db_session.query(ChartModel).filter_by(code="PCG_FR_2014").one().id
    company.base_currency = "EUR"
    db_session.commit()
    monkeypatch.setattr(pipeline_module, "load_active_classifier",
                        lambda: _fake_classifier(OperationType.ACHAT_SERVICES))
    return company


def _upload(client, headers) -> int:
    response = client.post("/api/invoices", headers=headers,
                           files={"file": ("altitude.pdf", _multi_line_pdf(), "application/pdf")})
    assert response.status_code == 202
    return response.json()["id"]


def test_lines_are_extracted_and_reconcile_with_total_ht(client, auth_headers, french_company):
    invoice_id = _upload(client, auth_headers)
    body = client.get(f"/api/invoices/{invoice_id}/lines", headers=auth_headers).json()

    assert [l["description"] for l in body["items"]] == [r[0] for r in ROWS]
    assert [Decimal(l["amount"]) for l in body["items"]] == \
        [Decimal(r[4].replace(" ", "").replace(",", ".")) for r in ROWS]
    assert Decimal(body["total"]) == Decimal("7950.40")
    assert body["matches"] == "HT"
    rates = {Decimal(l["vat_rate"]) for l in body["items"]}
    assert rates == {Decimal("20"), Decimal("0")}
    laptop = body["items"][6]
    assert (Decimal(laptop["quantity"]), Decimal(laptop["unit_price"])) == (Decimal("1"), Decimal("1390"))


def _entry_amounts(client, headers, invoice_id) -> dict[str, tuple[Decimal, Decimal]]:
    assert client.get(f"/api/invoices/{invoice_id}", headers=headers).json()["status"] == "ENTRIES_PROPOSED"
    entry = client.get(f"/api/entries/by-invoice/{invoice_id}", headers=headers).json()[0]
    return {l["account_code"]: (Decimal(l["debit"] or 0), Decimal(l["credit"] or 0)) for l in entry["lines"]}


def test_entry_is_split_by_nature_of_each_line(client, auth_headers, french_company):
    """Étape 3 : une écriture ventilée — un compte par nature de dépense, le
    portable en immobilisation (2183, TVA 44562, fournisseur d'immobilisations 404)."""
    lines = _entry_amounts(client, auth_headers, _upload(client, auth_headers))
    assert lines == {
        "6226": (Decimal("2400.00"), 0),   # honoraires / conseil
        "6132": (Decimal("700.00"), 0),    # location de salle
        "6181": (Decimal("598.80"), 0),    # abonnement SaaS : une charge, pas un logiciel immobilisé
        "6155": (Decimal("420.00"), 0),    # nettoyage
        "6231": (Decimal("1150.00"), 0),   # publicité
        "6064": (Decimal("186.60"), 0),    # fournitures de bureau (et non du mobilier 2184)
        "6251": (Decimal("980.00"), 0),    # déplacement
        "6261": (Decimal("125.00"), 0),    # affranchissement (TVA 0 %)
        "2183": (Decimal("1390.00"), 0),   # ordinateur : immobilisation
        "44566": (Decimal("1287.08"), 0),  # TVA sur biens et services (20 % de 6 435,40)
        "44562": (Decimal("278.00"), 0),   # TVA sur immobilisations (20 % de 1 390,00)
        "401": (0, Decimal("7847.48")),
        "404": (0, Decimal("1668.00")),
    }
    debit = sum(d for d, _ in lines.values())
    assert debit == sum(c for _, c in lines.values()) == Decimal("9515.48")


def test_switch_off_keeps_the_invoice_level_entry(client, auth_headers, french_company, monkeypatch):
    monkeypatch.setattr(get_settings(), "line_level_entries", False)
    lines = _entry_amounts(client, auth_headers, _upload(client, auth_headers))
    assert len(lines) == 3 and lines["401"] == (0, Decimal("9515.48"))


def test_failing_ventilation_keeps_the_invoice_level_entry(client, auth_headers, french_company, monkeypatch):
    from app.infrastructure.rules.line_entry import LineEntryBuilder

    def boom(self, **kwargs):
        raise RuntimeError("panne")
    monkeypatch.setattr(LineEntryBuilder, "build", boom)
    lines = _entry_amounts(client, auth_headers, _upload(client, auth_headers))
    assert len(lines) == 3


def test_failing_line_extraction_never_breaks_the_pipeline(client, auth_headers, french_company, monkeypatch):
    def boom(self, ocr_result):
        raise RuntimeError("tableau illisible")
    monkeypatch.setattr(TableLineExtractor, "extract", boom)

    invoice_id = _upload(client, auth_headers)
    assert client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).json()["status"] == "ENTRIES_PROPOSED"
    body = client.get(f"/api/invoices/{invoice_id}/lines", headers=auth_headers).json()
    assert body == {"items": [], "total": "0", "matches": None}


def test_reprocess_does_not_duplicate_lines(client, auth_headers, french_company):
    invoice_id = _upload(client, auth_headers)
    assert client.post(f"/api/invoices/{invoice_id}/reprocess", headers=auth_headers).status_code == 202
    body = client.get(f"/api/invoices/{invoice_id}/lines", headers=auth_headers).json()
    assert len(body["items"]) == len(ROWS)


def test_lines_of_another_company_are_hidden(client, auth_headers, french_company, db_session, admin_user):
    from app.infrastructure.db.models import CompanyModel, InvoiceModel
    other = CompanyModel(name="Autre", chart_id=french_company.chart_id)
    db_session.add(other)
    db_session.commit()
    invoice = InvoiceModel(company_id=other.id, uploaded_by=admin_user.id, original_filename="x.pdf",
                           storage_path="x", mime_type="application/pdf", file_size=1)
    db_session.add(invoice)
    db_session.commit()
    assert client.get(f"/api/invoices/{invoice.id}/lines", headers=auth_headers).status_code == 404


@pytest.fixture()
def malagasy_purchase_rules(db_session, chart):
    """Règles d'achat du plan malgache (seed_accounts.sql) et leurs comptes."""
    from app.infrastructure.db.models import AccountModel, AccountingRuleModel
    from tests.infrastructure.test_line_entry import MG_RULES
    codes = {c for r in MG_RULES for spec in r["template"]["lines"]
             for c in (spec.get("candidates") or []) + [spec["default_account"]]}
    for code in sorted(codes):
        db_session.add(AccountModel(chart_id=chart.id, code=code, label=f"Compte {code}",
                                    account_class=int(code[0]),
                                    normal_balance="CREDIT" if code.startswith("40") else "DEBIT"))
    for priority, rule in zip((100, 100, 100, 110), MG_RULES):
        db_session.add(AccountingRuleModel(chart_id=chart.id, code=rule["code"],
                                           operation_type=rule["operation_type"],
                                           description=rule["code"], priority=priority,
                                           template=rule["template"]))
    db_session.commit()


def test_two_page_multirate_invoice_with_global_discount_is_split(client, auth_headers, company,
                                                                  malagasy_purchase_rules,
                                                                  tmp_path, monkeypatch):
    """Facture FA-2026-11-0412 (plan malgache) : trois taux de TVA, intitulés de
    section, remise de ligne, remise globale de 2 % et acompte. Cas réel : une
    seule ligne 624 « transports » sans TVA, pour 46 961 600 Ar."""
    from pathlib import Path
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    monkeypatch.setattr(pipeline_module, "load_active_classifier",
                        lambda: _fake_classifier(OperationType.ACHAT_SERVICES))
    pdf = (Path(__file__).resolve().parents[1] / "fixtures" / "facture_multitaux_2pages.pdf").read_bytes()
    response = client.post("/api/invoices", headers=auth_headers,
                           files={"file": ("multitaux.pdf", pdf, "application/pdf")})
    invoice_id = response.json()["id"]
    invoice = client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).json()
    assert (Decimal(invoice["total_vat"]), Decimal(invoice["total_ttc"])) == \
        (Decimal("6215160"), Decimal("53176760"))
    assert invoice["status"] == "ENTRIES_PROPOSED", invoice.get("error_message")
    lines = _entry_amounts(client, auth_headers, invoice_id)
    assert lines["4456"] == (Decimal("6215160.00"), 0)
    assert lines["215"] == (Decimal("8937600.00"), 0)    # plaques de cuisson, après remise de 2 %
    assert lines["607"] == (Decimal("12054000.00"), 0)   # denrées
    assert sum(d for d, _ in lines.values()) == sum(c for _, c in lines.values()) == Decimal("53176760.00")
