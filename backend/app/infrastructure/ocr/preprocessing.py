"""Prétraitement d'image (Phase 6, étape 1) — chaîne OpenCV :
gris → redressement (Hough) → débruitage (non-local means) →
binarisation adaptative, avec contrôle de netteté (variance du Laplacien)."""
import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SHARPNESS_THRESHOLD = 100.0  # variance du Laplacien sous laquelle l'image est jugée floue


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[str]:
    """Convertit chaque page d'un PDF en image PNG 300 DPI (optimum
    précision/temps pour l'OCR). Implémenté avec PyMuPDF (wheel pip
    autonome) plutôt que pdf2image, qui exige le binaire externe Poppler —
    source de friction de déploiement, notamment sous Windows."""
    import fitz  # PyMuPDF

    paths = []
    zoom = dpi / 72.0  # PyMuPDF raisonne en points (72 dpi de base)
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(pdf_path) as document:
        for i, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=matrix)
            out = str(Path(pdf_path).with_suffix(f".page{i}.png"))
            pixmap.save(out)
            paths.append(out)
    return paths


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Redressement par transformée de Hough : détecte les lignes quasi
    horizontales et corrige l'angle médian si l'inclinaison dépasse 0,3°."""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                            minLineLength=gray.shape[1] // 4, maxLineGap=20)
    if lines is None:
        return gray
    # cv2.HoughLinesP renvoie tantôt (N, 1, 4), tantôt (N, 4) selon la
    # version d'OpenCV : reshape(-1, 4) normalise avant l'itération
    # (sans quoi lines[:, 0] peut ne livrer qu'une colonne de scalaires,
    # provoquant un TypeError au dépaquetage).
    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 15:  # on ne garde que les lignes quasi horizontales
            angles.append(angle)
    if not angles:
        return gray
    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.3:
        return gray
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    return cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(image_path: str) -> tuple[str, dict]:
    """Applique la chaîne complète et retourne (chemin_image_traitée,
    métadonnées journalisées pour la reproductibilité)."""
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Image illisible : {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    gray = _deskew(gray)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, blockSize=31, C=11)

    out_path = str(Path(image_path).with_suffix(".prep.png"))
    cv2.imwrite(out_path, binary)

    meta = {"sharpness": round(sharpness, 1),
            "low_quality": sharpness < SHARPNESS_THRESHOLD,
            "steps": ["grayscale", "deskew_hough", "nlmeans_denoise",
                      "adaptive_threshold_31_11"]}
    if meta["low_quality"]:
        logger.warning("Image de faible netteté (%.1f) : %s", sharpness, image_path)
    return out_path, meta
