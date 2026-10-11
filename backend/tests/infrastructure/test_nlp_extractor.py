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


class TestInternationalAndComplexLayouts:
    """Cas relevés sur une facture complexe (fournisseur étranger, deux
    colonnes, format anglo-saxon, pas de ligne « Total TTC ») et sur le corpus
    de test : chacun reproduit un défaut réel de l'extracteur."""

    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def _extract(self, *blocks):
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=list(blocks))
        return {e.entity_type: e for e in self.extractor.extract(ocr, language="en")}

    def test_amount_with_comma_thousands_and_dot_decimals(self):
        # « 115,123.75 » se lisait « 3.75 » (la virgule n'était pas un séparateur de milliers)
        found = self._extract(block("Net Services Subtotal:", x=400, y=100),
                              block("€115,123.75", x=520, y=100))
        assert found["TOTAL_HT"].normalized_value == "115123.75"

    def test_amount_is_not_taken_from_a_neighbouring_column_on_the_left(self):
        # L'IBAN (colonne de gauche) partage la ligne visuelle du sous-total :
        # son dernier chiffre était retenu comme montant HT.
        found = self._extract(block("IBAN (EUR): CH93 0023 0230 4928 1190 2", x=20, y=100, w=250),
                              block("Net Services Subtotal:", x=400, y=100),
                              block("€115,123.75", x=520, y=100))
        assert found["TOTAL_HT"].normalized_value == "115123.75"

    def test_left_neighbour_is_ignored_even_without_any_amount_on_the_right(self):
        found = self._extract(block("IBAN (EUR): CH93 0023 0230 4928 1190 2", x=20, y=100, w=250),
                              block("Net Services Subtotal:", x=400, y=100))
        assert "TOTAL_HT" not in found

    def test_long_sentence_mentioning_vat_is_not_an_amount_anchor(self):
        found = self._extract(block(
            "1. Reverse Charge & Tax Compliance: Cross-border supply of services within the European "
            "Union is subject to the VAT Act 1994 and EU Council Directive 2006/112/EC", x=20, y=300, w=500))
        assert "TOTAL_VAT" not in found

    def test_vat_exemption_mention_gives_zero_vat_not_the_law_article_number(self):
        # « art. 293 B » : le 293 était pris pour le montant de la TVA
        found = self._extract(block("Total", x=400, y=100), block("920.00 €", x=480, y=100),
                              block("TVA non applicable, art. 293 B du CGI.", x=20, y=140, w=300))
        assert found["TOTAL_VAT"].normalized_value == "0.00"
        assert found["TOTAL_TTC"].normalized_value == "920.00"

    def test_date_split_across_ocr_blocks(self):
        # « 17 / 08 » + « 2026 » : deux blocs, la date n'existait dans aucun
        found = self._extract(block("Date de facture", x=20, y=100),
                              block("17 / 08", x=200, y=100), block("2026", x=260, y=100))
        assert found["INVOICE_DATE"].normalized_value == "2026-08-17"

    def test_date_split_in_three_blocks_without_separators(self):
        found = self._extract(block("Date d'échéance", x=20, y=100),
                              block("31", x=200, y=100), block("08", x=230, y=100),
                              block("2026", x=260, y=100))
        assert found["INVOICE_DATE"].normalized_value == "2026-08-31"

    def test_abbreviated_month_name(self):
        found = self._extract(block("Issue Date:", x=20, y=100), block("09 Oct 2026", x=200, y=100))
        assert found["INVOICE_DATE"].normalized_value == "2026-10-09"
        assert found["INVOICE_DATE"].raw_value == "09 Oct 2026"

    def test_registration_number_is_not_preferred_to_the_anchored_invoice_date(self):
        found = self._extract(block("Date", x=20, y=100), block("2026-08-17", x=200, y=100),
                              block("R.C.S:2026-08-01", x=20, y=400))
        assert found["INVOICE_DATE"].normalized_value == "2026-08-17"

    def test_alphabetic_prefix_of_an_invoice_code_is_not_rewritten_as_digits(self):
        # « INV-2026-8849 » devenait « 1NV-2026-8849 »
        assert _fix_numeric_ocr_errors("INV-2026-8849") == "INV-2026-8849"
        assert _fix_numeric_ocr_errors("FAC-2026-00045") == "FAC-2026-00045"

    def test_zero_letters_misread_in_a_numeric_token_are_still_fixed(self):
        assert _fix_numeric_ocr_errors("OO-123") == "00-123"
        assert _fix_numeric_ocr_errors("1O0") == "100"

    def test_bank_account_number_on_the_total_line_is_not_the_total(self):
        # Corpus : « 12345678901 » (RIB, colonne de gauche) lu comme TTC
        found = self._extract(block("00001 00001 12345678901", x=20, y=100, w=200),
                              block("TOTAL TTC", x=400, y=100), block("9 000 000", x=520, y=100))
        assert found["TOTAL_TTC"].normalized_value == "9000000"


