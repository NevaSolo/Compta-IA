"""Facture sans TVA ni ligne « Total HT » : « Sous-total », « Remise », « Total à payer ».

Cas réel : sous-total 131 000, remise − 6 000, total à payer 125 000. Le sous-total lu comme
HT donnait une TVA de −6 000 et l'erreur « Montant VAT négatif pour la règle … »."""
import io
from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application import pipeline as pipeline_module
from app.core.config import get_settings
from app.domain.entities import OperationType
from app.domain.ports import ClassificationResult


def _invoice_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    rows = [
        (200, 44, "FACTURE D'ACHAT", 16),
        (150, 72, "Pelotes de laine et fils a tricoter - Montants en ariary malgaches (Ar)", 9),
        (70, 111, "N facture :", 9), (145, 111, "FAC-2026-014", 9),
        (335, 111, "Date :", 9), (398, 111, "13/10/2026", 9),
        (70, 136, "Vendeur :", 9), (145, 136, "Boutique Fil & Creation", 9),
        (335, 136, "Telephone :", 9), (398, 136, "034 12 345 67", 9),
        (70, 162, "Acheteur :", 9), (145, 162, "Client exemple", 9),
        (70, 263, "Pelote de laine acrylique rose", 9), (400, 263, "30 000", 9),
        (70, 293, "Pelote de laine coton beige", 9), (400, 293, "22 500", 9),
        (330, 540, "Sous-total", 9), (450, 540, "131 000", 9),
        (330, 565, "Remise", 9), (450, 565, "- 6 000", 9),
        (330, 595, "TOTAL A PAYER", 10), (450, 595, "125 000", 10),
        (70, 650, "Arrete la presente facture a la somme de : Cent vingt-cinq mille ariary (125 000 Ar).", 9),
    ]
    for x, y, text, size in rows:
        pdf.setFont("Helvetica", size)
        pdf.drawString(x, height - y, text)
    pdf.save()
    return buffer.getvalue()


class _Classifier:
    def classify(self, text, supplier_name, total):
        return ClassificationResult(OperationType.ACHAT_MARCHANDISES, 0.9, {}, "test")


@pytest.fixture()
def pipeline_env(tmp_path, monkeypatch, minimal_chart_of_accounts):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    monkeypatch.setattr(pipeline_module, "load_active_classifier", lambda: _Classifier())


def test_subtotal_before_discount_does_not_produce_a_negative_vat(client, auth_headers, pipeline_env):
    response = client.post("/api/invoices", headers=auth_headers,
                           files={"file": ("factest.pdf", _invoice_pdf(), "application/pdf")})
    assert response.status_code == 202
    invoice = client.get(f"/api/invoices/{response.json()['id']}", headers=auth_headers).json()

    assert invoice["status"] == "ENTRIES_PROPOSED", invoice["error_message"]
    assert Decimal(invoice["total_ttc"]) == Decimal("125000")
    assert Decimal(invoice["total_ht"]) == Decimal("125000")  # le net : pas le sous-total de 131 000
    assert Decimal(invoice["total_vat"]) == Decimal("0")
    assert invoice["supplier_name"] == "Boutique Fil & Creation"  # pas le sous-titre du document

    entry = client.get(f"/api/entries/by-invoice/{invoice['id']}", headers=auth_headers).json()[0]
    assert Decimal(entry["total_debit"]) == Decimal(entry["total_credit"]) == Decimal("125000")
    # TVA nulle : pas de ligne de TVA (une ligne à zéro est omise de l'écriture)
    assert [line["account_code"] for line in entry["lines"]] == ["607", "401"]
