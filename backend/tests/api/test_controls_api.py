"""Contrôles avant génération de l'écriture, de bout en bout (vrais PDF) : une erreur
bloquante (B) empêche l'écriture et passe la facture en erreur avec le motif ; une
alerte (A) laisse l'écriture proposée. Factures de test 14, 15 et 16 (une erreur
volontaire chacune) et facture 12 (correcte)."""
from pathlib import Path

import pytest

from app.application import pipeline as pipeline_module
from app.core.config import get_settings
from app.domain.entities import OperationType
from tests.api.test_invoice_lines_api import _fake_classifier, malagasy_purchase_rules  # noqa: F401

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture()
def processed(client, auth_headers, company, malagasy_purchase_rules, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    monkeypatch.setattr(pipeline_module, "load_active_classifier",
                        lambda: _fake_classifier(OperationType.ACHAT_SERVICES))

    def run(filename: str):
        response = client.post("/api/invoices", headers=auth_headers, files={
            "file": (filename, (FIXTURES / filename).read_bytes(), "application/pdf")})
        invoice_id = response.json()["id"]
        invoice = client.get(f"/api/invoices/{invoice_id}", headers=auth_headers).json()
        entities = client.get(f"/api/invoices/{invoice_id}/entities", headers=auth_headers).json()
        controls = {e["normalized_value"]: e["entity_type"] for e in entities
                    if e["entity_type"].startswith("CONTROL_")}
        entries = client.get(f"/api/entries/by-invoice/{invoice_id}", headers=auth_headers).json()
        return invoice, controls, entries
    return run


@pytest.mark.parametrize("filename, code", [
    ("facture_14_erreur_remise_en_double.pdf", "DISCOUNT_RATE"),     # 5 % annoncés, 10 % déduits
    ("facture_15_erreur_sous_total.pdf", "SECTION_SUBTOTAL"),        # sous-total A faux de 500 000
    ("facture_16_erreur_acompte_double.pdf", "NET_TO_PAY"),          # acompte déduit deux fois
    ("facture_multitaux_erreur_tva.pdf", "VAT_RATE"),                # TVA 10 % calculée à 20 %
    ("facture_21_erreur_taux_tva_18.pdf", "VAT_RATE_UNKNOWN"),       # taux de 18 % inexistant
    ("facture_22_erreur_montant_en_lettres.pdf", "AMOUNT_IN_WORDS"),  # 36 839 840 en lettres
    ("facture_24_demo_incorrecte_complexe.pdf", "VAT_RATE"),         # TVA 20 % sans déduire la remise
    # multi-taux dont le TTC est faux de 5 400 : la TVA reste la somme des taux (2 127 227),
    # pas « TVA (0 %) 0 », sinon l'écart signalé était celui de toute la TVA
    ("facture_28_facture_avec_erreurs.pdf", "TTC_HT_TVA"),
    ("facture_28_facture_avec_erreurs.pdf", "VAT_RATE_UNKNOWN"),      # taux de 18 %
    ("facture_28_facture_avec_erreurs.pdf", "DUE_BEFORE_DATE"),       # échéance avant la facture
])
def test_blocking_error_prevents_the_entry(processed, filename, code):
    invoice, controls, entries = processed(filename)
    assert controls.get(code) == "CONTROL_BLOCKING"
    assert invoice["status"] == "ERROR"
    assert invoice["error_message"].startswith("Écriture non générée")
    assert entries == []


def test_correct_invoice_gets_its_entry_with_only_warnings(processed):
    invoice, controls, entries = processed("facture_multitaux_2pages.pdf")
    assert invoice["status"] == "ENTRIES_PROPOSED"
    assert "CONTROL_BLOCKING" not in controls.values()
    assert controls == {"VAT_ZERO_REASON": "CONTROL_WARNING"}   # 0 % sans motif d'exonération
    assert len(entries) == 1


@pytest.mark.parametrize("filename, warnings", [
    ("facture_17_correcte_amenagement.pdf", {}),
    ("facture_18_correcte_multitaux_agricole.pdf", {"VAT_ZERO_REASON": "CONTROL_WARNING"}),
    # retenue de garantie de 5 % : net = TTC − acompte − retenue (cas réel : bloquée à tort)
    ("facture_19_correcte_btp_retenue.pdf", {}),
    # même ligne de montage facturée deux fois : alerte, l'écriture reste proposée
    ("facture_20_erreur_ligne_en_doublon.pdf", {"DUPLICATE_LINE": "CONTROL_WARNING"}),
    # libellé « Remise marché public (2,5 %) » sur deux lignes, note « Acompte déduit … » à
    # côté de « TVA (0 %) » : les taux étaient lus comme montants (TVA 20 % et acompte)
    ("facture_23_demo_correcte_complexe.pdf", {"VAT_ZERO_REASON": "CONTROL_WARNING"}),
    # avoir multi-taux : « Total avoir TTC » est le TTC (il n'était pas reconnu)
    ("facture_27_facture_avoir_correcte.pdf", {"VAT_ZERO_REASON": "CONTROL_WARNING"}),
])
def test_entry_is_proposed_with_warnings_only(processed, filename, warnings):
    invoice, controls, entries = processed(filename)
    assert controls == warnings
    assert invoice["status"] == "ENTRIES_PROPOSED" and len(entries) == 1
