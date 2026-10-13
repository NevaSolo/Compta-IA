"""Règles métier pures du domaine comptable.

Ces règles sont déterministes et ne dépendent d'aucun modèle statistique :
elles garantissent la conformité au principe de la partie double
(PCG malgache 2005, art. 420-1 : « Les écritures comptables sont passées
selon le système dit en partie double »)."""
from decimal import Decimal, ROUND_HALF_UP

from app.domain.entities import JournalEntry


class UnbalancedEntryError(Exception):
    """Levée quand une écriture viole l'invariant Débit = Crédit."""


class BalanceValidator:
    """Garantit l'invariant fondamental de la partie double.

    Appelé deux fois dans le cycle de vie d'une écriture :
    1. à la génération par le moteur de règles ;
    2. à la validation finale par le comptable (qui a pu modifier des montants).
    """

    @staticmethod
    def validate(entry: JournalEntry) -> None:
        if len(entry.lines) < 2:
            raise UnbalancedEntryError(
                "Une écriture comptable doit comporter au moins deux lignes (partie double)."
            )
        for line in entry.lines:
            if not line.is_valid_side():
                raise UnbalancedEntryError(
                    f"Ligne '{line.label}' invalide : une ligne est soit au débit, "
                    f"soit au crédit (débit={line.debit}, crédit={line.credit})."
                )
        if not entry.is_balanced():
            raise UnbalancedEntryError(
                f"Écriture déséquilibrée : total débit {entry.total_debit()} "
                f"≠ total crédit {entry.total_credit()}."
            )


class VATCalculator:
    """Calculs de TVA déterministes (taux normal 20 % à Madagascar).
    Arrondi commercial ROUND_HALF_UP à 2 décimales."""

    def __init__(self, rate: Decimal = Decimal("0.20")):
        self.rate = rate

    def _round(self, amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def vat_from_ht(self, ht: Decimal) -> Decimal:
        return self._round(ht * self.rate)

    def ttc_from_ht(self, ht: Decimal) -> Decimal:
        return self._round(ht * (1 + self.rate))

    def ht_from_ttc(self, ttc: Decimal) -> Decimal:
        return self._round(ttc / (1 + self.rate))

    def resolve_missing(self, ht: Decimal | None, vat: Decimal | None,
                        ttc: Decimal | None,
                        vat_evidence_found: bool = True
                        ) -> tuple[Decimal, Decimal, Decimal] | None:
        """Reconstitue le montant manquant.

        Quand deux des trois montants sont connus, le troisième se déduit
        par simple arithmétique (aucune hypothèse de taux nécessaire) — ce
        qui gère correctement, sans cas particulier, les factures sans TVA
        où HT = TTC (la TVA déduite vaut alors 0).

        Quand un seul montant est connu, `vat_evidence_found` indique si
        l'extracteur a repéré une mention de TVA sur la facture (ancre
        « TVA »/« VAT », même sans montant exploitable) :
        - si oui, on suppose une extraction incomplète et on applique le
          taux normal configuré, comme avant ;
        - si non, on ne fabrique JAMAIS une taxe absente du document —
          de nombreux fournisseurs (micro-entreprises, régimes
          d'exonération, factures étrangères) n'appliquent aucune TVA.
          On retient alors HT = TTC et TVA = 0.
        """
        if ht is not None and ttc is not None and vat is None:
            derived_vat = self._round(ttc - ht)
            if derived_vat < 0:
                # Une TVA ne peut pas être négative : le « HT » lu est en réalité un sous-total
                # AVANT remise (facture sans ligne « Total HT » : « Sous-total 131 000 »,
                # « Remise − 6 000 », « Total à payer 125 000 »). Le net est le TTC lu.
                if vat_evidence_found:
                    net = self.ht_from_ttc(ttc)
                    return net, self._round(ttc - net), ttc
                return ttc, Decimal("0.00"), ttc
            return ht, derived_vat, ttc
        if ht is not None and vat is not None and ttc is None:
            return ht, vat, self._round(ht + vat)
        if ttc is not None and vat is not None and ht is None:
            return self._round(ttc - vat), vat, ttc
        if ht is not None and vat is not None and ttc is not None:
            return ht, vat, ttc
        if ttc is not None:  # un seul montant connu : HT et TVA absents
            if vat_evidence_found:
                ht_calc = self.ht_from_ttc(ttc)
                return ht_calc, self._round(ttc - ht_calc), ttc
            return ttc, Decimal("0.00"), ttc  # aucune TVA constatée : exonération supposée
        if ht is not None:  # un seul montant connu : TTC et TVA absents
            if vat_evidence_found:
                vat_calc = self.vat_from_ht(ht)
                return ht, vat_calc, self._round(ht + vat_calc)
            return ht, Decimal("0.00"), ht
        return None
