"""Tests unitaires du domaine — zéro dépendance externe (pas de BDD, pas
de mocks lourds) : c'est l'intérêt d'une Clean Architecture bien posée."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain.entities import EntryLine, EntryStatus, JournalEntry
from app.domain.rules import BalanceValidator, UnbalancedEntryError, VATCalculator


def make_balanced_entry() -> JournalEntry:
    return JournalEntry(
        invoice_id=1, company_id=1, entry_date=date(2026, 1, 15), label="Facture test",
        lines=[
            EntryLine(account_id=1, account_code="606", label="Achat",
                     debit=Decimal("100.00"), credit=Decimal("0")),
            EntryLine(account_id=2, account_code="4456", label="TVA déductible",
                     debit=Decimal("20.00"), credit=Decimal("0")),
            EntryLine(account_id=3, account_code="401", label="Fournisseur",
                     debit=Decimal("0"), credit=Decimal("120.00")),
        ])


class TestBalanceValidator:
    def test_balanced_entry_passes(self):
        entry = make_balanced_entry()
        BalanceValidator.validate(entry)  # ne doit lever aucune exception

    def test_unbalanced_entry_raises(self):
        entry = make_balanced_entry()
        entry.lines[0].debit = Decimal("999.00")  # casse l'équilibre
        with pytest.raises(UnbalancedEntryError):
            BalanceValidator.validate(entry)

    def test_single_line_entry_raises(self):
        entry = JournalEntry(invoice_id=1, company_id=1, entry_date=date(2026, 1, 15), label="x",
                             lines=[EntryLine(account_id=1, account_code="606",
                                              label="x", debit=Decimal("100"))])
        with pytest.raises(UnbalancedEntryError, match="au moins deux lignes"):
            BalanceValidator.validate(entry)

    def test_line_with_both_debit_and_credit_raises(self):
        entry = make_balanced_entry()
        entry.lines[0].credit = Decimal("50.00")  # ligne invalide : D et C non nuls
        with pytest.raises(UnbalancedEntryError, match="soit au débit"):
            BalanceValidator.validate(entry)

    def test_line_with_neither_debit_nor_credit_raises(self):
        entry = make_balanced_entry()
        entry.lines[0].debit = Decimal("0")  # ligne invalide : ni D ni C
        with pytest.raises(UnbalancedEntryError):
            BalanceValidator.validate(entry)

    def test_entry_status_defaults_to_proposed(self):
        assert make_balanced_entry().status == EntryStatus.PROPOSED


class TestVATCalculator:
    def setup_method(self):
        self.calc = VATCalculator(Decimal("0.20"))

    def test_vat_from_ht(self):
        assert self.calc.vat_from_ht(Decimal("100")) == Decimal("20.00")

    def test_ttc_from_ht(self):
        assert self.calc.ttc_from_ht(Decimal("100")) == Decimal("120.00")

    def test_ht_from_ttc(self):
        assert self.calc.ht_from_ttc(Decimal("120")) == Decimal("100.00")

    def test_resolve_missing_vat(self):
        ht, vat, ttc = self.calc.resolve_missing(Decimal("100"), None, Decimal("120"))
        assert (ht, vat, ttc) == (Decimal("100"), Decimal("20.00"), Decimal("120"))

    def test_resolve_missing_ht(self):
        ht, vat, ttc = self.calc.resolve_missing(None, Decimal("20"), Decimal("120"))
        assert (ht, vat, ttc) == (Decimal("100.00"), Decimal("20"), Decimal("120"))

    def test_resolve_missing_ttc(self):
        ht, vat, ttc = self.calc.resolve_missing(Decimal("100"), Decimal("20"), None)
        assert (ht, vat, ttc) == (Decimal("100"), Decimal("20"), Decimal("120.00"))

    def test_resolve_from_ttc_only_assumes_normal_rate_when_vat_mentioned(self):
        """Une ancre TVA a été repérée sur la facture (montant illisible) :
        on suppose une extraction incomplète et on applique le taux normal."""
        ht, vat, ttc = self.calc.resolve_missing(None, None, Decimal("120"),
                                                 vat_evidence_found=True)
        assert ttc == Decimal("120")
        assert ht == Decimal("100.00")
        assert vat == Decimal("20.00")

    def test_resolve_from_ttc_only_assumes_no_vat_when_not_mentioned(self):
        """Aucune ancre TVA sur la facture : on ne fabrique pas de taxe —
        la facture est traitée comme exonérée (HT = TTC, TVA = 0)."""
        ht, vat, ttc = self.calc.resolve_missing(None, None, Decimal("120"),
                                                 vat_evidence_found=False)
        assert (ht, vat, ttc) == (Decimal("120"), Decimal("0.00"), Decimal("120"))

    def test_resolve_from_ht_only_assumes_normal_rate_when_vat_mentioned(self):
        ht, vat, ttc = self.calc.resolve_missing(Decimal("100"), None, None,
                                                 vat_evidence_found=True)
        assert (ht, vat, ttc) == (Decimal("100"), Decimal("20.00"), Decimal("120.00"))

    def test_resolve_from_ht_only_assumes_no_vat_when_not_mentioned(self):
        ht, vat, ttc = self.calc.resolve_missing(Decimal("100"), None, None,
                                                 vat_evidence_found=False)
        assert (ht, vat, ttc) == (Decimal("100"), Decimal("0.00"), Decimal("100"))

    def test_resolve_two_known_derives_zero_vat_by_pure_arithmetic(self):
        """HT et TTC égaux (facture sans TVA) : la TVA déduite est 0, sans
        aucune hypothèse de taux — cas déjà correct avant la correction."""
        ht, vat, ttc = self.calc.resolve_missing(Decimal("100"), None, Decimal("100"))
        assert (ht, vat, ttc) == (Decimal("100"), Decimal("0.00"), Decimal("100"))

    def test_resolve_all_none_returns_none(self):
        assert self.calc.resolve_missing(None, None, None) is None


class TestSubtotalBeforeDiscount:
    """Facture sans ligne « Total HT » : « Sous-total 131 000 », « Remise − 6 000 »,
    « Total à payer 125 000 ». Le sous-total lu comme HT donnait une TVA de −6 000
    (écriture refusée : « Montant VAT négatif »)."""

    def setup_method(self):
        self.calc = VATCalculator(Decimal("0.20"))

    def test_no_vat_mention_net_is_the_amount_to_pay(self):
        assert self.calc.resolve_missing(Decimal("131000"), None, Decimal("125000"),
                                         vat_evidence_found=False) == (
            Decimal("125000"), Decimal("0.00"), Decimal("125000"))

    def test_vat_mentioned_without_amount_rebuilds_ht_from_the_net(self):
        ht, vat, ttc = self.calc.resolve_missing(Decimal("131000"), None, Decimal("120000"),
                                                 vat_evidence_found=True)
        assert (ht, vat, ttc) == (Decimal("100000.00"), Decimal("20000.00"), Decimal("120000"))

    def test_a_vat_is_never_negative(self):
        for evidence in (True, False):
            _, vat, _ = self.calc.resolve_missing(Decimal("500"), None, Decimal("400"),
                                                  vat_evidence_found=evidence)
            assert vat >= 0

    def test_regular_vat_derivation_is_unchanged(self):
        assert self.calc.resolve_missing(Decimal("100"), None, Decimal("120")) == (
            Decimal("100"), Decimal("20.00"), Decimal("120"))
