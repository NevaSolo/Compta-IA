"""Lecture directe de la couche texte d'un PDF « numérique ».

Un PDF produit par un logiciel de facturation (et non un scan) contient déjà
son texte, avec la position exacte de chaque mot. Le rasteriser puis le relire
par OCR ne peut qu'introduire des erreurs (« €4,200.00 » lu « 44,200.00 »).
Ce module restitue cette couche texte sous la forme habituelle d'un résultat
OCR (blocs + coordonnées), pour que l'extraction en aval n'ait pas à savoir
d'où vient le texte ; il renvoie None pour un scan ou une photo, auquel cas
le pipeline retombe sur l'OCR comme avant.

Toutes les pages sont lues : les coordonnées verticales sont décalées de la
hauteur des pages précédentes, de sorte que la page 2 se place sous la page 1
(les heuristiques « le plus bas de la page » gardent leur sens)."""
import logging
import time

from app.domain.ports import OcrBlock, OcrResult

logger = logging.getLogger(__name__)

ENGINE_NAME = "PDF_TEXT"
MIN_WORDS = 25            # en dessous : scan (ou page quasi vide) -> OCR
MAX_GARBAGE_RATIO = 0.10  # police sans table Unicode : texte illisible -> OCR
TEXT_LAYER_CONFIDENCE = 0.99  # le texte est exact ; seule l'extraction peut se tromper


def read_pdf_text_layer(pdf_path: str) -> OcrResult | None:
    import fitz  # PyMuPDF

    start = time.perf_counter()
    blocks: list[OcrBlock] = []
    garbage_chars = total_chars = 0
    y_offset = 0.0
    try:
        with fitz.open(pdf_path) as document:
            for page in document:
                lines: dict[tuple[int, int], list[tuple]] = {}
                for x0, y0, x1, y1, word, block_no, line_no, _ in page.get_text("words"):
                    lines.setdefault((block_no, line_no), []).append((x0, y0, x1, y1, word))
                    total_chars += len(word)
                    garbage_chars += word.count("�") + word.count("(cid:")
                for words in lines.values():
                    words.sort(key=lambda w: w[0])
                    x0 = min(w[0] for w in words)
                    x1 = max(w[2] for w in words)
                    y0 = min(w[1] for w in words) + y_offset
                    y1 = max(w[3] for w in words) + y_offset
                    blocks.append(OcrBlock(
                        text=" ".join(w[4] for w in words),
                        bbox=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                        confidence=TEXT_LAYER_CONFIDENCE))
                y_offset += page.rect.height
    except Exception as exc:  # PDF protégé, corrompu... : l'OCR prendra le relais
        logger.warning("Couche texte du PDF illisible (%s) : repli sur l'OCR", exc)
        return None

    word_count = sum(len(b.text.split()) for b in blocks)
    if word_count < MIN_WORDS:
        return None
    if total_chars and garbage_chars / total_chars > MAX_GARBAGE_RATIO:
        logger.info("Couche texte inexploitable (encodage) : repli sur l'OCR")
        return None

    # Ordre de lecture : de haut en bas, puis de gauche à droite
    blocks.sort(key=lambda b: (round(b.bbox[0][1] / 4), b.bbox[0][0]))
    return OcrResult(engine=ENGINE_NAME,
                     raw_text="\n".join(b.text for b in blocks),
                     mean_confidence=TEXT_LAYER_CONFIDENCE, blocks=blocks,
                     duration_ms=int((time.perf_counter() - start) * 1000))
