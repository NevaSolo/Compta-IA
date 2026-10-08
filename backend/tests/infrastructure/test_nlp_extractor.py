"""Tests de l'extraction d'entités hybride (regex ancrées sur coordonnées
OCR). Pas de dépendance à un vrai moteur OCR : on fabrique des OcrResult
synthétiques pour isoler la logique d'extraction."""
from app.domain.ports import OcrBlock, OcrResult
from app.infrastructure.nlp.extractor import (
    HybridExtractor, normalize_amount, _fix_numeric_ocr_errors,
)


def block(text: str, x: float, y: float, w: float = 80, h: float = 20,
         conf: float = 0.9) -> OcrBlock:
    return OcrBlock(text=text, confidence=conf,
                    bbox=[[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


class TestNormalizeAmount:
    def test_thousands_with_space_and_comma_decimal(self):
        assert normalize_amount("1 234 567,50") == "1234567.50"

    def test_simple_integer(self):
        assert normalize_amount("1500") == "1500"

    def test_dot_decimal(self):
        assert normalize_amount("99.90") == "99.90"

    def test_empty_returns_none(self):
        assert normalize_amount("   ") is None


class TestFixNumericOcrErrors:
    def test_fixes_letter_o_in_numeric_token(self):
        assert _fix_numeric_ocr_errors("1O0") == "100"

    def test_does_not_touch_alphabetic_words(self):
        assert _fix_numeric_ocr_errors("Société") == "Société"


class TestHybridExtractorAmounts:
    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def test_extracts_ttc_aligned_on_same_visual_line(self):
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9, blocks=[
            block("Total TTC", x=10, y=100),
            block("120 000,00", x=200, y=102),  # même ligne visuelle
        ])
        entities = self.extractor.extract(ocr, language="fr")
        ttc = next((e for e in entities if e.entity_type == "TOTAL_TTC"), None)
        assert ttc is not None
        assert ttc.normalized_value == "120000.00"
        assert ttc.method.value == "REGEX"

    def test_extracts_ht_and_vat_separately(self):
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9, blocks=[
            block("Total HT", x=10, y=100), block("100 000", x=200, y=100),
            block("TVA 20%", x=10, y=130), block("20 000", x=200, y=131),
        ])
        entities = self.extractor.extract(ocr, language="fr")
        by_type = {e.entity_type: e for e in entities}
        assert by_type["TOTAL_HT"].normalized_value == "100000"
        assert by_type["TOTAL_VAT"].normalized_value == "20000"

    def test_ocr_corrupted_percent_sign_does_not_override_aligned_amount(self):
        """Bug réel corrigé (facture AUTO PRESTIGE SARL) : EasyOCR a lu le
        taux "TVA (20%)" comme "TVA (209)" — le '%' confondu avec un '9'.
        Le garde-fou anti-taux (qui cherche un '%' explicite) ne se déclenche
        plus, donc "209" redevenait un candidat valide et l'emportait à tort
        sur le véritable montant de TVA aligné sur la ligne suivante
        (32 000 000), causant une écriture déséquilibrée en aval."""
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9, blocks=[
            block("MONTANT HT", x=10, y=100), block("160 000 000 Ar", x=200, y=100),
            block("TVA (209)", x=10, y=130),         # '%' corrompu en '9' par l'OCR
            block("32 000 000 Ar", x=200, y=132),    # vrai montant de TVA, ligne alignée
            block("TOTAL TTC", x=10, y=160), block("192 000 000 Ar", x=200, y=160),
        ])
        entities = self.extractor.extract(ocr, language="fr")
        by_type = {e.entity_type: e for e in entities}
        assert by_type["TOTAL_VAT"].normalized_value == "32000000"
        assert by_type["TOTAL_HT"].normalized_value == "160000000"
        assert by_type["TOTAL_TTC"].normalized_value == "192000000"
        # Invariant métier que ce bug faisait échouer :
        ht = float(by_type["TOTAL_HT"].normalized_value)
        vat = float(by_type["TOTAL_VAT"].normalized_value)
        ttc = float(by_type["TOTAL_TTC"].normalized_value)
        assert ht + vat == ttc

    def test_amounts_not_on_same_line_are_not_wrongly_paired(self):
        # L'ancre TTC est loin (verticalement) du montant -> ne doit pas
        # capturer un montant sans rapport situé ailleurs sur la page.
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9, blocks=[
            block("Total TTC", x=10, y=100),
            block("999", x=10, y=500),  # sans rapport, loin
        ])
        entities = self.extractor.extract(ocr, language="fr")
        ttc = next((e for e in entities if e.entity_type == "TOTAL_TTC"), None)
        assert ttc is None  # aucun montant aligné trouvé


class TestHybridExtractorIdentifiers:
    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def test_extracts_invoice_number(self):
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9,
                        blocks=[block("Facture N: FA-2026-0042", x=10, y=50)])
        entities = self.extractor.extract(ocr, language="fr")
        inv = next((e for e in entities if e.entity_type == "INVOICE_NUMBER"), None)
        assert inv is not None
        assert "2026" in inv.raw_value

    def test_extracts_currency_ariary(self):
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9,
                        blocks=[block("Montant en Ariary", x=10, y=50)])
        entities = self.extractor.extract(ocr, language="fr")
        cur = next((e for e in entities if e.entity_type == "CURRENCY"), None)
        assert cur is not None
        assert cur.normalized_value == "MGA"


class TestHybridExtractorDate:
    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def test_extracts_slash_date(self):
        ocr = OcrResult(engine="EASYOCR", raw_text="", mean_confidence=0.9,
                        blocks=[block("Date : 15/01/2026", x=10, y=50)])
        entities = self.extractor.extract(ocr, language="fr")
        date_entity = next((e for e in entities if e.entity_type == "INVOICE_DATE"), None)
        assert date_entity is not None
        assert date_entity.normalized_value == "2026-01-15"
