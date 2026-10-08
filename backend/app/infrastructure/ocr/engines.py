"""Adaptateurs OCR — EasyOCR (principal) et Tesseract (fallback),
derrière le port OCREngine, plus l'orchestrateur de fallback (Phase 6, étape 2).

Les modèles EasyOCR sont chargés paresseusement et gardés en mémoire
(singleton par groupe de langues) : les recharger à chaque facture
coûterait 10 à 20 secondes par requête."""
import logging
import threading
import time

from app.core.config import get_settings
from app.domain.ports import OCREngine, OcrBlock, OcrResult

logger = logging.getLogger(__name__)

_easyocr_readers: dict[str, object] = {}
# FastAPI exécute les BackgroundTasks synchrones dans un threadpool : sans
# verrou, plusieurs factures traitées simultanément peuvent chacune rater le
# cache au même instant et déclencher des téléchargements concurrents du
# même modèle (constaté en conditions réelles — plusieurs "Downloading
# detection model" en parallèle dans les logs).
_easyocr_lock = threading.Lock()
# Second verrou, distinct : une fois le Reader créé, plusieurs factures
# importées ensemble (import multiple) peuvent être traitées en parallèle
# et appeler reader.readtext() simultanément sur la MÊME instance PyTorch —
# l'inférence concurrente sur un modèle partagé n'est pas garantie
# thread-safe côté PyTorch (buffers internes potentiellement mutés). On
# sérialise donc l'inférence elle-même ; le reste du pipeline (extraction,
# classification, écriture) continue de tourner en parallèle par facture.
_easyocr_inference_lock = threading.Lock()


def _get_easyocr_reader(languages: list[str]):
    key = ",".join(sorted(languages))
    reader = _easyocr_readers.get(key)
    if reader is not None:
        return reader
    with _easyocr_lock:
        # Second contrôle : un autre thread a pu terminer l'initialisation
        # pendant qu'on attendait le verrou.
        reader = _easyocr_readers.get(key)
        if reader is None:
            import easyocr
            logger.info("Chargement du Reader EasyOCR pour les langues %s (CPU)", key)
            reader = easyocr.Reader(languages, gpu=False, verbose=False)
            _easyocr_readers[key] = reader
    return reader


class EasyOCRAdapter(OCREngine):
    """Moteur principal : détecteur CRAFT + reconnaissance CRNN,
    robuste aux photos de smartphone et multilingue."""

    def extract_text(self, image_path: str, languages: list[str]) -> OcrResult:
        start = time.perf_counter()
        reader = _get_easyocr_reader(languages)
        with _easyocr_inference_lock:
            raw = reader.readtext(image_path)  # [(bbox, text, confidence), ...]
        blocks = [OcrBlock(text=text, bbox=[[float(x), float(y)] for x, y in bbox],
                           confidence=float(conf))
                  for bbox, text, conf in raw]
        mean_conf = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0
        return OcrResult(engine="EASYOCR",
                         raw_text="\n".join(b.text for b in blocks),
                         mean_confidence=round(mean_conf, 4), blocks=blocks,
                         duration_ms=int((time.perf_counter() - start) * 1000))


class TesseractAdapter(OCREngine):
    """Moteur de repli : Tesseract 5 (LSTM), rapide en CPU sur scans propres."""

    def extract_text(self, image_path: str, languages: list[str]) -> OcrResult:
        import pytesseract
        from PIL import Image

        start = time.perf_counter()
        lang_map = {"fr": "fra", "en": "eng"}
        tess_langs = "+".join(lang_map.get(lang, lang) for lang in languages)
        data = pytesseract.image_to_data(Image.open(image_path), lang=tess_langs,
                                         output_type=pytesseract.Output.DICT)
        blocks, current_line, line_key = [], [], None
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                continue
            key = (data["block_num"][i], data["line_num"][i])
            x, y, w, h = (data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i])
            token = {"text": word, "conf": conf / 100.0,
                     "bbox": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}
            if key != line_key and current_line:
                blocks.append(_merge_line(current_line))
                current_line = []
            line_key = key
            current_line.append(token)
        if current_line:
            blocks.append(_merge_line(current_line))
        mean_conf = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0
        return OcrResult(engine="TESSERACT",
                         raw_text="\n".join(b.text for b in blocks),
                         mean_confidence=round(mean_conf, 4), blocks=blocks,
                         duration_ms=int((time.perf_counter() - start) * 1000))


def _merge_line(tokens: list[dict]) -> OcrBlock:
    """Fusionne les mots d'une même ligne Tesseract en un bloc, pour obtenir
    la même granularité que les blocs EasyOCR (une ligne visuelle)."""
    xs = [pt[0] for tok in tokens for pt in tok["bbox"]]
    ys = [pt[1] for tok in tokens for pt in tok["bbox"]]
    return OcrBlock(text=" ".join(tok["text"] for tok in tokens),
                    bbox=[[min(xs), min(ys)], [max(xs), min(ys)],
                          [max(xs), max(ys)], [min(xs), max(ys)]],
                    confidence=sum(tok["conf"] for tok in tokens) / len(tokens))


class OcrOrchestrator:
    """Stratégie de fallback validée en Phase 6 :
    EasyOCR d'abord ; si confiance < seuil (0,55) ou < 10 mots → Tesseract ;
    on garde le meilleur des deux ; si les deux < 0,40 → échec (illisible)."""

    def __init__(self, primary: OCREngine | None = None,
                 fallback: OCREngine | None = None):
        self.primary = primary or EasyOCRAdapter()
        self.fallback = fallback or TesseractAdapter()
        self.settings = get_settings()

    def run(self, image_path: str, languages: list[str]) -> OcrResult | None:
        try:
            result = self.primary.extract_text(image_path, languages)
        except Exception as exc:
            # Le moteur principal peut échouer pour des raisons indépendantes
            # de la qualité de l'image (dépendance absente, modèle non
            # téléchargé...) : on dégrade vers le fallback plutôt que de
            # faire échouer tout le pipeline.
            logger.warning("Moteur OCR principal indisponible (%s) : fallback Tesseract", exc)
            result = None

        if result is not None:
            word_count = len(result.raw_text.split())
            if result.mean_confidence >= self.settings.ocr_fallback_threshold and word_count >= 10:
                return result
            logger.info("Confiance EasyOCR insuffisante (%.2f, %d mots) : fallback Tesseract",
                        result.mean_confidence, word_count)

        try:
            fallback_result = self.fallback.extract_text(image_path, languages)
        except Exception as exc:  # Tesseract absent du système, par exemple
            logger.warning("Fallback Tesseract indisponible : %s", exc)
            fallback_result = None

        if result is None and fallback_result is None:
            return None  # les deux moteurs sont indisponibles : échec explicite

        best = result if result is not None else fallback_result
        if (fallback_result is not None and result is not None
                and fallback_result.mean_confidence > result.mean_confidence):
            best = fallback_result
        if best.mean_confidence < self.settings.ocr_reject_threshold:
            return None  # facture illisible : le système renonce explicitement
        return best
