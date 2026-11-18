"""Contrôles de la facture avant génération de l'écriture.

Chaque contrôle renvoie une anomalie classée :
- BLOQUANT : l'écriture n'est pas générée (la facture passe en erreur, avec le motif) ;
- ALERTE   : l'écriture est proposée, mais signalée au comptable (validation humaine).

Les contrôles ne portent que sur ce que la facture permet de vérifier seule
(arithmétique, TVA, remises, acomptes, montant en lettres, dates). Les
rapprochements avec des pièces externes (bon de commande, contrat, historique
de prix, IBAN connu) supposent des données que le système ne détient pas.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.entities import InvoiceLine

BLOCKING = "BLOQUANT"
WARNING = "ALERTE"

# Mention justifiant une TVA à 0 % (exportation, exonération, franchise…)
ZERO_VAT_REASON_RE = re.compile(
    r"export|exon[ée]r|exempt|franchise|hors\s+champ|non\s+assujetti|autoliquidation"
    r"|reverse\s+charge|article\s+\d|art\.\s*\d|intracom", re.IGNORECASE)


@dataclass
class Anomaly:
    code: str
    severity: str
    message: str


@dataclass
class InvoiceFacts:
    """Ce que la lecture de la facture a établi (montants en devise de la facture)."""
    is_credit_note: bool
    currency: str | None
    total_ht: Decimal | None
    total_vat: Decimal | None
    total_ttc: Decimal | None
    invoice_date: date | None
    amounts: dict[str, Decimal] = field(default_factory=dict)   # NET_TO_PAY, DEPOSIT_PAID…
    texts: dict[str, str] = field(default_factory=dict)         # VAT_SUMMARY_RATES, DUE_DATE…
    vat_mismatches: list[str] = field(default_factory=list)     # écarts base × taux ≠ TVA
    lines: list[InvoiceLine] = field(default_factory=list)
    section_anomalies: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    has_nif: bool = True
    full_text: str = ""


def _fmt(value: Decimal) -> str:
    text = f"{value:,.0f}" if value == value.to_integral_value() else f"{value:,.2f}"
    return text.replace(",", " ").replace(".", ",")


def run_controls(facts: InvoiceFacts, today: date, allowed_vat_rates: set[Decimal]) -> list[Anomaly]:
    found: list[Anomaly] = []
    # Ariary : pas de centimes, 1 Ar d'arrondi par ligne au plus ; autres devises : 2 centimes
    unit = Decimal("1") if (facts.currency or "MGA") == "MGA" else Decimal("0.02")

    def add(code: str, severity: str, message: str) -> None:
        found.append(Anomaly(code, severity, message))

    ht, vat, ttc = facts.total_ht, facts.total_vat, facts.total_ttc
    a = facts.amounts
    net, deposit = a.get("NET_TO_PAY"), a.get("DEPOSIT_PAID", Decimal("0"))
    gross, discount = a.get("GROSS_TOTAL_HT"), a.get("GLOBAL_DISCOUNT")

    # ---------------------------------------------------- 1. Arithmétique
    if ht is not None and vat is not None and ttc is not None and abs(ht + vat - ttc) > unit:
        add("TTC_HT_TVA", BLOCKING,
            f"Total TTC {_fmt(ttc)} ≠ Total HT {_fmt(ht)} + TVA {_fmt(vat)} = {_fmt(ht + vat)}")
    if net is not None and ttc is not None and abs(net - (ttc - deposit)) > unit:
        hint = ""
        if deposit and abs(net - (ttc - 2 * deposit)) <= unit:
            hint = " : l'acompte semble déduit deux fois"
        elif deposit and abs(net - ttc) <= unit:
            hint = " : l'acompte n'a pas été déduit"
        add("NET_TO_PAY", BLOCKING,
            f"Net à payer {_fmt(net)} ≠ TTC {_fmt(ttc)} − acompte {_fmt(deposit)} = "
            f"{_fmt(ttc - deposit)}{hint}")
    words = a.get("AMOUNT_IN_WORDS")
    if words is not None:
        # le montant en lettres est celui du net à payer (ou du TTC s'il n'y a pas d'acompte)
        targets = [t for t in (net, ttc, ttc - deposit if ttc is not None else None) if t is not None]
        if targets and all(abs(words - t) > unit for t in targets):
            add("AMOUNT_IN_WORDS", BLOCKING,
                f"Montant en lettres ({_fmt(words)}) ≠ montant en chiffres ({_fmt(targets[0])})")
    if not facts.is_credit_note:
        for label, value in (("Total HT", ht), ("Total TTC", ttc)):
            if value is not None and value <= 0:
                add("NON_POSITIVE", BLOCKING, f"{label} nul ou négatif ({_fmt(value)}) sur une facture")
        for line in facts.lines:
            if (line.quantity is not None and line.quantity <= 0) or \
                    (line.unit_price is not None and line.unit_price < 0):
                add("NON_POSITIVE", BLOCKING,
                    f"Quantité ou prix unitaire négatif ou nul : « {line.description[:60]} »")
    for title, printed, computed in facts.section_anomalies:
        add("SECTION_SUBTOTAL", BLOCKING,
            f"Sous-total « {title[:60]} » {_fmt(printed)} ≠ somme de ses lignes {_fmt(computed)}")
    if gross is not None and len(facts.lines) >= 2:
        lines_total = sum((l.amount for l in facts.lines), Decimal("0"))
        if abs(lines_total - gross) > unit * len(facts.lines):
            add("GROSS_VS_LINES", BLOCKING,
                f"Total HT brut {_fmt(gross)} ≠ somme des lignes {_fmt(lines_total)}")
    if gross is not None and ht is not None and abs(gross - (discount or 0) - ht) > unit:
        add("HT_VS_GROSS", BLOCKING,
            f"Total HT {_fmt(ht)} ≠ HT brut {_fmt(gross)} − remise {_fmt(discount or Decimal('0'))} "
            f"= {_fmt(gross - (discount or 0))}")

    # ---------------------------------------------------- 2. TVA
    for message in facts.vat_mismatches:
        add("VAT_RATE", BLOCKING, message)
    bases, summary_vat = a.get("VAT_SUMMARY_BASES"), a.get("VAT_SUMMARY_VAT")
    if bases is not None and ht is not None and abs(bases - ht) > unit * 3:
        add("VAT_BASES", BLOCKING,
            f"Somme des bases du récapitulatif TVA {_fmt(bases)} ≠ Total HT {_fmt(ht)}")
    if summary_vat is not None and vat is not None and abs(summary_vat - vat) > unit * 3:
        add("VAT_TOTAL", BLOCKING,
            f"Somme des TVA du récapitulatif {_fmt(summary_vat)} ≠ TVA totale {_fmt(vat)}")
    rates = {Decimal(r) for r in facts.texts.get("VAT_SUMMARY_RATES", "").split(";") if r}
    rates |= {l.vat_rate for l in facts.lines if l.vat_rate is not None}
    unknown = sorted(r for r in rates if r not in allowed_vat_rates)
    if unknown:
        add("VAT_RATE_UNKNOWN", BLOCKING,
            "Taux de TVA hors référentiel : " + ", ".join(f"{r.normalize():f} %" for r in unknown))
    if Decimal("0") in rates and not ZERO_VAT_REASON_RE.search(facts.full_text):
        add("VAT_ZERO_REASON", WARNING, "TVA à 0 % sans mention du motif (exportation, exonération…)")

    # ---------------------------------------- 3. Remises, acomptes
    discount_rate = a.get("GLOBAL_DISCOUNT_RATE")
    base = gross if gross is not None else (
        sum((l.amount for l in facts.lines), Decimal("0")) if facts.lines else None)
    if discount is not None and discount_rate is not None and base:
        expected = (base * discount_rate / 100).quantize(Decimal("0.01"))
        if abs(expected - discount) > unit * 2:
            hint = " : remise comptée deux fois" if abs(discount - 2 * expected) <= unit * 2 else ""
            add("DISCOUNT_RATE", BLOCKING,
                f"Remise annoncée {discount_rate.normalize():f} % de {_fmt(base)} = {_fmt(expected)}, "
                f"montant déduit {_fmt(discount)}{hint}")
    if deposit and ttc is not None and deposit > ttc:
        add("DEPOSIT_GT_TTC", BLOCKING, f"Acompte {_fmt(deposit)} supérieur au TTC {_fmt(ttc)}")

    # ------------------------------------------------- 5-6. Mentions, dates
    if facts.invoice_date and facts.invoice_date > today:
        add("DATE_FUTURE", BLOCKING, f"Date de facture dans le futur ({facts.invoice_date:%d/%m/%Y})")
    due = facts.texts.get("DUE_DATE")
    if due and facts.invoice_date:
        due_date = date.fromisoformat(due)
        if due_date < facts.invoice_date:
            add("DUE_BEFORE_DATE", BLOCKING,
                f"Échéance ({due_date:%d/%m/%Y}) antérieure à la date de facture "
                f"({facts.invoice_date:%d/%m/%Y})")
    if not facts.has_nif and (facts.currency or "MGA") == "MGA":
        add("NIF_MISSING", WARNING, "NIF du fournisseur non trouvé sur la facture")
    return found
