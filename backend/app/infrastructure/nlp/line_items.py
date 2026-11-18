"""Extraction des lignes de détail d'une facture (tableau articles / prestations).

Étape 1 de la ventilation par ligne : les lignes sont extraites et
enregistrées pour être consultées, mais ne pilotent PAS encore l'écriture
comptable (qui reste générée au niveau de la facture, comme avant). Un échec
ou une lecture partielle n'a donc aucun effet sur le reste du pipeline.

Principe :
1. on reconstitue les lignes visuelles (mêmes coordonnées verticales) ;
2. le tableau commence à une ligne d'en-tête (« Désignation … Montant ») et
   s'arrête au premier libellé de totaux (« Total HT », « TVA », …) ;
3. chaque ligne du tableau = une désignation suivie d'une suite de nombres.
   Parmi ces nombres, on cherche l'interprétation cohérente
   quantité × prix unitaire = montant, ce qui lève aussi l'ambiguïté des
   séparateurs de milliers (« 2 150,00 » : 2 × 150,00 ou 2 150,00 ?).
"""
import itertools
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.domain.entities import InvoiceLine
from app.domain.ports import LineItemExtractor, OcrBlock, OcrResult
from app.infrastructure.nlp.extractor import (
    _fix_numeric_ocr_errors, _visual_lines, normalize_amount,
)

HEADER_DESC_RE = re.compile(
    r"d[ée]signation|description|libell[ée]|\barticles?\b|prestations?|\bproduits?\b"
    r"|\bitems?\b|d[ée]tail|\bnature\b", re.IGNORECASE)
HEADER_NUM_RE = re.compile(
    r"montant|\btotal\b|\bprix\b|\bp\.?\s*u\b|amount|price|qt[ée]|quantit|\bqty\b|\bh\.?t\b",
    re.IGNORECASE)
# Début de la zone des totaux : fin du tableau des lignes
END_RE = re.compile(
    r"^\s*(?:total|sous[\s-]*total|sub[\s-]*total|montant\s*(?:h\.?t|ttc|total|tva|net)"
    r"|net\s*[àa]\s*payer|t\.?v\.?a\b|vat\b|taxes?\b|base\s*(?:h\.?t|imposable)"
    r"|r[ée]capitulatif|amount\s*due|balance\s*due|grand\s*total|acompte|remise\s*globale"
    r"|conditions|arr[êe]t[ée]e?\s)", re.IGNORECASE)

UNIT_RE = re.compile(
    r"^(?:€|\$|£|eur|usd|gbp|mga|ar|ariary|u|un|unit[ée]s?|pc[es]?|pcs|h|hrs?|heures?|j|jours?"
    r"|mois|an|ans|x|forfait|ens|lot|kg|m|m2|m²|l)$", re.IGNORECASE)
# Intitulé de section dans le tableau : « A. Produits… », « 2) Prestations », « Sous-total »
SECTION_TITLE_RE = re.compile(r"^\s*(?:[A-Z]|\d{1,2})[.)]\s+\S|.*\b(?:sous[\s-]*total|subtotal)\b",
                              re.IGNORECASE)
SECTION_VAT_RE = re.compile(r"\b(?:t\.?v\.?a|vat)\b\D{0,4}(\d+(?:[.,]\d+)?)\s*%", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*\d{1,2}\.\s+[A-Za-zÀ-ÿ]{3}")
# « Page 1 of 2 », ou « … RCS 2006 B 00152 | Page 1 » en pied de page
PAGE_FOOTER_RE = re.compile(r"\bpage\s+\d+\s*(?:(?:of|sur|/)\s*\d+|$)", re.IGNORECASE)
TOTAL_WORD_RE = re.compile(r"\b(?:total|subtotal|sous-total)\b", re.IGNORECASE)
MAX_DESCRIPTION_WORDS = 30   # au-delà : un paragraphe (conditions générales), pas une ligne
MAX_CONTINUATION_WORDS = 15

# Cellule vide d'une colonne (« — » dans la colonne Remise), séparateur « € / hr »
EMPTY_CELL_RE = re.compile(r"^[—–\-/|]$")
# Unité libre écrite après la quantité (« 2 demi-journée », « 4 billet ») : un mot court
UNIT_WORD_RE = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.\-]{0,14}$")
NUMBER_RE = re.compile(r"^([-−–]?)[€$£]?(\d[\d.,]*)[€$£]?$")
# « 20 % », et « -5 % » dans une colonne Remise (le signe ne change pas la remise)
PERCENT_RE = re.compile(r"^[-−–]?(\d+(?:[.,]\d+)?)\s*%$")
THOUSANDS_TAIL_RE = re.compile(r"^\d{3}(?:[.,]\d{1,2})?$")
THOUSANDS_HEAD_RE = re.compile(r"^[-−–]?\d{1,3}$")

