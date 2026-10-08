"""Tests du moteur de règles : le gabarit JSON doit produire une écriture
équilibrée, et le suggesteur ML ne doit jamais sortir de la liste
`candidates` fournie par la règle (contrainte validée en Phase 6)."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain.entities import Account
from app.domain.ports import AccountSuggestion
from app.infrastructure.rules.rule_engine import RuleEngine, RuleEngineError

ACCOUNTS = {
    "607": Account(id=1, code="607", label="Achats de marchandises",
                   account_class=6, normal_balance="DEBIT"),
    "4456": Account(id=2, code="4456", label="TVA déductible",
                    account_class=4, normal_balance="DEBIT"),
    "401": Account(id=3, code="401", label="Fournisseurs", account_class=4,
                   normal_balance="CREDIT"),
    "404": Account(id=4, code="404", label="Fournisseurs d'immobilisations",
                   account_class=4, normal_balance="CREDIT"),
    "2182": Account(id=5, code="2182", label="Matériel informatique",
                    account_class=2, normal_balance="DEBIT"),
}

RULE_MARCHANDISES = {
    "code": "R-ACHAT-MARCH-01",
    "template": {"lines": [
        {"role": "charge", "side": "D", "amount": "HT",
         "default_account": "607", "ml_refinable": True, "candidates": ["607"]},
        {"role": "tva", "side": "D", "amount": "VAT",
         "default_account": "4456", "ml_refinable": False},
        {"role": "tiers", "side": "C", "amount": "TTC",
         "default_account": "401", "ml_refinable": False},
    ]},
}


class FakeAccountRepository:
    def get_by_code(self, code):
        return ACCOUNTS.get(code)

    def list_active(self):
        return list(ACCOUNTS.values())


class FakeSuggesterAlwaysDefault:
    """Simule un suggesteur ML malicieux qui tenterait de sortir du cadre :
    le test vérifie que même dans ce cas, le compte reste dans `candidates`."""
    def suggest(self, text, supplier, candidates, default):
        # Tente de renvoyer un compte HORS candidats (2182, une immobilisation)
        rogue_code = "2182"
        if rogue_code in candidates:
            return AccountSuggestion(account_code=rogue_code, confidence=0.9,
                                     suggested_by_ml=True)
        return AccountSuggestion(account_code=default, confidence=0.5,
                                 suggested_by_ml=False)


def test_generates_balanced_entry_from_template():
    engine = RuleEngine(FakeAccountRepository(), FakeSuggesterAlwaysDefault())
    entry = engine.generate_entry(
        rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
        label="Facture X", amounts={"HT": Decimal("100"), "VAT": Decimal("20"),
                                    "TTC": Decimal("120")},
        invoice_text="achat de riz", supplier=None)
    assert entry.is_balanced()
    assert entry.total_debit() == Decimal("120")
    assert {line.account_code for line in entry.lines} == {"607", "4456", "401"}


def test_ml_suggestion_cannot_escape_candidates_whitelist():
    """Le suggesteur essaie de renvoyer 2182 (immobilisation) mais la règle
    n'autorise que 607 en candidat -> le compte réellement affecté doit être 607."""
    engine = RuleEngine(FakeAccountRepository(), FakeSuggesterAlwaysDefault())
    entry = engine.generate_entry(
        rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
        label="Facture X", amounts={"HT": Decimal("100"), "VAT": Decimal("20"),
                                    "TTC": Decimal("120")},
        invoice_text="achat", supplier=None)
    charge_line = next(l for l in entry.lines if l.debit == Decimal("100"))
    assert charge_line.account_code == "607"  # jamais 2182


def test_zero_vat_line_is_omitted_not_an_error():
    """Bug réel corrigé : une facture exonérée (TVA=0, HT=TTC) faisait
    échouer la génération d'écriture ('Montant VAT indisponible'), alors que
    0 est une valeur légitime — la ligne TVA doit simplement être omise et
    l'écriture rester équilibrée sur les deux lignes restantes."""
    engine = RuleEngine(FakeAccountRepository(), FakeSuggesterAlwaysDefault())
    entry = engine.generate_entry(
        rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
        label="Facture exonérée",
        amounts={"HT": Decimal("100"), "VAT": Decimal("0"), "TTC": Decimal("100")},
        invoice_text="achat de riz", supplier=None)
    assert entry.is_balanced()
    assert {line.account_code for line in entry.lines} == {"607", "401"}  # pas de 4456
    assert entry.total_debit() == Decimal("100")


def test_negative_amount_raises():
    engine = RuleEngine(FakeAccountRepository(), FakeSuggesterAlwaysDefault())
    with pytest.raises(RuleEngineError):
        engine.generate_entry(
            rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
            label="Facture X",
            amounts={"HT": Decimal("100"), "VAT": Decimal("-5"), "TTC": Decimal("95")},
            invoice_text="achat", supplier=None)


def test_missing_amount_raises():
    engine = RuleEngine(FakeAccountRepository(), FakeSuggesterAlwaysDefault())
    with pytest.raises(RuleEngineError):
        engine.generate_entry(
            rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
            label="Facture X", amounts={"HT": Decimal("100"), "VAT": None, "TTC": None},
            invoice_text="achat", supplier=None)


def test_unknown_account_code_raises():
    class BadRepo(FakeAccountRepository):
        def get_by_code(self, code):
            return None
    engine = RuleEngine(BadRepo(), FakeSuggesterAlwaysDefault())
    with pytest.raises(RuleEngineError):
        engine.generate_entry(
            rule=RULE_MARCHANDISES, invoice_id=1, company_id=1, entry_date=date(2026, 1, 15),
            label="x", amounts={"HT": Decimal("100"), "VAT": Decimal("20"),
                                "TTC": Decimal("120")},
            invoice_text="x", supplier=None)
