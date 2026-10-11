"""Devises : liste prise en charge et conversion des montants d'une facture
vers la devise de tenue de comptabilité de l'entreprise."""
from decimal import ROUND_HALF_UP, Decimal

SUPPORTED_CURRENCIES = ("MGA", "EUR", "USD", "GBP", "CHF")
CENT = Decimal("0.01")
# Écart toléré entre « TTC − HT » et la TVA convertie directement : au-delà, ce
# n'est plus un arrondi mais une vraie incohérence, qu'on ne doit pas masquer.
ROUNDING_TOLERANCE = Decimal("0.05")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def convert_amounts(ht: Decimal | None, vat: Decimal | None, ttc: Decimal | None,
                    rate: Decimal) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Convertit (HT, TVA, TTC) au taux donné (1 unité de devise = `rate` unités
    de la devise de l'entreprise). HT et TTC sont arrondis séparément ; la TVA
    prend le centime d'écart d'arrondi, de sorte que HT + TVA = TTC exactement
    et que l'écriture reste équilibrée."""
    ht_c = money(ht * rate) if ht is not None else None
    ttc_c = money(ttc * rate) if ttc is not None else None
    vat_c = money(vat * rate) if vat is not None else None
    if ht_c is not None and ttc_c is not None:
        difference = ttc_c - ht_c
        if vat_c is None or abs(difference - vat_c) <= ROUNDING_TOLERANCE:
            vat_c = difference
    return ht_c, vat_c, ttc_c
