"""Extraction d'entités hybride (Phase 6, étape 4) :
- regex ancrées sur les COORDONNÉES OCR pour les entités à format fixe
  (montants, dates, NIF, STAT, n° facture) — un montant est associé à son
  libellé s'ils sont alignés sur la même ligne visuelle ;
- spaCy NER (optionnel) + heuristique de zone pour le nom du fournisseur.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.domain.entities import DocumentType, ExtractedEntity, ExtractionMethod
from app.domain.ports import EntityExtractor, OcrBlock, OcrResult

logger = logging.getLogger(__name__)

# ----------------------------------------------------------- Ancres multilingues
ANCHORS = {
    "TOTAL_TTC": [r"total\s*ttc", r"net\s*[àa]\s*payer", r"montant\s*ttc",
                  r"amount\s*due", r"grand\s*total", r"totaly", r"total\s*$",
                  r"total\s*due", r"balance\s*due", r"total\s*payable",
                  r"amount\s*payable", r"total\s*[àa]\s*payer"],
    "TOTAL_HT": [r"total\s*h\.?t", r"montant\s*h\.?t", r"sub\s*-?\s*total",
                 r"total\s*hors\s*taxes?", r"sous\s*-?\s*total", r"total\s*net",
                 r"net\s*total", r"base\s*imposable"],
    "TOTAL_VAT": [r"t\.?v\.?a", r"\bvat\b", r"taxe"],
    "INVOICE_NUMBER": [r"facture\s*(n[°ºo]|num|#)", r"invoice\s*(no|#|number)",
                       r"fact\.?\s*n[°ºo]", r"faktiora", r"\bn[°ºo]?\s*:"],
    "NIF": [r"\bn\.?i\.?f\b"],
    "STAT": [r"\bstat\b"],
    "DATE": [r"\bdate\b", r"\bdaty\b", r"\ble\b\s*:"],
}

# Séparateurs de milliers : espace, point, virgule (format anglo-saxon
# « 115,123.75 »), espaces insécables. Sans la virgule, « 115,123.75 » se
# lisait « 3.75 » : toutes les factures au format international échouaient.
AMOUNT_RE = re.compile(r"(\d{1,3}(?:[ .,  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)")
DATE_RES = [
    re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"),
    re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})\b"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]
MONTHS = {  # fr / en / mg
    "janvier": 1, "january": 1, "janoary": 1, "février": 2, "fevrier": 2,
    "february": 2, "febroary": 2, "mars": 3, "march": 3, "martsa": 3,
    "avril": 4, "april": 4, "aprily": 4, "mai": 5, "may": 5, "mey": 5,
    "juin": 6, "june": 6, "jona": 6, "juillet": 7, "july": 7, "jolay": 7,
    "août": 8, "aout": 8, "august": 8, "aogositra": 8, "septembre": 9,
    "september": 9, "septambra": 9, "octobre": 10, "october": 10, "oktobra": 10,
    "novembre": 11, "november": 11, "novambra": 11, "décembre": 12,
    "decembre": 12, "december": 12, "desambra": 12,
    # abréviations courantes (fr / en) : « 09 Oct 2026 », « 12 sept. 2026 »
    "jan": 1, "janv": 1, "feb": 2, "fev": 2, "fév": 2, "févr": 2, "fevr": 2,
    "mar": 3, "apr": 4, "avr": 4, "jun": 6, "juil": 7, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}
# Date dont les composantes ont été séparées par l'OCR en plusieurs blocs
# (« 17 / 08 » + « 2026 ») puis rejointes par un simple espace : séparateurs
# optionnels, année à 4 chiffres obligatoire pour limiter les faux positifs.
DATE_SPLIT_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]?\s*(\d{1,2})\s*[/\-.]?\s*(20\d{2})(?!\d)")
TEXT_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})(?!\d)")
# Mention d'exonération de TVA : « TVA non applicable, art. 293 B du CGI »,
# « VAT exempt », « exonéré de TVA ». Le nombre qui l'accompagne (ici un
# numéro d'article de loi) n'est PAS un montant de taxe : la TVA vaut 0.
VAT_EXEMPT_RE = re.compile(
    r"(tva|vat|taxe)[^.:;]{0,40}(non\s+applicable|exon[ée]r|exempt)"
    r"|(non\s+applicable|exon[ée]r|exempt)[^.:;]{0,40}(tva|vat)"
    r"|art(?:icle|\.)?\s*293\s*b", re.IGNORECASE)
# --- Choix entre plusieurs montants candidats ---------------------------------
# Une facture comporte souvent plusieurs « totaux » : TTC, net à payer (après
# acompte), net avec escompte, HT avant/après remise... Prendre « le plus bas de
# la page » ou « le plus proche de 70 % de la hauteur » revenait à tirer au sort.
# On classe les libellés (rang 0 = le plus fiable) puis on arbitre par le calcul.
TTC_RANKS = [
    (0, r"total\s*ttc|montant\s*ttc|grand\s*total|total\s*(?:tax|vat)\s*incl|total\s*toutes?\s*taxes"),
    (1, r"net\s*[àa]\s*payer|amount\s*due|total\s*due|balance\s*due|total\s*payable"
        r"|amount\s*payable|total\s*[àa]\s*payer"),
]
HT_RANKS = [
    (2, r"avant\s*remise|before\s*discount|hors\s*remise|\bbrut\b|\bgross\b"),
    (1, r"sub\s*-?\s*total|sous\s*-?\s*total"),
]
VAT_PRIMARY = r"total\s*(?:tva|vat|tax)|montant\s*(?:de\s*la\s*)?(?:tva|vat)|vat\s*amount|tax\s*amount"
# Libellés qui ne désignent jamais le montant cherché : un escompte est
# conditionnel (jamais le TTC), « N° TVA » est un identifiant, pas une taxe.
EXCLUDED_ANCHORS = {
    "TOTAL_TTC": re.compile(r"escompte|early\s*payment|prompt\s*payment|rebate", re.IGNORECASE),
    "TOTAL_VAT": re.compile(r"n\s*[°º]|\bid\b|identif|num[ée]ro|number|siret|siren|registration|intracom",
                            re.IGNORECASE),
}
TOLERANCE = Decimal("0.02")  # écart d'arrondi toléré entre HT + TVA et TTC

# Montants purement informatifs (n'entrent pas dans l'écriture) : montrés au comptable
INFO_ANCHORS = {
    "DEPOSIT_PAID": r"acompte|deposit|advance\s*payment",
    "EARLY_PAYMENT_DISCOUNT": r"escompte|early\s*payment\s*discount",
    "NET_TO_PAY": r"net\s*[àa]\s*payer|reste\s*[àa]\s*payer|amount\s*due|balance\s*due|total\s*due|net\s*payable",
}
# Un « net à payer » assorti d'un escompte est conditionnel : on ne le retient pas.
INFO_EXCLUDED_ANCHORS = {
    "NET_TO_PAY": re.compile(r"escompte|early\s*payment|prompt\s*payment|rebate", re.IGNORECASE),
}

CURRENCY_RE = re.compile(r"(?<![A-Za-z])(ariary|mga|ar|eur|usd|gbp|chf)(?![A-Za-z])|(€|\$|£)", re.IGNORECASE)

# Titres de document et en-têtes de colonne génériques (garde-fou pour
# l'extraction du fournisseur : un bloc "FACTURE", "FACTURE D'AVOIR",
# "VENDEUR"... n'est jamais un nom de tiers, même s'il satisfait par
# ailleurs l'heuristique de position/casse — bug réel corrigé : sur une
# facture d'avoir, l'en-tête de colonne "VENDEUR" précédait le vrai nom
# du fournisseur et était retourné à sa place).
# Étiquettes qui désignent explicitement l'émetteur de la facture (« Vendeur : Boutique X »).
# Elles doivent porter un « : » : un en-tête de colonne « VENDEUR » (nom en dessous, voisin
# « CLIENT » à droite) n'est pas une étiquette de valeur.
SUPPLIER_LABEL_RE = re.compile(
    r"^\s*(?:vendeur|fournisseur|[ée]metteur|[ée]mise\s+par|seller|supplier|vendor|issued\s+by)"
    r"\s*[:：]\s*(?P<value>.*)$", re.IGNORECASE)

DOCUMENT_TITLE_PATTERNS = [
    r"^factures?\b", r"\bavoir\b", r"note\s*de\s*cr[ée]dit", r"credit\s*note",
    r"^devis\b", r"^invoice\b", r"^quotation\b",
    r"^vendeurs?\b", r"^clients?\b", r"^fournisseurs?\b", r"^acheteurs?\b",
    r"^destinataires?\b",
]
AVOIR_RE = re.compile(r"facture\s*d.?avoir|note\s*de\s*cr[ée]dit|credit\s*note|\bavoir\b",
                      re.IGNORECASE)


def detect_document_type(raw_text: str) -> DocumentType:
    """Une facture d'avoir (note de crédit fournisseur) doit générer une
    écriture au sens inversé (cf. RuleEngine.generate_entry) — on la détecte
    tôt, sur le texte OCR brut, pour piloter à la fois ce comportement et
    l'exclusion du titre de la recherche du nom de fournisseur."""
    if AVOIR_RE.search(raw_text or ""):
        return DocumentType.AVOIR
    return DocumentType.FACTURE


