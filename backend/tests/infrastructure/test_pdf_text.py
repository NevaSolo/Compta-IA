"""Lecture directe de la couche texte des PDF numériques (sans OCR).

Les PDF de test sont générés à la volée avec ReportLab : aucune dépendance à
un fichier de facture réel."""
import io

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.infrastructure.nlp.extractor import HybridExtractor
from app.infrastructure.ocr.pdf_text import ENGINE_NAME, read_pdf_text_layer

WIDTH, HEIGHT = A4


def _write(tmp_path, draw_pages) -> str:
    path = str(tmp_path / "facture.pdf")
    pdf = canvas.Canvas(path, pagesize=A4)
    draw_pages(pdf)
    pdf.save()
    return path


def _text(pdf, x, y_from_top, text, size=10):
    pdf.setFont("Helvetica", size)
    pdf.drawString(x, HEIGHT - y_from_top, text)


def _complex_two_page_invoice(pdf):
    """Reproduit les pièges d'une vraie facture internationale : fournisseur
    étranger, colonne IBAN à gauche sur la ligne des totaux, format anglo-saxon,
    TVA par autoliquidation, AUCUNE ligne « Total TTC », puis une page 2 avec
    frais, jalons et conditions générales mentionnant la TVA."""
    _text(pdf, 40, 60, "NEXUS TECHNOLOGIES GROUP", 16)
    _text(pdf, 400, 60, "FACTURE / INVOICE", 14)
    _text(pdf, 400, 100, "Invoice No:")
    _text(pdf, 480, 100, "INV-2026-8849")
    _text(pdf, 400, 115, "Issue Date:")
    _text(pdf, 480, 115, "09 Oct 2026")
    _text(pdf, 400, 130, "Due Date:")
    _text(pdf, 480, 130, "08 Nov 2026")
    _text(pdf, 400, 145, "Currency:")
    _text(pdf, 480, 145, "EUR")
    _text(pdf, 40, 200, "Core Infrastructure Migration (Phase 3)")
    _text(pdf, 460, 200, "EUR 28,800.00")
    _text(pdf, 40, 220, "Enterprise Security Audit & Penetration Testing")
    _text(pdf, 460, 220, "EUR 10,450.00")
    _text(pdf, 40, 240, "Dedicated Managed Hosting & SRE Support")
    _text(pdf, 460, 240, "EUR 75,873.75")
    # Colonne de gauche (IBAN) sur la même ligne que le sous-total
    _text(pdf, 40, 300, "IBAN (EUR): CH93 0023 0230 4928 1190 2")
    _text(pdf, 330, 300, "Net Services Subtotal:")
    _text(pdf, 480, 300, "EUR 115,123.75")
    _text(pdf, 330, 318, "VAT / Sales Tax (Reverse Charge 0%):")
    _text(pdf, 480, 318, "EUR 0.00")
    pdf.showPage()
    _text(pdf, 40, 60, "2. Milestone Billing Schedule")
    _text(pdf, 40, 90, "Milestone 3: Cutover   BILLED HERE (EUR 56,505)")
    _text(pdf, 40, 120, "On-Site Deployment Travel: Flights Zurich - London")
    _text(pdf, 460, 120, "EUR 1,420.50")
    _text(pdf, 40, 200, "1. Reverse Charge: the recipient is required to account for VAT under VAT Act 1994 "
                        "and Council Directive 2006/112/EC (Ref. 928 4019 33).", 7)
    pdf.showPage()


class TestReadPdfTextLayer:
    def test_returns_blocks_with_coordinates_and_a_dedicated_engine_name(self, tmp_path):
        path = _write(tmp_path, _complex_two_page_invoice)
        result = read_pdf_text_layer(path)
        assert result is not None
        assert result.engine == ENGINE_NAME
        assert result.mean_confidence > 0.95
        assert "INV-2026-8849" in result.raw_text
        assert all(len(b.bbox) == 4 for b in result.blocks)

    def test_second_page_is_placed_below_the_first(self, tmp_path):
        path = _write(tmp_path, _complex_two_page_invoice)
        result = read_pdf_text_layer(path)
        first = next(b for b in result.blocks if "Core Infrastructure" in b.text)
        second = next(b for b in result.blocks if "Milestone Billing" in b.text)
        assert first.bbox[0][1] < HEIGHT < second.bbox[0][1]

    def test_scanned_pdf_without_text_layer_falls_back_to_ocr(self, tmp_path):
        def draw(pdf):
            buffer = io.BytesIO()
            Image.new("RGB", (200, 200), "white").save(buffer, "PNG")
            buffer.seek(0)
            from reportlab.lib.utils import ImageReader
            pdf.drawImage(ImageReader(buffer), 50, 400, width=300, height=300)
            pdf.showPage()
        assert read_pdf_text_layer(_write(tmp_path, draw)) is None

    def test_page_with_a_handful_of_words_is_not_considered_a_text_pdf(self, tmp_path):
        def draw(pdf):
            _text(pdf, 50, 50, "Scan page 1")
            pdf.showPage()
        assert read_pdf_text_layer(_write(tmp_path, draw)) is None

    def test_corrupted_or_non_pdf_file_returns_none_instead_of_raising(self, tmp_path):
        path = tmp_path / "fake.pdf"
        path.write_bytes(b"%PDF-1.4 ceci n'est pas un vrai pdf")
        assert read_pdf_text_layer(str(path)) is None


class TestComplexInvoiceEndToEnd:
    def test_amounts_date_and_number_are_extracted_from_the_text_layer(self, tmp_path):
        path = _write(tmp_path, _complex_two_page_invoice)
        entities = {e.entity_type: e for e in
                    HybridExtractor(use_spacy=False).extract(read_pdf_text_layer(path), "en")}
        assert entities["TOTAL_HT"].normalized_value == "115123.75"   # pas l'IBAN, pas « 3.75 »
        assert entities["TOTAL_VAT"].normalized_value == "0.00"
        assert entities["INVOICE_NUMBER"].normalized_value == "INV-2026-8849"
        assert entities["INVOICE_DATE"].normalized_value == "2026-10-09"
        assert entities["CURRENCY"].normalized_value == "EUR"

    def test_conditions_paragraph_on_page_two_does_not_override_the_vat_amount(self, tmp_path):
        path = _write(tmp_path, _complex_two_page_invoice)
        entities = {e.entity_type: e for e in
                    HybridExtractor(use_spacy=False).extract(read_pdf_text_layer(path), "en")}
        assert entities["TOTAL_VAT"].normalized_value == "0.00"
