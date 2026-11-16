"""Extraction des lignes de détail d'une facture (tableau articles / prestations)
et contrôle de leur cohérence avec les totaux. OcrResult synthétiques : aucune
dépendance à un moteur OCR réel."""
from decimal import Decimal

from app.domain.entities import InvoiceLine
from app.domain.ports import OcrBlock, OcrResult
from app.domain.rules import reconcile_line_items
from app.infrastructure.nlp.line_items import TableLineExtractor


def block(text: str, x: float, y: float, w: float = 80, h: float = 20,
          conf: float = 0.9) -> OcrBlock:
    return OcrBlock(text=text, confidence=conf,
                    bbox=[[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def row(y: float, *cells: tuple[float, str]) -> list[OcrBlock]:
    return [block(text, x, y) for x, text in cells]


def extract(blocks: list[OcrBlock]) -> list[InvoiceLine]:
    return TableLineExtractor().extract(
        OcrResult(engine="TEST", raw_text="\n".join(b.text for b in blocks),
                  mean_confidence=0.9, blocks=blocks))


HEADER = row(100, (40, "Désignation"), (300, "Qté"), (360, "P.U. HT"), (440, "TVA"), (500, "Montant HT"))


class TestTableDetection:
    def test_one_ocr_block_per_cell(self):
        blocks = HEADER + row(130, (40, "Honoraires mission conseil"), (300, "1"),
                              (360, "2 400,00"), (440, "20 %"), (500, "2 400,00"))
        [line] = extract(blocks)
        assert line.description == "Honoraires mission conseil"
        assert (line.quantity, line.unit_price, line.amount) == (Decimal("1"), Decimal("2400.00"),
                                                                 Decimal("2400.00"))
        assert line.vat_rate == Decimal("20")

    def test_whole_row_in_a_single_block_like_a_pdf_text_layer(self):
        blocks = HEADER + [block("Ordinateur portable Dell 15 1 1 390,00 20% 1 390,00", 40, 130, w=500)]
        [line] = extract(blocks)
        # « 15 » appartient à la désignation ; « 1 390,00 » est un seul nombre
        assert line.description == "Ordinateur portable Dell 15"
        assert (line.quantity, line.unit_price, line.amount) == (Decimal("1"), Decimal("1390.00"),
                                                                 Decimal("1390.00"))

    def test_thousands_ambiguity_is_resolved_by_quantity_times_price(self):
        # « 2 150,00 » : quantité 2 × 150,00 = 300,00 — et non 2 150,00
        blocks = HEADER + [block("Location salle 2 150,00 300,00", 40, 130, w=500)]
        [line] = extract(blocks)
        assert (line.quantity, line.unit_price, line.amount) == (Decimal("2"), Decimal("150.00"),
                                                                 Decimal("300.00"))

    def test_decimal_quantity_and_unit_words(self):
        blocks = HEADER + row(130, (40, "Abonnement logiciel SaaS"), (300, "12 mois"),
                              (360, "49,90"), (500, "598,80"))
        [line] = extract(blocks)
        assert (line.quantity, line.unit_price, line.amount) == (Decimal("12"), Decimal("49.90"),
                                                                 Decimal("598.80"))

    def test_vat_column_without_percent_sign(self):
        blocks = HEADER + row(130, (40, "Nettoyage des locaux"), (300, "1"), (360, "420,00"),
                              (440, "20"), (500, "420,00"))
        [line] = extract(blocks)
        assert line.amount == Decimal("420.00") and line.vat_rate == Decimal("20")

    def test_amount_only_line_keeps_lower_confidence(self):
        blocks = HEADER + row(130, (40, "Frais de dossier"), (500, "75,00"))
        [line] = extract(blocks)
        assert line.amount == Decimal("75.00") and line.quantity is None
        assert line.confidence < 0.9

    def test_wrapped_description_is_appended_to_previous_line(self):
        blocks = HEADER + row(130, (40, "Mission d'audit"), (300, "1"), (360, "800,00"), (500, "800,00")) \
            + row(160, (40, "du 01/09 au 30/09"))
        [line] = extract(blocks)
        assert line.description == "Mission d'audit du 01/09 au 30/09"

    def test_table_ends_at_totals(self):
        blocks = HEADER + row(130, (40, "Publicité en ligne"), (300, "1"), (360, "1 150,00"),
                              (500, "1 150,00")) \
            + row(200, (380, "Total HT"), (500, "1 150,00")) \
            + row(220, (380, "TVA 20 %"), (500, "230,00")) \
            + row(240, (380, "Total TTC"), (500, "1 380,00"))
        assert [l.description for l in extract(blocks)] == ["Publicité en ligne"]

    def test_negative_discount_line(self):
        blocks = HEADER + row(130, (40, "Remise commerciale"), (500, "-50,00"))
        [line] = extract(blocks)
        assert line.amount == Decimal("-50.00")

    def test_no_header_means_no_lines(self):
        blocks = row(130, (40, "Honoraires"), (500, "1 000,00"))
        assert extract(blocks) == []

    def test_header_repeated_on_next_page_is_not_a_line(self):
        blocks = HEADER + row(130, (40, "Fournitures de bureau"), (500, "186,60")) \
            + row(900, (40, "Désignation"), (300, "Qté"), (500, "Montant HT")) \
            + row(930, (40, "Affranchissement"), (500, "125,00"))
        assert [l.line_no for l in extract(blocks)] == [1, 2]

    def test_lines_are_numbered_in_reading_order(self):
        blocks = HEADER + row(130, (40, "Ligne A"), (500, "10,00")) + row(160, (40, "Ligne B"), (500, "20,00"))
        assert [(l.line_no, l.description) for l in extract(blocks)] == [(1, "Ligne A"), (2, "Ligne B")]


class TestReconcile:
    LINES = [InvoiceLine(1, "A", Decimal("100.00")), InvoiceLine(2, "B", Decimal("50.01"))]

    def test_sum_matches_total_ht(self):
        assert reconcile_line_items(self.LINES, Decimal("150.01"), Decimal("180.01")) == "HT"

    def test_sum_matches_total_ttc(self):
        assert reconcile_line_items(self.LINES, Decimal("125.00"), Decimal("150.01")) == "TTC"

    def test_rounding_tolerance(self):
        assert reconcile_line_items(self.LINES, Decimal("150.03"), None) == "HT"

    def test_missing_line_is_not_reliable(self):
        assert reconcile_line_items(self.LINES[:1], Decimal("150.01"), Decimal("180.01")) is None

    def test_no_lines(self):
        assert reconcile_line_items([], Decimal("1"), Decimal("1")) is None


class TestRealWorldColumns:
    """Colonnes « Réf | Désignation | Qté | Unité | PU HT | Remise | TVA | Total HT »."""
    HEADER = row(100, (20, "Réf."), (80, "Désignation"), (300, "Qté"), (330, "Unité"), (370, "PU HT"),
                 (420, "Remise"), (460, "TVA"), (500, "Total HT"))

    def test_empty_discount_cell_and_free_unit_word(self):
        blocks = self.HEADER + row(130, (20, "LOC-SALLE"), (80, "Location de salle de réunion"), (300, "2"),
                                   (330, "demi-jou"), (370, "180,00 €"), (420, "—"), (460, "20 %"),
                                   (500, "360,00 €"))
        [line] = extract(blocks)
        assert line.description == "LOC-SALLE Location de salle de réunion"
        assert (line.quantity, line.unit_price, line.amount, line.vat_rate) == \
            (Decimal("2"), Decimal("180.00"), Decimal("360.00"), Decimal("20"))

    def test_discount_column_is_not_taken_for_the_vat_rate(self):
        blocks = self.HEADER + row(130, (20, "ABO-SAAS"), (80, "Abonnement logiciel SaaS"), (300, "1"),
                                   (330, "an"), (370, "1 440,00 €"), (420, "10 %"), (460, "20 %"),
                                   (500, "1 296,00 €"))
        [line] = extract(blocks)
        assert (line.quantity, line.unit_price, line.amount, line.vat_rate) == \
            (Decimal("1"), Decimal("1440.00"), Decimal("1296.00"), Decimal("20"))
        assert line.confidence == 0.9  # lecture cohérente grâce à la remise

    def test_header_on_several_lines_gross_discount_net_and_section_end(self):
        blocks = row(100, (300, "RATE /"), (360, "QTY /"), (420, "GROSS"), (520, "NET AMOUNT (€)")) \
            + row(125, (40, "DESCRIPTION / DELIVERABLE MODULE"), (470, "DISCOUNT")) \
            + row(150, (300, "UNIT"), (360, "HRS"), (420, "TOTAL")) \
            + row(180, (40, "Enterprise Security Audit"), (300, "€5,500.00"), (360, "2"),
                  (420, "€11,000.00"), (470, "€550.00"), (520, "€10,450.00")) \
            + row(205, (40, "Testing"), (300, "/ fixed")) \
            + row(240, (40, "Gross Services Total:"), (520, "€10,450.00")) \
            + row(400, (40, "4. Enterprise Terms & Notes"))
        [line] = extract(blocks)
        assert line.description == "Enterprise Security Audit Testing / fixed"
        assert (line.quantity, line.unit_price, line.amount) == (Decimal("2"), Decimal("5500.00"),
                                                                 Decimal("10450.00"))

    def test_terms_paragraph_and_page_footer_are_not_lines(self):
        blocks = HEADER + row(130, (40, "Frais de dossier"), (500, "75,00")) \
            + row(160, (40, "1. Conditions générales de vente applicables"), ) \
            + row(190, (40, "Pénalités de retard : trois fois le taux d'intérêt légal, indemnité de 40,00")) \
            + row(220, (40, "Page 1 of 2"), (500, "2"))
        assert [l.description for l in extract(blocks)] == ["Frais de dossier"]
