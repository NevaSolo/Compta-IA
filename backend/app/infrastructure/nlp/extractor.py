"""Extraction d'entités hybride (Phase 6, étape 4) :
- regex ancrées sur les COORDONNÉES OCR pour les entités à format fixe
  (montants, dates, NIF, STAT, n° facture) — un montant est associé à son
  libellé s'ils sont alignés sur la même ligne visuelle ;
- spaCy NER (optionnel) + heuristique de zone pour le nom du fournisseur.
"""
import logging
import re
from datetime import datetime

from app.domain.entities import DocumentType, ExtractedEntity, ExtractionMethod
from app.domain.ports import EntityExtractor, OcrBlock, OcrResult

logger = logging.getLogger(__name__)

# ----------------------------------------------------------- Ancres multilingues
ANCHORS = {
    "TOTAL_TTC": [r"total\s*ttc", r"net\s*[àa]\s*payer", r"montant\s*ttc",
                  r"amount\s*due", r"grand\s*total", r"totaly", r"total\s*$"],
    "TOTAL_HT": [r"total\s*h\.?t", r"montant\s*h\.?t", r"sub\s*-?\s*total",
                 r"total\s*hors\s*taxes?"],
    "TOTAL_VAT": [r"t\.?v\.?a", r"\bvat\b", r"taxe"],
    "INVOICE_NUMBER": [r"facture\s*(n[°ºo]|num|#)", r"invoice\s*(no|#|number)",
                       r"fact\.?\s*n[°ºo]", r"faktiora", r"\bn[°ºo]?\s*:"],
    "NIF": [r"\bn\.?i\.?f\b"],
    "STAT": [r"\bstat\b"],
    "DATE": [r"\bdate\b", r"\bdaty\b", r"\ble\b\s*:"],
}

AMOUNT_RE = re.compile(r"(\d{1,3}(?:[ . ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)")
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
}
CURRENCY_RE = re.compile(r"\b(ariary|mga|ar|eur|€|usd|\$)\b", re.IGNORECASE)

# Titres de document et en-têtes de colonne génériques (garde-fou pour
# l'extraction du fournisseur : un bloc "FACTURE", "FACTURE D'AVOIR",
# "VENDEUR"... n'est jamais un nom de tiers, même s'il satisfait par
# ailleurs l'heuristique de position/casse — bug réel corrigé : sur une
# facture d'avoir, l'en-tête de colonne "VENDEUR" précédait le vrai nom
# du fournisseur et était retourné à sa place).
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


