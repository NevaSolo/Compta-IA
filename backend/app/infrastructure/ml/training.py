"""Réentraînement du classifieur d'opérations à partir des validations et
corrections du comptable (Phase 6, étapes 9-10).

Protocole anti-régression validé :
- split TEMPOREL 80/20 (les factures récentes en test) ;
- la nouvelle version n'est activée que si son F1 macro ≥ celui de la
  version active ;
- artefact joblib versionné, jamais d'écrasement (rollback possible).
"""
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.db import models as m

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 30
MODEL_NAME = "operation_classifier"


def collect_training_data(db: Session) -> tuple[list[str], list[str]]:
    """Construit le jeu d'entraînement : pour chaque facture dont l'écriture
    est VALIDÉE, le texte OCR + fournisseur → le type d'opération réellement
    retenu (la classification d'origine, corrigée le cas échéant)."""
    documents, labels = [], []
    rows = db.execute(
        select(m.InvoiceModel, m.ClassificationModel, m.OcrResultModel)
        .join(m.ClassificationModel, m.ClassificationModel.invoice_id == m.InvoiceModel.id)
        .join(m.OcrResultModel, m.OcrResultModel.invoice_id == m.InvoiceModel.id)
        .where(m.InvoiceModel.status == "VALIDATED")
        .order_by(m.InvoiceModel.id)
    ).all()
    for invoice, classification, ocr in rows:
        supplier_name = invoice.supplier.name if invoice.supplier else ""
        documents.append(f"{ocr.raw_text} {supplier_name}")
        labels.append(classification.operation_type)
    return documents, labels


def _split_temporal(documents: list[str], labels: list[str]):
    """Découpage 80/20 TEMPOREL (pas aléatoire) : les factures les plus
    récentes en test, pour refléter la dérive réelle de distribution plutôt
    qu'un mélange artificiellement optimiste."""
    split = int(len(documents) * 0.8)
    return documents[:split], documents[split:], labels[:split], labels[split:]


def train_and_evaluate(documents: list[str], labels: list[str]):
    """Baseline (étape 6.1 de la spec IA) : TF-IDF + régression logistique
    calibrée. Simple, rapide, nativement bien calibrée — la probabilité
    calibrée alimente directement le score de confiance (étape 8)."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.pipeline import Pipeline

    x_train, x_test, y_train, y_test = _split_temporal(documents, labels)

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000,
                                  sublinear_tf=True)),
        ("clf", CalibratedClassifierCV(
            LogisticRegression(max_iter=1000, class_weight="balanced"), cv=3)),
    ])
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    return (pipeline,
            round(accuracy_score(y_test, predictions), 4),
            round(f1_score(y_test, predictions, average="macro"), 4))


class LabelDecodingPipeline:
    """Enveloppe autour d'un pipeline sklearn entraîné sur des labels
    entiers — nécessaire pour XGBoost : contrairement à la régression
    logistique, son ré-ajustement interne par `CalibratedClassifierCV` sur
    chaque pli de validation croisée exige des classes entières continues
    (0..n-1), pas les chaînes ACHAT_MARCHANDISES/... Cette enveloppe
    redonne les libellés d'origine en sortie (`classes_`, `predict`) pour
    exposer exactement le même contrat que la régression logistique côté
    `SklearnClassifier.classify()` — interchangeable sans code spécifique."""

    def __init__(self, pipeline, encoder):
        self._pipeline = pipeline
        self._encoder = encoder
        self.classes_ = encoder.classes_

    def predict(self, x):
        return self._encoder.inverse_transform(self._pipeline.predict(x))

    def predict_proba(self, x):
        # Les colonnes de predict_proba suivent l'ordre croissant des labels
        # entiers, qui est celui de encoder.classes_ (LabelEncoder trie les
        # classes d'origine par ordre alphabétique avant de les numéroter) —
        # aucune permutation supplémentaire n'est donc nécessaire ici.
        return self._pipeline.predict_proba(x)


def train_and_evaluate_xgboost(documents: list[str], labels: list[str]):
    """Modèle avancé (étape 6.2 de la spec IA) : TF-IDF + XGBoost, sur le
    MÊME split temporel que la baseline pour une comparaison à données
    égales. XGBoost n'est pas nativement calibré (contrairement à la
    régression logistique) : `CalibratedClassifierCV` est indispensable
    ici puisque la probabilité de classe alimente le score de confiance
    global — un modèle non calibré fausserait ce score."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder
    from xgboost import XGBClassifier

    x_train, x_test, y_train, y_test = _split_temporal(documents, labels)

    encoder = LabelEncoder()
    y_train_encoded = encoder.fit_transform(y_train)

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000,
                                  sublinear_tf=True)),
        ("clf", CalibratedClassifierCV(
            XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1,
                         eval_metric="mlogloss"), cv=3)),
    ])
    pipeline.fit(x_train, y_train_encoded)
    wrapped = LabelDecodingPipeline(pipeline, encoder)
    predictions = wrapped.predict(x_test)
    return (wrapped,
            round(accuracy_score(y_test, predictions), 4),
            round(f1_score(y_test, predictions, average="macro"), 4))