def normalize_amount(raw: str) -> str | None:
    """Normalise un montant : gère espace/point comme séparateurs de milliers
    et virgule/point décimal. Ambiguïté résolue par la position : un séparateur
    suivi d'exactement 3 chiffres en fin de groupe = milliers."""
    text = raw.strip().replace(" ", " ")
    text = re.sub(r"[^\d.,\s]", "", text).strip()
    if not text:
        return None
    # dernier séparateur = décimal s'il est suivi de 1 ou 2 chiffres
    match = re.match(r"^([\d\s.,]*?)[.,](\d{1,2})$", text)
    if match:
        integer_part = re.sub(r"[\s.,]", "", match.group(1))
        return f"{integer_part}.{match.group(2)}" if integer_part else None
    return re.sub(r"[\s.,]", "", text) or None


_CONFUSABLE_LETTERS = set("OolISB")  # lettres que l'OCR confond avec des chiffres


def _fix_numeric_ocr_errors(text: str) -> str:
    """Corrections O→0, l/I→1, S→5, B→8 uniquement dans les tokens
    majoritairement numériques (jamais dans le texte : noms propres).

    Un préfixe alphabétique réel suivi d'un séparateur et de chiffres
    (« INV-2026-8849 », « FAC-00045 ») est un code de pièce, pas un nombre
    mal lu : le corriger donnait « 1NV-2026-8849 ». Le préfixe n'est
    préservé que s'il contient une lettre non confondable avec un chiffre,
    pour que « OO-123 » (deux zéros mal lus) reste corrigé."""
    def fix_token(token: str) -> str:
        prefix = re.match(r"^([A-Za-z]{2,})[\-/_.]?\d", token)
        if prefix and not set(prefix.group(1)) <= _CONFUSABLE_LETTERS:
            return token
        digits = sum(ch.isdigit() for ch in token)
        if digits >= max(2, len(token) // 2):
            return (token.replace("O", "0").replace("o", "0")
                    .replace("l", "1").replace("I", "1")
                    .replace("S", "5").replace("B", "8"))
        return token
    return " ".join(fix_token(tok) for tok in text.split(" "))


def _block_center_y(block: OcrBlock) -> float:
    return sum(pt[1] for pt in block.bbox) / len(block.bbox)


def _block_center_x(block: OcrBlock) -> float:
    return sum(pt[0] for pt in block.bbox) / len(block.bbox)


def _block_height(block: OcrBlock) -> float:
    ys = [pt[1] for pt in block.bbox]
    return max(ys) - min(ys)


def _same_visual_line(a: OcrBlock, b: OcrBlock) -> bool:
    """Deux blocs sont sur la même ligne visuelle si leurs centres verticaux
    sont distants de moins d'une demi-hauteur de bloc."""
    tolerance = max(_block_height(a), _block_height(b)) * 0.6
    return abs(_block_center_y(a) - _block_center_y(b)) <= tolerance


def _matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in patterns)


