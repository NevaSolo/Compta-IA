"""Contrôles unitaires (app.domain.controls) et conversion du montant en lettres."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain.controls import BLOCKING, WARNING, InvoiceFacts, run_controls
from app.infrastructure.nlp.extractor import french_words_to_number

RATES = {Decimal(r) for r in ("0", "5.5", "10", "20")}
TODAY = date(2026, 11, 18)


@pytest.mark.parametrize("text, value", [
    ("Cent onze millions sept cent cinquante-quatre mille huit cents", 111754800),
    ("Quarante-cinq millions cent soixante-seize mille sept cent soixante", 45176760),
    ("Vingt-cinq millions cinq cent quatre-vingt-douze mille", 25592000),
    ("quatre-vingt-dix-neuf", 99), ("soixante et onze", 71), ("deux milliards trois cents millions", 2300000000),
    ("mille deux cent", 1200),
])
def test_french_words(text, value):
    assert french_words_to_number(text) == value


def facts(**kw):
    base = dict(is_credit_note=False, currency="MGA", total_ht=Decimal("1000"), total_vat=Decimal("200"),
                total_ttc=Decimal("1200"), invoice_date=date(2026, 11, 1))
    base.update(kw)
    return InvoiceFacts(**base)


def codes(f):
    return {(a.code, a.severity) for a in run_controls(f, TODAY, RATES)}


def test_clean_invoice_has_no_anomaly():
    assert codes(facts(amounts={"NET_TO_PAY": Decimal("1200"), "AMOUNT_IN_WORDS": Decimal("1200")})) == set()


def test_each_rule():
    assert ("TTC_HT_TVA", BLOCKING) in codes(facts(total_ttc=Decimal("1250")))
    assert ("AMOUNT_IN_WORDS", BLOCKING) in codes(facts(amounts={"AMOUNT_IN_WORDS": Decimal("1100")}))
    assert ("DEPOSIT_GT_TTC", BLOCKING) in codes(facts(amounts={"DEPOSIT_PAID": Decimal("1500")}))
    assert ("DATE_FUTURE", BLOCKING) in codes(facts(invoice_date=date(2027, 1, 1)))
    assert ("DUE_BEFORE_DATE", BLOCKING) in codes(facts(texts={"DUE_DATE": "2026-10-01"}))
    assert ("VAT_RATE_UNKNOWN", BLOCKING) in codes(facts(texts={"VAT_SUMMARY_RATES": "18"}))
    assert ("VAT_BASES", BLOCKING) in codes(facts(amounts={"VAT_SUMMARY_BASES": Decimal("900")}))
    assert ("HT_VS_GROSS", BLOCKING) in codes(facts(amounts={"GROSS_TOTAL_HT": Decimal("1100"),
                                                             "GLOBAL_DISCOUNT": Decimal("50")}))
    assert ("NON_POSITIVE", BLOCKING) in codes(facts(total_ht=Decimal("-1000"), total_vat=Decimal("-200"),
                                                     total_ttc=Decimal("-1200")))
    assert ("VAT_ZERO_REASON", WARNING) in codes(facts(texts={"VAT_SUMMARY_RATES": "0"}))
    assert ("VAT_ZERO_REASON", WARNING) not in codes(facts(texts={"VAT_SUMMARY_RATES": "0"},
                                                           full_text="Exportation exonérée de TVA"))
    assert ("NIF_MISSING", WARNING) in codes(facts(has_nif=False))


def test_credit_note_may_be_negative():
    assert not codes(facts(is_credit_note=True, total_ht=Decimal("-1000"), total_vat=Decimal("-200"),
                           total_ttc=Decimal("-1200")))
