"""Tests de la stratégie de fallback OCR — bug réel corrigé en production :
une exception du moteur principal (dépendance absente, modèle non
téléchargé...) ne doit jamais faire planter le pipeline, mais dégrader
proprement vers le moteur de repli."""
from app.domain.ports import OcrResult
from app.infrastructure.ocr.engines import OcrOrchestrator


class FakeEngineRaising:
    def extract_text(self, image_path, languages):
        raise ModuleNotFoundError("No module named 'easyocr'")


class FakeEngineLowConfidence:
    def extract_text(self, image_path, languages):
        return OcrResult(engine="EASYOCR", raw_text="a b", mean_confidence=0.2)


class FakeEngineGoodConfidence:
    def extract_text(self, image_path, languages):
        return OcrResult(engine="TESSERACT",
                         raw_text=" ".join(f"mot{i}" for i in range(15)),
                         mean_confidence=0.75)


class FakeEngineAlsoRaising:
    def extract_text(self, image_path, languages):
        raise RuntimeError("Tesseract introuvable dans le PATH")


def test_primary_exception_falls_back_to_secondary_instead_of_crashing():
    orchestrator = OcrOrchestrator(primary=FakeEngineRaising(),
                                   fallback=FakeEngineGoodConfidence())
    result = orchestrator.run("facture.png", ["fr"])
    assert result is not None
    assert result.engine == "TESSERACT"


def test_both_engines_failing_returns_none_explicitly():
    orchestrator = OcrOrchestrator(primary=FakeEngineRaising(),
                                   fallback=FakeEngineAlsoRaising())
    result = orchestrator.run("facture.png", ["fr"])
    assert result is None  # renoncement explicite, pas de crash


def test_primary_low_confidence_still_tries_fallback():
    orchestrator = OcrOrchestrator(primary=FakeEngineLowConfidence(),
                                   fallback=FakeEngineGoodConfidence())
    result = orchestrator.run("facture.png", ["fr"])
    assert result is not None
    assert result.engine == "TESSERACT"  # meilleure confiance que le primaire


class FakeEngineGoodConfidencePrimary:
    def extract_text(self, image_path, languages):
        return OcrResult(engine="EASYOCR",
                         raw_text=" ".join(f"mot{i}" for i in range(15)),
                         mean_confidence=0.9)


def test_primary_good_confidence_skips_fallback():
    orchestrator = OcrOrchestrator(primary=FakeEngineGoodConfidencePrimary(),
                                   fallback=FakeEngineRaising())
    result = orchestrator.run("facture.png", ["fr"])
    assert result is not None
    assert result.engine == "EASYOCR"  # le fallback n'est jamais appelé
