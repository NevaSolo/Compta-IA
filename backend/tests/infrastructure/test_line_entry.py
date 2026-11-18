"""Écriture ventilée ligne par ligne, avec les règles du plan malgache
(seed_accounts.sql) : un compte par nature de dépense, immobilisation isolée,
TVA ventilée par taux, et repli (None) quand la ventilation n'est pas sûre."""
from datetime import date
from decimal import Decimal

from app.domain.entities import Account, InvoiceLine
from app.infrastructure.ml.classifiers import ACCOUNT_KEYWORDS
from app.infrastructure.rules.line_entry import LineEntryBuilder


def _rule(code, operation, charge_default, candidates, tiers="401"):
    return {"code": code, "operation_type": operation, "template": {"lines": [
        {"role": "charge", "side": "D", "amount": "HT", "default_account": charge_default,
         "ml_refinable": True, "candidates": candidates},
        {"role": "tva", "side": "D", "amount": "VAT", "default_account": "4456", "ml_refinable": False},
        {"role": "tiers", "side": "C", "amount": "TTC", "default_account": tiers, "ml_refinable": False},
    ]}}


MG_RULES = [  # par priorité, comme list_active_for_chart
    _rule("R-ACHAT-MARCH-01", "ACHAT_MARCHANDISES", "607", ["607"]),
    _rule("R-ACHAT-SVC-01", "ACHAT_SERVICES", "604",
          ["604", "611", "613", "615", "616", "617", "621", "622", "623", "624", "625", "626", "627", "628"]),
    _rule("R-ACHAT-IMMO-01", "ACHAT_IMMOBILISATION", "218",
          ["204", "205", "213", "215", "218", "2181", "2182", "2183"], tiers="404"),
    _rule("R-ACHAT-FOURN-01", "ACHAT_SERVICES", "606", ["6061", "6064", "606"]),
]
SERVICES = MG_RULES[1]


class FakeAccounts:
    def get_by_code(self, code):
        return Account(id=hash(code) % 10_000, code=code, label=f"Compte {code}",
                       account_class=int(code[0]), normal_balance="DEBIT")


def _builder(**kwargs):
    return LineEntryBuilder(FakeAccounts(), MG_RULES, ACCOUNT_KEYWORDS, **kwargs)


def _build(lines, total_vat, builder=None, **kwargs):
    entry = (builder or _builder()).build(
        lines=lines, fallback_rule=SERVICES, fallback_account="622", total_vat=total_vat,
        invoice_id=1, company_id=1, entry_date=date(2024, 10, 4), label="Facture FV-2024-0180", **kwargs)
    if entry is None:
        return None
    return {l.account_code: (l.debit, l.credit) for l in entry.lines}


def L(no, description, amount, rate="20"):
    return InvoiceLine(no, description, Decimal(amount), vat_rate=Decimal(rate) if rate is not None else None)


# Les 9 lignes de la facture FV-2024-0180 (3 taux de TVA), telles qu'extraites du PDF
FV_0180 = [
    L(1, "CONS-STR Prestation de conseil en stratégie digitale — AT honoraires (3 jours)", "2850.00"),
    L(2, "LOC-SALLE Location de salle de réunion équipée — demi-journée séminaire rnée", "360.00"),
    L(3, "ABO-SAAS Abonnement annuel logiciel SaaS de gestion CRM", "1296.00"),
    L(4, "NETT-LOC Prestation de nettoyage des locaux — contrat mensuel", "320.00"),
    L(5, "PUB-CAMP Campagne publicitaire digitale (réseaux sociaux, octobre)", "1150.00"),
    L(6, "FOURN-BU Fournitures de bureau (papeterie, R consommables imprimante)", "186.40"),
    L(7, "PC-PORT15 Ordinateur portable professionnel 15\" — N° série PC-ALT-5523 (immobilisation)", "1390.00"),
    L(8, "TRAIN-BIL Frais de déplacement — billets de train mission client Lyon", "356.00", "10"),
    L(9, "AFFRANCH Frais postaux et affranchissement courrier recommandé", "42.00", "0"),
]


def test_each_line_gets_the_account_of_its_nature_in_the_malagasy_chart():
    lines = _build(FV_0180, Decimal("1546.08"))
    assert lines == {
        "622": (Decimal("2850.00"), 0), "613": (Decimal("360.00"), 0), "628": (Decimal("1296.00"), 0),
        "615": (Decimal("320.00"), 0), "623": (Decimal("1150.00"), 0), "6064": (Decimal("186.40"), 0),
        "2182": (Decimal("1390.00"), 0), "625": (Decimal("356.00"), 0), "626": (Decimal("42.00"), 0),
        # TVA ventilée par taux : 20 % × 7 552,40 − 10 % × 356,00 → 1 546,08 au total
        "4456": (Decimal("1546.08"), 0),
        "401": (0, Decimal("7828.48")),   # services + fournitures : 6 560,40 HT + 1 268,08 TVA
        "404": (0, Decimal("1668.00")),   # ordinateur : 1 390,00 HT + 278,00 TVA
    }