# Taux de TVA plausibles (France, Madagascar, et taux usuels) : sert à reconnaître
# une colonne « TVA » écrite sans le signe %.
VAT_RATES = {Decimal(r) for r in ("0", "2.1", "5.5", "7", "8.5", "10", "13", "19.6", "20")}
MAX_MERGE_GAPS = 8  # au-delà, combinatoire trop large : fusion maximale uniquement


@dataclass
class _Atom:
    text: str
    block: int  # indice du bloc OCR dans la ligne (une cellule de tableau ≈ un bloc)


@dataclass
class _Token:
    value: Decimal
    percent: bool
    start: int   # indice du premier atome
    merges: int  # nombre de groupes de milliers fusionnés
    currency: bool = False  # écrit avec un symbole monétaire (« €160.00 ») : un prix, pas une quantité


@dataclass
class _Reading:
    """Une interprétation de la suite de nombres d'une ligne."""
    start: int                      # indice de l'atome où commencent les nombres retenus
    amount: Decimal
    quantity: Decimal | None
    unit_price: Decimal | None
    vat_rate: Decimal | None
    consistent: bool                # quantité × prix unitaire = montant
    strays: int                     # nombres non expliqués (rendus à la désignation)
    merges: int


def _to_decimal(raw: str) -> Decimal | None:
    normalized = normalize_amount(raw)
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= max(Decimal("0.02"), abs(b) * Decimal("0.005"))