def _visual_lines(blocks: list[OcrBlock]) -> list[list[OcrBlock]]:
    """Regroupe les blocs en lignes visuelles (de gauche à droite).

    L'OCR découpe souvent une même ligne en plusieurs blocs (« 17 / 08 » puis
    « 2026 » ; cellules d'un tableau) : les entités qui s'étalent sur
    plusieurs blocs, comme une date, ne sont visibles qu'une fois la ligne
    reconstituée."""
    lines: list[list[OcrBlock]] = []
    for block in sorted(blocks, key=_block_center_y):
        if lines and _same_visual_line(lines[-1][0], block):
            lines[-1].append(block)
        else:
            lines.append([block])
    return [sorted(line, key=lambda b: b.bbox[0][0]) for line in lines]


def _is_label_like(text: str) -> bool:
    """Un libellé de total (« Total TTC », « VAT / Sales Tax (Reverse Charge
    0%) ») est court. Une phrase de conditions générales qui contient le mot
    « VAT » ou « total » n'est pas une ancre de montant : sur un document de
    plusieurs pages, ces paragraphes produiraient des candidats parasites."""
    return len(text) <= 70 and len(text.split()) <= 12


def _looks_like_money(raw: str) -> bool:
    """Distingue un montant d'un entier quelconque (fin d'IBAN, quantité,
    numéro de page) : décimales, séparateur de milliers, ou au moins 4 chiffres."""
    digits = re.sub(r"\D", "", raw)
    return bool(re.search(r"[.,]\d{1,2}$", raw.strip()) or re.search(r"\d[ ., ]\d{3}", raw)
                or len(digits) >= 4)