def test_entry_is_balanced_after_currency_conversion():
    lines = _build(FV_0180, Decimal("1546.08"), rate=Decimal("4999.37"))
    assert sum(d for d, _ in lines.values()) == sum(c for _, c in lines.values())


def test_vat_is_prorated_when_line_rates_are_unknown():
    lines = _build([L(1, "Honoraires d'audit", "800.00", None), L(2, "Location de salle", "200.00", None)],
                   Decimal("200.00"))
    assert lines["4456"] == (Decimal("200.00"), 0) and lines["401"] == (0, Decimal("1200.00"))


def test_line_vats_always_sum_to_the_invoice_vat():
    lines = _build([L(1, "Honoraires", "33.33"), L(2, "Location", "33.33"), L(3, "Nettoyage", "33.34")],
                   Decimal("20.01"))
    assert lines["4456"] == (Decimal("20.01"), 0)


def test_subscription_is_never_a_fixed_asset():
    lines = _build([L(1, "Abonnement logiciel SaaS", "500.00"), L(2, "Honoraires", "500.00")], Decimal("200"))
    assert not any(code.startswith("2") for code in lines) and "404" not in lines


def test_fixed_asset_threshold_sends_small_equipment_to_expenses():
    lines = _build([L(1, "Ordinateur portable", "300.00"), L(2, "Location de salle", "700.00")], Decimal("200"),
                   builder=_builder(fixed_asset_min_amount=Decimal("500")))
    assert "2182" not in lines and "404" not in lines
    assert lines["622"] == (Decimal("300.00"), 0)  # sous le seuil : charge, compte de la facture


def test_single_nature_invoice_is_not_ventilated():
    # Tout va au même compte : l'écriture au niveau facture (inchangée) est conservée
    assert _build([L(1, "Honoraires janvier", "500.00"), L(2, "Honoraires février", "500.00")],
                  Decimal("200")) is None


def test_lines_without_keywords_follow_the_invoice_account():
    lines = _build([L(1, "Prestation XZ-12", "600.00"), L(2, "Ordinateur portable", "400.00")], Decimal("200"))
    assert lines["622"] == (Decimal("600.00"), 0) and lines["2182"] == (Decimal("400.00"), 0)


def test_discount_bigger_than_a_charge_is_not_ventilated():
    assert _build([L(1, "Honoraires", "100.00"), L(2, "Remise exceptionnelle honoraires", "-150.00"),
                   L(3, "Ordinateur portable", "1050.00")], Decimal("200")) is None


def test_credit_note_reverses_every_side():
    lines = _build([L(1, "Honoraires", "500.00"), L(2, "Ordinateur portable", "500.00")], Decimal("200"),
                   reverse_sides=True)
    assert lines["622"] == (0, Decimal("500.00")) and lines["404"] == (Decimal("600.00"), 0)


# Facture FV-2024-0150 (restaurant) : matériel de cuisine + denrées, deux taux de TVA
FV_0150 = [
    L(1, "MAT-INOX4 Plan de travail inox brossé 2000x600mm", "1780.00"),
    L(2, "FOUR-PRO Four mixte professionnel 6 niveaux GN1/1", "3910.00"),
    L(3, "HUILE-OL5 Huile d'olive vierge extra bidon 5L", "1155.00", "5.5"),
    L(4, "FARINE-T55 Farine de blé T55 sac 25kg", "497.50", "5.5"),
]
IMMO = MG_RULES[2]


def test_kitchen_equipment_is_capitalised_and_food_is_a_purchase():
    entry = _builder().build(
        lines=FV_0150, fallback_rule=IMMO, fallback_account="218", total_vat=Decimal("1228.89"),
        invoice_id=1, company_id=1, entry_date=date(2024, 9, 6), label="Facture FV-2024-0150")
    assert {l.account_code: (l.debit, l.credit) for l in entry.lines} == {
        "215": (Decimal("5690.00"), 0),     # plan de travail + four
        "607": (Decimal("1652.50"), 0),     # huile + farine
        "4456": (Decimal("1228.89"), 0),    # 20 % × 5 690,00 + 5,5 % × 1 652,50
        "404": (0, Decimal("6828.00")),     # matériel : 5 690,00 + 1 138,00
        "401": (0, Decimal("1743.39")),     # denrées : 1 652,50 + 90,89
    }


def test_short_keywords_match_whole_words_only():
    from app.infrastructure.rules.line_entry import _hits
    assert _hits(["four"], "four mixte") == 1
    assert _hits(["four"], "fours a pizza") == 1
    assert _hits(["four"], "fournitures de bureau") == 0
    assert _hits(["four"], "fournisseur") == 0
    assert _hits(["sel"], "sellerie") == 0