def _fix_numeric_ocr_errors(text: str) -> str:
    """Corrections O→0, l/I→1, S→5, B→8 uniquement dans les tokens
    majoritairement numériques (jamais dans le texte : noms propres)."""
    def fix_token(token: str) -> str:
        digits = sum(ch.isdigit() for ch in token)
        if digits >= max(2, len(token) // 2):
            return (token.replace("O", "0").replace("o", "0")
                    .replace("l", "1").replace("I", "1")
                    .replace("S", "5").replace("B", "8"))
        return token
    return " ".join(fix_token(tok) for tok in text.split(" "))


def _block_center_y(block: OcrBlock) -> float:
    return sum(pt[1] for pt in block.bbox) / len(block.bbox)


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
        entities += self._extract_identifiers(blocks)
        entities += self._extract_date(blocks)
        entities += self._extract_currency(blocks)
        supplier = self._extract_supplier(blocks, language)
        if supplier:
            entities.append(supplier)
        return entities

    # -------------------------------------------------- Montants ancrés
    def _extract_amounts(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        found: dict[str, ExtractedEntity] = {}
        max_y = max((_block_center_y(b) for b in blocks), default=0)

        for entity_type in ("TOTAL_TTC", "TOTAL_HT", "TOTAL_VAT"):
            own_candidates = []
            aligned_candidates = []
            for anchor in blocks:
                if not _matches_any(anchor.text, ANCHORS[entity_type]):
                    continue
                # 1) montant dans le bloc ancre lui-même — on exclut les
                # nombres suivis de '%' : pour l'ancre TVA, "20%" est un taux,
                # pas le montant de la taxe (bug corrigé après tests unitaires).
                own = [m for m in AMOUNT_RE.findall(anchor.text)
                       if not re.search(re.escape(m) + r"\s*%", anchor.text)]
                if own:
                    own_candidates.append((own[-1], anchor, anchor.confidence))
                # 2) montant dans un bloc aligné horizontalement (même ligne)
                for other in blocks:
                    if other is anchor or not _same_visual_line(anchor, other):
                        continue
                    amounts = AMOUNT_RE.findall(other.text)
                    if amounts:
                        aligned_candidates.append((amounts[-1],
                                           other, min(anchor.confidence, other.confidence)))
            # Priorité systématique au montant ALIGNÉ (ligne voisine) sur un
            # nombre trouvé dans le bloc-ancre lui-même : le second n'est
            # utilisé qu'en repli. Bug réel corrigé : l'OCR peut corrompre
            # un taux ("20%") en un nombre qui ressemble à un montant valide
            # ("209" si le "%" est lu comme un "9"), sans le signe "%" que le
            # garde-fou ci-dessus cherche — cette valeur parasite l'emportait
            # alors à tort sur le véritable montant aligné.
            candidates = aligned_candidates or own_candidates
            if candidates:
                # heuristique : pour le TTC, préférer le candidat le plus bas sur la page
                raw, block, conf = max(
                    candidates,
                    key=lambda c: _block_center_y(c[1]) if entity_type == "TOTAL_TTC"
                    else -abs(_block_center_y(c[1]) - max_y * 0.7))
                normalized = normalize_amount(raw)
                if normalized:
                    found[entity_type] = ExtractedEntity(
                        entity_type=entity_type, raw_value=raw,
                        normalized_value=normalized, confidence=round(conf, 4),
                        method=ExtractionMethod.REGEX,
                        source_block={"bbox": block.bbox, "text": block.text})
        return list(found.values())

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
        candidates: list[tuple[datetime, OcrBlock, bool]] = []
        for block in blocks:
            near_anchor = _matches_any(block.text, ANCHORS["DATE"])
            for regex in DATE_RES:
                for match in regex.finditer(block.text):
                    parsed = self._parse_date(match)
                    if parsed:
                        candidates.append((parsed, block, near_anchor))
            # dates textuelles : « 15 janvier 2026 »
            text_match = re.search(r"(\d{1,2})\s+([a-zA-Zéûôà]+)\s+(\d{4})", block.text)
            if text_match and text_match.group(2).lower() in MONTHS:
                try:
                    parsed = datetime(int(text_match.group(3)),
                                      MONTHS[text_match.group(2).lower()],
                                      int(text_match.group(1)))
                    candidates.append((parsed, block, near_anchor))
                except ValueError:
                    pass
        if not candidates:
            return []
        # plausibilité ± 2 ans, priorité aux dates proches d'une ancre, sinon la plus ancienne
        now = datetime.now()
        plausible = [c for c in candidates if abs((c[0] - now).days) < 730] or candidates
        anchored = [c for c in plausible if c[2]]
        best = min(anchored or plausible, key=lambda c: c[0])
        return [ExtractedEntity(entity_type="INVOICE_DATE", raw_value=best[1].text,
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
    def _extract_currency(self, blocks: list[OcrBlock]) -> list[ExtractedEntity]:
        mapping = {"ariary": "MGA", "mga": "MGA", "ar": "MGA",
                   "eur": "EUR", "€": "EUR", "usd": "USD", "$": "USD"}
        for block in blocks:
            match = CURRENCY_RE.search(block.text)
            if match:
                return [ExtractedEntity(
                    entity_type="CURRENCY", raw_value=match.group(1),
                    normalized_value=mapping.get(match.group(1).lower(), "MGA"),
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