@dataclass
class _Candidate:
    """Un montant candidat pour un total, avec le rang du libellé qui l'a désigné."""
    raw: str
    normalized: str | None
    value: Decimal | None
    block: OcrBlock
    confidence: float
    rank: int
    exempt: bool = False

    @classmethod
    def make(cls, raw: str, block: OcrBlock, confidence: float, rank: int) -> "_Candidate":
        normalized = normalize_amount(raw)
        try:
            value = Decimal(normalized) if normalized else None
        except InvalidOperation:
            value = None
        return cls(raw, normalized, value, block, confidence, rank)


class HybridExtractor(EntityExtractor):
    """Implémentation du port EntityExtractor : regex ancrées + NER optionnel."""

    def __init__(self, use_spacy: bool = True):
        self.use_spacy = use_spacy
        self._nlp = None  # chargé paresseusement

    # ------------------------------------------------------------- API
    def extract(self, ocr_result: OcrResult, language: str | None) -> list[ExtractedEntity]:
        blocks = [OcrBlock(text=_fix_numeric_ocr_errors(b.text), bbox=b.bbox,
                           confidence=b.confidence) for b in ocr_result.blocks]
        entities: list[ExtractedEntity] = []
        entities += self._extract_amounts(blocks)
        entities += self._extract_informative_amounts(blocks)
        entities += self._extract_identifiers(blocks)
        entities += self._extract_date(blocks)
        entities += self._extract_currency(
            blocks, preferred=[e.source_block["text"] for e in entities
                               if e.entity_type in ("TOTAL_TTC", "TOTAL_HT")])
        supplier = self._extract_supplier(blocks, language)
        if supplier:
            entities.append(supplier)
        return entities

    # -------------------------------------------------- Montants ancrés
    def _extract_amounts(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        max_y = max((_block_center_y(b) for b in blocks), default=0)
        pools = {t: self._collect_candidates(t, blocks) for t in ("TOTAL_TTC", "TOTAL_HT", "TOTAL_VAT")}

        def position(entity_type: str, c: "_Candidate") -> float:
            # À rang égal : le TTC le plus bas de la page ; HT/TVA vers 70 % de la hauteur
            y = _block_center_y(c.block)
            return y if entity_type == "TOTAL_TTC" else -abs(y - max_y * 0.7)

        # Arbitrage par le calcul : seul le trio (HT, TVA, TTC) qui vérifie
        # HT + TVA = TTC est cohérent. Indépendant de la langue et de la mise en page.
        chosen: dict[str, _Candidate] = {}
        if all(pools.values()):
            best_key, best = None, None
            for ht in pools["TOTAL_HT"]:
                for vat in pools["TOTAL_VAT"]:
                    for ttc in pools["TOTAL_TTC"]:
                        if abs(ht.value + vat.value - ttc.value) > TOLERANCE:
                            continue
                        key = (-(ht.rank + vat.rank + ttc.rank), position("TOTAL_TTC", ttc),
                               position("TOTAL_HT", ht), position("TOTAL_VAT", vat))
                        if best_key is None or key > best_key:
                            best_key, best = key, (ht, vat, ttc)
            if best:
                chosen = {"TOTAL_HT": best[0], "TOTAL_VAT": best[1], "TOTAL_TTC": best[2]}
        # Sinon (un total manquant, ou aucun trio cohérent) : meilleur candidat par type
        for entity_type, pool in pools.items():
            if entity_type not in chosen and pool:
                chosen[entity_type] = max(pool, key=lambda c: (-c.rank, position(entity_type, c)))

        return [ExtractedEntity(
                    entity_type=t, raw_value=c.raw, normalized_value="0.00" if c.exempt else c.normalized,
                    confidence=round(c.confidence, 4), method=ExtractionMethod.REGEX,
                    source_block={"bbox": c.block.bbox, "text": c.block.text})
                for t, c in chosen.items()]

    @staticmethod
    def _rank(entity_type: str, anchor_text: str) -> int:
        lowered = anchor_text.lower()
        if entity_type == "TOTAL_TTC":
            return next((r for r, p in TTC_RANKS if re.search(p, lowered)), 2)
        if entity_type == "TOTAL_HT":
            return next((r for r, p in HT_RANKS if re.search(p, lowered)), 0)
        return 0 if re.search(VAT_PRIMARY, lowered) else 1

    def _collect_candidates(self, entity_type: str, blocks: list[OcrBlock]) -> list["_Candidate"]:
        own_candidates, right_candidates, left_candidates = [], [], []
        exempt_anchors = []  # mentions « TVA non applicable » (TVA seulement)
        excluded = EXCLUDED_ANCHORS.get(entity_type)
        for anchor in blocks:
            if not _is_label_like(anchor.text):
                continue
            if not _matches_any(anchor.text, ANCHORS[entity_type]):
                continue
            if excluded and excluded.search(anchor.text):
                continue
            rank = self._rank(entity_type, anchor.text)
            # 1) montant dans le bloc ancre lui-même — on exclut les
            # nombres suivis de '%' : pour l'ancre TVA, "20%" est un taux,
            # pas le montant de la taxe (bug corrigé après tests unitaires).
            is_exempt = entity_type == "TOTAL_VAT" and VAT_EXEMPT_RE.search(anchor.text)
            if is_exempt:
                exempt_anchors.append(anchor)
            own = [] if is_exempt else [
                m for m in AMOUNT_RE.findall(anchor.text)
                if not re.search(re.escape(m) + r"\s*%", anchor.text)]
            if own:
                own_candidates.append(_Candidate.make(own[-1], anchor, anchor.confidence, rank))
            # 2) montant dans un bloc aligné horizontalement (même ligne)
            for other in blocks:
                if other is anchor or not _same_visual_line(anchor, other):
                    continue
                amounts = [m for m in AMOUNT_RE.findall(other.text)
                           if not re.search(re.escape(m) + r"\s*%", other.text)]
                if not amounts:
                    continue
                candidate = _Candidate.make(amounts[-1], other,
                                            min(anchor.confidence, other.confidence), rank)
                if _block_center_x(other) > _block_center_x(anchor):
                    right_candidates.append(candidate)
                elif _looks_like_money(amounts[-1]):
                    # Bug réel : sur une facture à deux colonnes, « Net
                    # Subtotal » (colonne de droite) partageait sa ligne avec
                    # un IBAN (colonne de gauche) dont le dernier chiffre,
                    # « 2 », était pris pour le montant HT.
                    left_candidates.append(candidate)
        # Priorité systématique au montant ALIGNÉ (ligne voisine) sur un
        # nombre trouvé dans le bloc-ancre lui-même : le second n'est
        # utilisé qu'en repli. Bug réel corrigé : l'OCR peut corrompre
        # un taux ("20%") en un nombre qui ressemble à un montant valide
        # ("209" si le "%" est lu comme un "9"), sans le signe "%" que le
        # garde-fou ci-dessus cherche — cette valeur parasite l'emportait
        # alors à tort sur le véritable montant aligné.
        candidates = [c for c in (right_candidates or left_candidates or own_candidates)
                      if c.value is not None]
        if not candidates and exempt_anchors:
            # Aucun montant de taxe, mais une mention d'exonération : TVA = 0
            # (et non « absente », ce qui ferait appliquer le taux par défaut).
            candidates = [_Candidate("0", "0.00", Decimal("0"), exempt_anchors[0],
                                     exempt_anchors[0].confidence, 0, exempt=True)]
        return candidates

    def _extract_informative_amounts(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        """Acompte déjà versé, escompte : à porter à la connaissance du comptable
        mais jamais dans l'écriture (l'acompte a déjà été enregistré à son
        versement ; l'escompte n'existe que si le client paie avant l'échéance)."""
        found = []
        for entity_type, pattern in INFO_ANCHORS.items():
            entity = None
            for anchor in blocks:
                if entity or not (_is_label_like(anchor.text) and re.search(pattern, anchor.text.lower())):
                    continue
                excluded = INFO_EXCLUDED_ANCHORS.get(entity_type)
                if excluded and excluded.search(anchor.text):
                    continue
                for other in blocks:
                    if other is anchor or not _same_visual_line(anchor, other):
                        continue
                    if _block_center_x(other) <= _block_center_x(anchor):
                        continue
                    amounts = AMOUNT_RE.findall(other.text)
                    # un escompte est une déduction : montant signé « - », jamais le net à payer voisin
                    if not amounts or (entity_type == "EARLY_PAYMENT_DISCOUNT"
                                       and not re.match(r"\s*[-−–]", other.text)):
                        continue
                    normalized = normalize_amount(amounts[-1])
                    if normalized:
                        entity = ExtractedEntity(
                            entity_type=entity_type, raw_value=amounts[-1], normalized_value=normalized,
                            confidence=round(min(anchor.confidence, other.confidence), 4),
                            method=ExtractionMethod.REGEX,
                            source_block={"bbox": other.bbox, "text": other.text})
                        break
            if entity:
                found.append(entity)
        return found

    # -------------------------------------------- NIF / STAT / n° facture
    def _extract_identifiers(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        entities = []
        specs = [("NIF", ANCHORS["NIF"], r"(\d[\d\s]{7,})"),
                 ("STAT", ANCHORS["STAT"], r"([\d][\d\s\-/]{5,})"),
                 ("INVOICE_NUMBER", ANCHORS["INVOICE_NUMBER"], r"([A-Za-z]{0,4}[\-/]?\d[\w\-/]*)")]
        for entity_type, anchors, value_pattern in specs:
            for anchor in blocks:
                if not _matches_any(anchor.text, anchors):
                    continue
                zone = anchor.text
                for other in blocks:
                    if other is not anchor and _same_visual_line(anchor, other):
                        zone += " " + other.text
                # la valeur suit l'ancre dans la zone
                lowered = zone.lower()
                anchor_end = 0
                for pattern in anchors:
                    match = re.search(pattern, lowered)
                    if match:
                        anchor_end = max(anchor_end, match.end())
                value_match = re.search(value_pattern, zone[anchor_end:])
                if value_match:
                    raw = value_match.group(1).strip()
                    entities.append(ExtractedEntity(
                        entity_type=entity_type, raw_value=raw,
                        normalized_value=re.sub(r"\s", "", raw),
                        confidence=round(anchor.confidence, 4),
                        method=ExtractionMethod.REGEX,
                        source_block={"bbox": anchor.bbox, "text": anchor.text}))
                    break
            # une seule occurrence par type
        return entities

    # -------------------------------------------------------------- Date
    def _extract_date(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        candidates: list[tuple[datetime, OcrBlock, bool, str]] = []
        # Unités de recherche : chaque bloc, plus chaque ligne visuelle
        # reconstituée (une date découpée par l'OCR en « 17 / 08 » + « 2026 »
        # n'existe dans aucun bloc pris isolément).
        units = list(blocks)
        for line in _visual_lines(blocks):
            if len(line) > 1:
                xs = [pt[0] for b in line for pt in b.bbox]
                ys = [pt[1] for b in line for pt in b.bbox]
                units.append(OcrBlock(
                    text=" ".join(b.text for b in line),
                    bbox=[[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]],
                    confidence=min(b.confidence for b in line)))
        for block in units:
            near_anchor = _matches_any(block.text, ANCHORS["DATE"])
            for regex in DATE_RES + [DATE_SPLIT_RE]:
                for match in regex.finditer(block.text):
                    parsed = self._parse_date(match)
                    if parsed:
                        candidates.append((parsed, block, near_anchor, match.group(0)))
            # dates textuelles : « 15 janvier 2026 », « 09 Oct 2026 », « 12 sept. 2026 »
            for text_match in TEXT_DATE_RE.finditer(block.text):
                month = MONTHS.get(text_match.group(2).lower())
                if month is None:
                    continue
                try:
                    parsed = datetime(int(text_match.group(3)), month, int(text_match.group(1)))
                except ValueError:
                    continue
                candidates.append((parsed, block, near_anchor, text_match.group(0)))
        if not candidates:
            return []
        # plausibilité ± 2 ans, priorité aux dates proches d'une ancre, sinon la plus ancienne
        now = datetime.now()
        plausible = [c for c in candidates if abs((c[0] - now).days) < 730] or candidates
        anchored = [c for c in plausible if c[2]]
        best = min(anchored or plausible, key=lambda c: c[0])
        return [ExtractedEntity(entity_type="INVOICE_DATE", raw_value=best[3],
                                normalized_value=best[0].strftime("%Y-%m-%d"),
                                confidence=round(best[1].confidence, 4),
                                method=ExtractionMethod.REGEX,
                                source_block={"bbox": best[1].bbox, "text": best[1].text})]

    @staticmethod
    def _parse_date(match: re.Match) -> datetime | None:
        groups = match.groups()
        try:
            if len(groups[0]) == 4:  # AAAA-MM-JJ
                return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
            year = int(groups[2])
            if year < 100:
                year += 2000
            return datetime(year, int(groups[1]), int(groups[0]))  # JJ/MM/AAAA
        except ValueError:
            return None

    # ------------------------------------------------------------ Devise
    def _extract_currency(self, blocks: list[OcrBlock],
                          preferred: list[str] | None = None) -> list[ExtractedEntity]:
        mapping = {"ariary": "MGA", "mga": "MGA", "ar": "MGA", "eur": "EUR", "€": "EUR",
                   "usd": "USD", "$": "USD", "gbp": "GBP", "£": "GBP", "chf": "CHF"}
        # La devise la plus fiable est celle écrite à côté des montants retenus
        # (« 47 104,03 € ») : un « € » isolé en pied de page (capital social)
        # ne doit pas l'emporter sur des montants en Ariary.
        preferred = set(preferred or [])
        ordered = [b for b in blocks if b.text in preferred] + list(blocks)
        for block in ordered:
            match = CURRENCY_RE.search(block.text)
            if match:
                symbol = match.group(1) or match.group(2)
                return [ExtractedEntity(
                    entity_type="CURRENCY", raw_value=symbol,
                    normalized_value=mapping.get(symbol.lower(), "MGA"),
                    confidence=round(block.confidence, 4),
                    method=ExtractionMethod.REGEX,
                    source_block={"bbox": block.bbox, "text": block.text})]
        return []

    # ------------------------------------------------------- Fournisseur
    def _extract_supplier(self, blocks: list[OcrBlock],
                          language: str | None) -> ExtractedEntity | None:
        """NER spaCy (ORG) restreint au tiers supérieur de la page ; à défaut,
        heuristique : premier bloc textuel majuscule significatif du haut de page."""
        if not blocks:
            return None
        labelled = self._supplier_from_label(blocks)
        if labelled is not None:
            return labelled
        max_y = max(_block_center_y(b) for b in blocks)
        top_blocks = [b for b in blocks if _block_center_y(b) < max_y / 3
                      and not _matches_any(b.text.strip(), DOCUMENT_TITLE_PATTERNS)]

        if self.use_spacy:
            nlp = self._get_nlp(language)
            if nlp is not None:
                for block in top_blocks:
                    doc = nlp(block.text)
                    for ent in doc.ents:
                        if ent.label_ == "ORG" and len(ent.text) >= 3:
                            return ExtractedEntity(
                                entity_type="SUPPLIER_NAME", raw_value=ent.text,
                                normalized_value=ent.text.strip().upper(),
                                confidence=round(block.confidence * 0.9, 4),
                                method=ExtractionMethod.NER,
                                source_block={"bbox": block.bbox, "text": block.text})
        for block in top_blocks:
            text = block.text.strip()
            if (len(text) >= 4 and sum(c.isalpha() for c in text) >= 3
                    and not _matches_any(text, sum(ANCHORS.values(), []))
                    and not AMOUNT_RE.fullmatch(text)):
                return ExtractedEntity(
                    entity_type="SUPPLIER_NAME", raw_value=text,
                    normalized_value=text.upper(),
                    confidence=round(block.confidence * 0.6, 4),
                    method=ExtractionMethod.NER,
                    source_block={"bbox": block.bbox, "text": block.text})
        return None

    @staticmethod
    def _supplier_from_label(blocks: list[OcrBlock]) -> ExtractedEntity | None:
        """Valeur placée après une étiquette explicite (« Vendeur : … »), dans le même
        bloc ou dans le bloc voisin de droite sur la même ligne. C'est le signal le plus
        fiable : il l'emporte sur l'heuristique de position, qui prenait un sous-titre."""
        for label in blocks:
            match = SUPPLIER_LABEL_RE.match(label.text)
            if not match:
                continue
            value, source, confidence = match.group("value").strip(), label, label.confidence
            if not value:
                neighbours = [b for b in blocks if b is not label and _same_visual_line(label, b)
                              and _block_center_x(b) > _block_center_x(label)]
                neighbours.sort(key=_block_center_x)
                for other in neighbours:
                    text = other.text.strip()
                    if (len(text) >= 3 and sum(c.isalpha() for c in text) >= 2
                            and not SUPPLIER_LABEL_RE.match(text) and not text.rstrip().endswith(":")
                            and not _matches_any(text, DOCUMENT_TITLE_PATTERNS)):
                        value, source, confidence = text, other, min(label.confidence, other.confidence)
                        break
            if len(value) >= 3 and sum(c.isalpha() for c in value) >= 2:
                return ExtractedEntity(
                    entity_type="SUPPLIER_NAME", raw_value=value, normalized_value=value.upper(),
                    confidence=round(confidence * 0.9, 4), method=ExtractionMethod.REGEX,
                    source_block={"bbox": source.bbox, "text": source.text})
        return None

    def _get_nlp(self, language: str | None):
        if self._nlp is None:
            try:
                import spacy
                model = "fr_core_news_md" if (language or "fr").startswith("fr") else "xx_ent_wiki_sm"
                try:
                    self._nlp = spacy.load(model)
                except OSError:
                    logger.warning("Modèle spaCy %s absent : NER désactivé "
                                   "(python -m spacy download %s)", model, model)
                    self._nlp = False
            except ImportError:
                self._nlp = False
        return self._nlp or None


def detect_language(text: str) -> str | None:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return None
