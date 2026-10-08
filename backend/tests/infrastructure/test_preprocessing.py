"""Tests du prétraitement d'image — bug réel corrigé en production :
cv2.HoughLinesP renvoie tantôt (N, 1, 4), tantôt (N, 4) selon la version
d'OpenCV/les paramètres ; _deskew doit gérer les deux formes sans planter."""
from unittest.mock import patch

import numpy as np

from app.infrastructure.ocr import preprocessing


def _blank_gray_image(size=200):
    return np.zeros((size, size), dtype=np.uint8)


def test_deskew_handles_lines_shape_n_1_4():
    """Forme (N, 1, 4) — celle historiquement attendue par le code."""
    lines = np.array([[[10, 50, 190, 52]], [[10, 60, 190, 63]]], dtype=np.int32)
    with patch("cv2.HoughLinesP", return_value=lines):
        result = preprocessing._deskew(_blank_gray_image())
    assert result is not None
    assert result.shape == (200, 200)


def test_deskew_handles_lines_shape_n_4():
    """Forme (N, 4) — celle qui provoquait un TypeError avant correction
    (lines[:, 0] livrait alors une colonne de scalaires, non des quadruplets)."""
    lines = np.array([[10, 50, 190, 52], [10, 60, 190, 63]], dtype=np.int32)
    with patch("cv2.HoughLinesP", return_value=lines):
        result = preprocessing._deskew(_blank_gray_image())
    assert result is not None
    assert result.shape == (200, 200)


def test_deskew_returns_original_when_no_lines_detected():
    with patch("cv2.HoughLinesP", return_value=None):
        image = _blank_gray_image()
        result = preprocessing._deskew(image)
    assert result is image