class TestSeveralCompetingTotals:
    """Facture réelle « Helios » : trois montants à payer (TTC 47 104,03 ; net à
    payer après acompte 42 104,03 ; net avec escompte 41 261,95) et deux HT
    (avant/après remise). Le TTC retenu était le dernier de la page : 41 261,95,
    d'où « HT + TVA ≠ TTC » puis une écriture déséquilibrée."""

    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def _helios(self):
        rows = [("Total HT avant remise", "40 674,00 €"), ("Remise commerciale (3 %)", "-1 220,22 €"),
                ("Total HT net", "39 453,78 €"), ("Total TVA", "7 650,25 €"),
                ("Total TTC", "47 104,03 €"), ("Acompte déjà versé", "-5 000,00 €"),
                ("NET À PAYER", "42 104,03 €"), ("Escompte 2 % avant le", "-842,08 €"),
                ("Soit net à payer avec", "41 261,95 €")]
        blocks = []
        for i, (label, amount) in enumerate(rows):
            blocks += [block(label, x=400, y=100 + 30 * i, w=150), block(amount, x=600, y=100 + 30 * i)]
        blocks.append(block("N° TVA : FR47 512 874 963", x=20, y=60, w=200))
        return OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=blocks)

    def _by_type(self, ocr):
        return {e.entity_type: e for e in self.extractor.extract(ocr, "fr")}

    def test_ttc_is_the_gross_total_not_the_net_to_pay(self):
        found = self._by_type(self._helios())
        assert found["TOTAL_TTC"].normalized_value == "47104.03"

    def test_ht_is_the_net_after_discount_not_the_amount_before_discount(self):
        found = self._by_type(self._helios())
        assert found["TOTAL_HT"].normalized_value == "39453.78"
        assert found["TOTAL_VAT"].normalized_value == "7650.25"

    def test_extracted_totals_satisfy_ht_plus_vat_equals_ttc(self):
        from decimal import Decimal
        found = self._by_type(self._helios())
        assert (Decimal(found["TOTAL_HT"].normalized_value) + Decimal(found["TOTAL_VAT"].normalized_value)
                == Decimal(found["TOTAL_TTC"].normalized_value))

    def test_deposit_and_early_payment_discount_are_reported_but_not_used_as_totals(self):
        found = self._by_type(self._helios())
        assert found["DEPOSIT_PAID"].normalized_value == "5000.00"
        assert found["EARLY_PAYMENT_DISCOUNT"].normalized_value == "842.08"  # pas 41 261,95

    def test_net_to_pay_is_reported_as_information_and_is_the_unconditional_one(self):
        found = self._by_type(self._helios())
        assert found["NET_TO_PAY"].normalized_value == "42104.03"  # ni 47 104,03 ni 41 261,95

    def test_net_to_pay_ignores_a_discounted_net(self):
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=[
            block("Net à payer avec escompte", x=400, y=100, w=180), block("990,00", x=620, y=100)])
        assert "NET_TO_PAY" not in self._by_type(ocr)

    def test_the_arithmetic_picks_the_consistent_total_when_labels_rank_equally(self):
        # Deux libellés de même rang : celui qui égale HT + TVA l'emporte,
        # même s'il est plus haut sur la page.
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=[
            block("Total HT", x=400, y=100), block("100,00", x=600, y=100),
            block("Total TVA", x=400, y=130), block("20,00", x=600, y=130),
            block("Amount payable", x=400, y=200), block("120,00", x=600, y=200),
            block("Amount due", x=400, y=300), block("90,00", x=600, y=300)])
        assert self._by_type(ocr)["TOTAL_TTC"].normalized_value == "120.00"

    def test_without_any_consistent_total_the_best_ranked_label_wins(self):
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=[
            block("Total HT", x=400, y=100), block("100,00", x=600, y=100),
            block("Total TVA", x=400, y=130), block("20,00", x=600, y=130),
            block("Total TTC", x=400, y=200), block("125,00", x=600, y=200),
            block("Net à payer", x=400, y=300), block("90,00", x=600, y=300)])
        assert self._by_type(ocr)["TOTAL_TTC"].normalized_value == "125.00"

    def test_a_vat_registration_number_is_not_a_vat_amount(self):
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=[
            block("N° TVA :", x=20, y=60), block("512 874 963,00", x=200, y=60)])
        assert "TOTAL_VAT" not in self._by_type(ocr)


class TestCurrencyDetection:
    def setup_method(self):
        self.extractor = HybridExtractor(use_spacy=False)

    def _currency(self, *blocks):
        ocr = OcrResult(engine="PDF_TEXT", raw_text="", mean_confidence=0.99, blocks=list(blocks))
        found = {e.entity_type: e for e in self.extractor.extract(ocr, "fr")}
        return found["CURRENCY"].normalized_value if "CURRENCY" in found else None

    def test_euro_symbol_is_recognised(self):
        # « € » seul n'était jamais reconnu (\b ne s'applique pas à un symbole) : MGA par défaut
        assert self._currency(block("Total TTC", x=400, y=100), block("47 104,03 €", x=600, y=100)) == "EUR"

    def test_dollar_and_pound_symbols(self):
        assert self._currency(block("Total TTC", x=400, y=100), block("$1,200.00", x=600, y=100)) == "USD"
        assert self._currency(block("Total TTC", x=400, y=100), block("£950.00", x=600, y=100)) == "GBP"

    def test_currency_written_next_to_the_totals_wins_over_a_footer_symbol(self):
        assert self._currency(block("Capital social 50 000 €", x=20, y=20, w=200),
                              block("Total TTC", x=400, y=100), block("120 000 Ar", x=600, y=100)) == "MGA"