CANDIDATE_ALGORITHMS = [
    ("tfidf+logreg-calibrated", train_and_evaluate),
    ("tfidf+xgboost-calibrated", train_and_evaluate_xgboost),
]


def retrain(db: Session) -> dict:
    """Point d'entrée du réentraînement (déclenché par l'Admin ou par seuil).

    Démarche comparative de l'étape 6 de la spec IA : baseline (régression
    logistique) ET modèle avancé (XGBoost) sont entraînés sur le MÊME split
    temporel, chacun versionné individuellement dans `model_versions` — le
    tableau de versions constitue lui-même la trace de la comparaison. Seul
    le meilleur des deux (F1 macro) est comparé à la version active pour
    décider d'une promotion (protection anti-régression) ; en cas d'égalité,
    la régression logistique est préférée (plus interprétable, nativement
    calibrée — cf. justification de la spec)."""
    documents, labels = collect_training_data(db)
    if len(documents) < MIN_TRAINING_SAMPLES or len(set(labels)) < 2:
        return {"status": "SKIPPED",
                "reason": f"Données insuffisantes ({len(documents)} exemples, "
                          f"{len(set(labels))} classes) — minimum {MIN_TRAINING_SAMPLES} et 2 classes."}

    import joblib

    active = db.scalar(select(m.ModelVersionModel).where(
        m.ModelVersionModel.name == MODEL_NAME,
        m.ModelVersionModel.is_active.is_(True)))
    active_f1 = float(active.f1_score) if active and active.f1_score is not None else 0.0

    count = db.scalar(select(m.ModelVersionModel.id).where(
        m.ModelVersionModel.name == MODEL_NAME).order_by(
        m.ModelVersionModel.id.desc()).limit(1)) or 0
    models_dir = Path(get_settings().models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    candidates = []  # [(algorithm, version, pipeline, accuracy, f1)]
    for i, (algorithm, train_fn) in enumerate(CANDIDATE_ALGORITHMS, start=1):
        pipeline, accuracy, f1 = train_fn(documents, labels)
        version = f"1.{count + i}.0"
        candidates.append((algorithm, version, pipeline, accuracy, f1))

    # Meilleur candidat = F1 macro le plus haut ; égalité → régression
    # logistique (premier de la liste, cf. docstring).
    best = max(candidates, key=lambda c: c[4])
    promote = best[4] >= active_f1
    if promote and active:
        active.is_active = False

    for algorithm, version, pipeline, accuracy, f1 in candidates:
        artifact_path = str(models_dir / f"{MODEL_NAME}-{version}.joblib")
        joblib.dump(pipeline, artifact_path)
        is_winner_and_promoted = promote and version == best[1]
        db.add(m.ModelVersionModel(
            name=MODEL_NAME, version=version, algorithm=algorithm,
            artifact_path=artifact_path, accuracy=accuracy, f1_score=f1,
            training_samples=len(documents), is_active=is_winner_and_promoted,
            trained_at=datetime.utcnow()))

    # marquer les corrections consommées
    for correction in db.scalars(select(m.CorrectionModel).where(
            m.CorrectionModel.used_for_training.is_(False))).all():
        correction.used_for_training = True
    db.commit()

    logger.info("Réentraînement comparatif : %s",
               {algo: f1 for algo, _, _, _, f1 in candidates})
    return {"status": "PROMOTED" if promote else "TRAINED_NOT_PROMOTED",
            "version": best[1], "algorithm": best[0],
            "accuracy": best[3], "f1_score": best[4],
            "previous_f1": active_f1, "training_samples": len(documents),
            "candidates": [{"algorithm": algo, "version": v, "accuracy": acc, "f1_score": f1}
                          for algo, v, _, acc, f1 in candidates]}