class TableLineExtractor(LineItemExtractor):
    """Implémentation du port LineItemExtractor sur les blocs OCR positionnés."""

    def extract(self, ocr_result: OcrResult) -> list[InvoiceLine]:
        blocks = [OcrBlock(text=_fix_numeric_ocr_errors(b.text), bbox=b.bbox,
                           confidence=b.confidence) for b in ocr_result.blocks]
        lines: list[InvoiceLine] = []
        self.section_anomalies: list[tuple[str, Decimal, Decimal]] = []
        in_table = False
        amount_left = 0.0
        visual_lines = _visual_lines(blocks)
        skip = 0
        for index, visual_line in enumerate(visual_lines):
            if skip:
                skip -= 1
                continue
            text = " ".join(b.text for b in visual_line)
            header_size = self._header_size(visual_lines, index)
            if header_size:
                in_table = True  # (ré)ouverture : en-tête répété sur une page suivante
                skip = header_size - 1
                # Bord gauche de la dernière colonne (« Montant ») : le montant d'une
                # ligne s'y trouve toujours
                last = max((b for line in visual_lines[index:index + header_size] for b in line),
                           key=lambda b: max(pt[0] for pt in b.bbox))
                amount_left = min(pt[0] for pt in last.bbox)
                continue
            if not in_table:
                continue
            if self._ends_table(visual_line, text):
                in_table = False
                continue
            # Un nombre qui n'atteint pas la colonne des montants appartient à la
            # désignation (« 4 feux gaz, inox, garantie 2 ans ») : pas une ligne
            reaches_amounts = max(pt[0] for pt in visual_line[-1].bbox) >= amount_left
            item = self._parse_row(visual_line) if reaches_amounts else None
            if item is not None:
                item.line_no = len(lines) + 1
                lines.append(item)
            elif lines and self._is_continuation(visual_line):
                # Désignation sur plusieurs lignes : texte sans aucun nombre
                lines[-1].description = f"{lines[-1].description} {text.strip()}"[:500]
        return self._drop_subtotals(lines)

    def _drop_subtotals(self, lines: list[InvoiceLine]) -> list[InvoiceLine]:
        """Intitulés de section (« B. Équipements (TVA 20 %)  27 800 000 ») et
        sous-totaux : une ligne sans quantité ni prix dont le montant est la somme
        des lignes qui la suivent (intitulé) ou qui la précèdent (sous-total). Les
        garder compterait ces montants deux fois. Un intitulé EXPLICITE (« A. … »)
        est retiré même si son montant est faux : l'écart est noté dans
        `self.section_anomalies` (sous-total ≠ somme des lignes, contrôle bloquant)."""
        def plain(line: InvoiceLine) -> bool:
            return line.quantity is None and line.unit_price is None

        def group(indices) -> list[int]:
            members = []
            for j in indices:
                if plain(lines[j]):
                    break
                members.append(j)
            return members

        def total(members) -> Decimal:
            return sum((lines[j].amount for j in members), Decimal("0"))

        kept = []
        for i, line in enumerate(lines):
            if plain(line):
                explicit = bool(SECTION_TITLE_RE.match(line.description))
                after, before = group(range(i + 1, len(lines))), group(range(i - 1, -1, -1))
                matches_after = (len(after) >= 2 or (after and explicit)) and _close(total(after), line.amount)
                matches_before = (len(before) >= 2 or (before and explicit)) and _close(total(before), line.amount)
                if matches_after or (explicit and after and not matches_before):
                    # Intitulé de section : son taux (« (TVA 20 %) ») vaut pour ses lignes
                    rate = SECTION_VAT_RE.search(line.description)
                    for j in after:
                        if rate and lines[j].vat_rate is None:
                            lines[j].vat_rate = Decimal(rate.group(1).replace(",", "."))
                    if not matches_after:
                        self.section_anomalies.append(
                            (line.description, line.amount, total(after)))
                    continue
                if matches_before:
                    continue
            kept.append(line)
        for no, line in enumerate(kept, start=1):
            line.line_no = no
        return kept

    # ----------------------------------------------------------- Tableau
    def _header_size(self, visual_lines: list[list[OcrBlock]], index: int) -> int:
        """Nombre de lignes visuelles de l'en-tête de tableau commençant ici (0 si
        aucun). Un en-tête peut s'étaler sur 2-3 lignes (« RATE / | QTY / » puis
        « DESCRIPTION | DISCOUNT ») : on teste les fenêtres de 1 à 3 lignes."""
        text = ""
        for size in range(1, 4):
            if index + size > len(visual_lines):
                return 0
            line = visual_lines[index + size - 1]
            if self._has_amount(line):
                return 0
            line_text = " ".join(b.text for b in line)
            if size == 1 and not (HEADER_DESC_RE.search(line_text) or HEADER_NUM_RE.search(line_text)):
                return 0  # un en-tête commence par un intitulé de colonne (pas « MVola : 034… »)
            text += " " + line_text
            if HEADER_DESC_RE.search(text) and HEADER_NUM_RE.search(text):
                return size
        return 0

    @staticmethod
    def _ends_table(visual_line: list[OcrBlock], text: str) -> bool:
        first = visual_line[0].text
        return bool(END_RE.search(first)
                    or SECTION_RE.search(first)                       # « 4. Conditions générales »
                    or PAGE_FOOTER_RE.search(text)                    # « Page 1 of 2 »
                    or (TOTAL_WORD_RE.search(first) and len(first.split()) <= 5))  # « Gross Services Total: »

    # ------------------------------------------------------------ Lignes
    @staticmethod
    def _has_amount(visual_line: list[OcrBlock]) -> bool:
        return any(re.search(r"\d[.,]\d{2}\b", b.text) for b in visual_line)

    @staticmethod
    def _is_continuation(visual_line: list[OcrBlock]) -> bool:
        text = " ".join(b.text for b in visual_line)
        return (bool(re.search(r"[A-Za-zÀ-ÿ]{2}", text)) and not re.search(r"\d[.,]\d{2}\b", text)
                and len(text.split()) <= MAX_CONTINUATION_WORDS)

    def _parse_row(self, visual_line: list[OcrBlock]) -> InvoiceLine | None:
        atoms = [_Atom(word, i) for i, block in enumerate(visual_line)
                 for word in block.text.split()]
        # « 20 % » : le signe % isolé se rattache au nombre qui précède
        merged_atoms: list[_Atom] = []
        for atom in atoms:
            if atom.text == "%" and merged_atoms and NUMBER_RE.match(merged_atoms[-1].text):
                merged_atoms[-1] = _Atom(merged_atoms[-1].text + "%", merged_atoms[-1].block)
            else:
                merged_atoms.append(atom)
        atoms = merged_atoms

        run_start = len(atoms)
        while run_start > 0:
            text = atoms[run_start - 1].text
            if self._is_numeric_atom(text):
                run_start -= 1
            elif (run_start < len(atoms) and run_start >= 2 and UNIT_WORD_RE.match(text)
                  and NUMBER_RE.match(atoms[run_start - 2].text)):
                run_start -= 1  # unité libre entre la quantité et le prix
            else:
                break
        if run_start == 0 or run_start == len(atoms):
            return None  # pas de désignation, ou pas de nombres

        reading = self._best_reading(atoms, run_start)
        if reading is None:
            return None
        description = " ".join(a.text for a in atoms[:reading.start]).strip(" -:|")
        if not re.search(r"[A-Za-zÀ-ÿ]{2}", description) or len(description.split()) > MAX_DESCRIPTION_WORDS:
            return None
        confidence = min(b.confidence for b in visual_line) * (1.0 if reading.consistent else 0.7)
        xs = [pt[0] for b in visual_line for pt in b.bbox]
        ys = [pt[1] for b in visual_line for pt in b.bbox]
        return InvoiceLine(
            line_no=0, description=description[:500], amount=reading.amount,
            quantity=reading.quantity, unit_price=reading.unit_price,
            vat_rate=reading.vat_rate, confidence=round(confidence, 4),
            source_bbox=[[min(xs), min(ys)], [max(xs), min(ys)],
                         [max(xs), max(ys)], [min(xs), max(ys)]])

    @staticmethod
    def _is_numeric_atom(text: str) -> bool:
        return bool(NUMBER_RE.match(text) or PERCENT_RE.match(text) or UNIT_RE.match(text)
                    or EMPTY_CELL_RE.match(text))

    # ------------------------------------------------------ Interprétation
    def _best_reading(self, atoms: list[_Atom], run_start: int) -> _Reading | None:
        best: _Reading | None = None
        for tokens in self._tokenizations(atoms, run_start):
            reading = self._interpret(tokens)
            if reading is None:
                continue
            key = (reading.consistent, -reading.strays, reading.merges)
            if best is None or key > (best.consistent, -best.strays, best.merges):
                best = reading
        return best

    def _tokenizations(self, atoms: list[_Atom], run_start: int):
        """Toutes les lectures possibles des séparateurs de milliers (« 1 390,00 »
        = un nombre, ou « 1 » puis « 390,00 »), bornées en nombre."""
        indexed = [(i, atoms[i]) for i in range(run_start, len(atoms))
                   if NUMBER_RE.match(atoms[i].text) or PERCENT_RE.match(atoms[i].text)]
        gaps = [k for k in range(len(indexed) - 1)
                if indexed[k + 1][0] == indexed[k][0] + 1                 # atomes consécutifs
                and indexed[k][1].block == indexed[k + 1][1].block        # même cellule
                and THOUSANDS_HEAD_RE.match(indexed[k][1].text)
                and THOUSANDS_TAIL_RE.match(indexed[k + 1][1].text)]
        if len(gaps) > MAX_MERGE_GAPS:
            choices = [(True,) * len(gaps)]
        else:
            choices = itertools.product((False, True), repeat=len(gaps))
        for choice in choices:
            merge_after = {g for g, do_merge in zip(gaps, choice) if do_merge}
            tokens: list[_Token] = []
            k = 0
            while k < len(indexed):
                start_k, parts = k, [indexed[k][1].text]
                while k in merge_after:
                    k += 1
                    parts.append(indexed[k][1].text)
                token = self._make_token(" ".join(parts), indexed[start_k][0], len(parts) - 1)
                if token is None:
                    break
                tokens.append(token)
                k += 1
            else:
                yield tokens

    @staticmethod
    def _make_token(raw: str, start: int, merges: int) -> _Token | None:
        percent = PERCENT_RE.match(raw)
        if percent:
            value = _to_decimal(percent.group(1))
            return _Token(value, True, start, 0) if value is not None else None
        number = NUMBER_RE.match(raw.replace(" ", "")) if merges else NUMBER_RE.match(raw)
        if not number:
            return None
        value = _to_decimal(number.group(2))
        if value is None:
            return None
        return _Token(-value if number.group(1) else value, False, start, merges,
                      currency=bool(re.search(r"[€$£]", raw)))

    @staticmethod
    def _interpret(tokens: list[_Token]) -> _Reading | None:
        money = [t for t in tokens if not t.percent]
        if not money:
            return None
        amount = money[-1]
        merges = sum(t.merges for t in tokens)
        all_percents = [t.value for t in tokens if t.percent]
        vat_percents = [p for p in all_percents if p in VAT_RATES]
        vat_rate = vat_percents[-1] if vat_percents else None

        def reading(start_index: int, quantity, unit_price, rate, consistent) -> _Reading:
            return _Reading(start=money[start_index].start, amount=amount.value,
                            quantity=quantity, unit_price=unit_price, vat_rate=rate,
                            consistent=consistent, strays=start_index, merges=merges)

        candidates: list[_Reading] = []
        n = len(money)
        # Une paire (quantité, prix unitaire) avant le montant, avec entre les deux
        # d'éventuelles colonnes : taux de TVA sans %, montant brut, remise.
        for i in range(n - 2):
            q, pu = money[i], money[i + 1]
            gross = q.value * pu.value
            between = [t.value for t in money[i + 2:n - 1]]
            rate = vat_rate
            if _close(gross, amount.value):
                consistent = True
                if vat_rate is None and len(between) == 1 and between[0] in VAT_RATES \
                        and not _close(between[0], gross):
                    rate = between[0]  # colonne TVA écrite sans le signe %
            elif any(_close(gross, g) and any(_close(g - d, amount.value) for d in between[j + 1:])
                     for j, g in enumerate(between)):
                consistent = True  # brut − remise (en montant) = net
            else:
                # remise en % : quantité × prix × (1 − remise %) = montant ;
                # le taux de TVA est alors l'autre pourcentage de la ligne
                discount = next((p for p in all_percents
                                 if _close(gross * (1 - p / 100), amount.value)), None)
                consistent = discount is not None
                if consistent:
                    others = list(all_percents)
                    others.remove(discount)
                    others = [p for p in others if p in VAT_RATES]
                    rate = others[-1] if others else None
            if not consistent:
                continue
            quantity, unit_price = q.value, pu.value
            if (q.currency and not pu.currency) or (
                    quantity != quantity.to_integral_value() and unit_price == unit_price.to_integral_value()):
                quantity, unit_price = unit_price, quantity  # colonnes « prix | qté »
            candidates.append(reading(i, quantity, unit_price, rate, True))
        # prix unitaire = montant (quantité 1 implicite)
        if n >= 2 and _close(money[n - 2].value, amount.value):
            candidates.append(reading(n - 2, None, money[n - 2].value, vat_rate, True))
        if candidates:
            return min(candidates, key=lambda r: r.strays)
        return reading(n - 1, None, None, vat_rate, False)
