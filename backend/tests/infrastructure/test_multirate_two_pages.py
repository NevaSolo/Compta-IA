"""Facture FA-2026-11-0412 (2 pages) : tableau par sections, trois taux de TVA
(0 / 10 / 20 %), remise en ligne (-5 %), remise globale (2 %), acompte et
mise en page à deux colonnes. Cas réel : TVA lue 0, TTC = HT, TTC pris pour
l'acompte, intitulés de section comptés comme lignes, écriture sur un seul compte."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.rules import net_of_global_discount, reconcile_line_items
from app.infrastructure.nlp.extractor import HybridExtractor
from app.infrastructure.nlp.line_items import TableLineExtractor
from app.infrastructure.ocr.pdf_text import read_pdf_text_layer

from tests.infrastructure.test_line_entry import SERVICES, _builder

PDF = Path(__file__).resolve().parents[1] / "fixtures" / "facture_multitaux_2pages.pdf"


@pytest.fixture(scope="module")
def ocr():
    return read_pdf_text_layer(str(PDF))


def test_totals_sum_the_vat_of_each_rate_and_keep_the_deposit_apart(ocr):
    values = {e.entity_type: Decimal(e.normalized_value)
              for e in HybridExtractor(use_spacy=False).extract(ocr, "fr") if e.entity_type in (
                  "TOTAL_HT", "TOTAL_VAT", "TOTAL_TTC", "DEPOSIT_PAID", "NET_TO_PAY", "GLOBAL_DISCOUNT")}
    assert values == {
        "TOTAL_HT": Decimal("46961600"), "TOTAL_VAT": Decimal("6215160"),   # 5 448 800 + 766 360 + 0
        "TOTAL_TTC": Decimal("53176760"), "DEPOSIT_PAID": Decimal("8000000"),
        "NET_TO_PAY": Decimal("45176760"), "GLOBAL_DISCOUNT": Decimal("958400"),
    }


def test_section_titles_and_page_footer_are_not_lines(ocr):
    lines = TableLineExtractor().extract(ocr)
    assert [l.amount for l in lines] == [Decimal(a) for a in (
        "8100000", "3360000", "840000", "9120000", "9500000", "5700000", "3480000",
        "3120000", "2850000", "1850000")]
    plaques = lines[3]   # remise de ligne « -5 % » : 2 × 4 800 000 × 0,95
    assert (plaques.quantity, plaques.unit_price, plaques.vat_rate) == (2, 4800000, 20)
    assert "4 feux gaz" in plaques.description


def test_entry_is_split_by_nature_after_the_global_discount(ocr):
    lines = TableLineExtractor().extract(ocr)
    assert reconcile_line_items(lines, Decimal("46961600"), Decimal("53176760")) is None  # avant remise
    net = net_of_global_discount(lines, Decimal("46961600"), Decimal("958400"))
    entry = _builder().build(lines=net, fallback_rule=SERVICES, fallback_account="624",
                             total_vat=Decimal("6215160"), invoice_id=1, company_id=1,
                             entry_date=date(2026, 11, 18), label="Facture FA-2026-11-0412")
    assert {l.account_code: (l.debit, l.credit) for l in entry.lines} == {
        "607": (Decimal("12054000.00"), 0),   # riz, huile, sel (0 %)
        "215": (Decimal("8937600.00"), 0),    # plaques de cuisson professionnelles
        "606": (Decimal("18306400.00"), 0),   # vaisselle, linge, détergents
        "604": (Decimal("5850600.00"), 0),    # installation, formation
        "624": (Decimal("1813000.00"), 0),    # livraison et transport
        "4456": (Decimal("6215160.00"), 0),
        "401": (0, Decimal("42451640.00")),
        "404": (0, Decimal("10725120.00")),   # 8 937 600 + 20 % de TVA
    }


ERROR_PDF = PDF.with_name("facture_multitaux_erreur_tva.pdf")


def test_vat_summary_row_computed_at_the_wrong_rate_is_flagged():
    """Facture MS-2026-1187 : la ligne à 10 % du récapitulatif est calculée à 20 %
    (1 323 080 au lieu de 661 540) ; TTC = HT + TVA imprimée reste vrai."""
    entities = HybridExtractor(use_spacy=False).extract(read_pdf_text_layer(str(ERROR_PDF)), "fr")
    warnings = [e for e in entities if e.entity_type == "VAT_RATE_MISMATCH"]
    assert [Decimal(w.normalized_value) for w in warnings] == [Decimal("661540.00")]
    assert "661 540 attendu" in warnings[0].raw_value
    supplier = next(e for e in entities if e.entity_type == "SUPPLIER_NAME")
    assert supplier.raw_value == "MediSoa Distribution SARL"   # sous l'en-tête « ÉMETTEUR »


def test_correct_vat_summary_raises_no_warning(ocr):
    entities = HybridExtractor(use_spacy=False).extract(ocr, "fr")
    assert not [e for e in entities if e.entity_type == "VAT_RATE_MISMATCH"]


def test_section_rate_applies_to_its_lines_and_medical_items_are_split():
    lines = TableLineExtractor().extract(read_pdf_text_layer(str(ERROR_PDF)))
    assert [l.vat_rate for l in lines] == [Decimal(r) for r in ("0", "0", "0", "20", "20", "20", "10", "10", "10")]
    net = net_of_global_discount(lines, Decimal("58597700"), Decimal("1812300"))
    assert sum((l.amount * l.vat_rate / 100).quantize(Decimal("0.01")) for l in net) == Decimal("8918180.00")
    entry = _builder().build(lines=net, fallback_rule=SERVICES, fallback_account="615",
                             total_vat=Decimal("9579720"), invoice_id=1, company_id=1,
                             entry_date=date(2026, 11, 18), label="Facture MS-2026-1187")
    debits = {l.account_code: l.debit for l in entry.lines if l.debit}
    assert debits["606"] == Decimal("10699100.00")   # sérum, compresses, gants
    assert debits["215"] == Decimal("41283200.00")   # moniteur, lits, autoclave
    assert debits["615"] == Decimal("3104000.00")    # contrat de maintenance
    assert debits["604"] == Decimal("3511400.00")    # installation, formation
