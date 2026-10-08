"""Tests du réentraînement comparatif (étape 6 de la spec IA) : la
baseline (régression logistique) ET le modèle avancé (XGBoost) doivent
être entraînés sur le même corpus et versionnés individuellement — le
meilleur des deux (F1 macro) n'est promu que s'il égale ou dépasse la
version active (protection anti-régression)."""
from app.infrastructure.db.models import (
    ClassificationModel, InvoiceModel, ModelVersionModel, OcrResultModel,
)
from app.infrastructure.ml import training
from app.infrastructure.ml.training import MIN_TRAINING_SAMPLES, retrain

MARCHANDISES_TEXTS = [
    "facture vente riz sac marchandise carton lot revente vary entola",
    "achat de marchandises riz sac carton lot revente commerce",
    "vente riz vary sac de marchandise carton lot negoce",
]
SERVICES_TEXTS = [
    "prestation de service maintenance informatique reparation conseil",
    "facture honoraires consulting audit prestation service abonnement",
    "service de maintenance reparation entretien prestation location",
]


def _seed_validated_invoices(db_session, comptable_user, n_per_class: int = 16):
    for i in range(n_per_class):
        for texts, operation_type in ((MARCHANDISES_TEXTS, "ACHAT_MARCHANDISES"),
                                      (SERVICES_TEXTS, "ACHAT_SERVICES")):
            invoice = InvoiceModel(company_id=comptable_user.company_id,
                                   uploaded_by=comptable_user.id,
                                   original_filename=f"f{operation_type}{i}.pdf",
                                   storage_path="/tmp/f.pdf", mime_type="application/pdf",
                                   file_size=10, status="VALIDATED")
            db_session.add(invoice)
            db_session.flush()
            db_session.add(OcrResultModel(
                invoice_id=invoice.id, engine="EASYOCR",
                raw_text=texts[i % len(texts)], mean_confidence=0.9,
                blocks=[], duration_ms=10))
            db_session.add(ClassificationModel(
                invoice_id=invoice.id, model_version_id=_builtin_version_id(db_session),
                operation_type=operation_type, probability=0.8))
    db_session.commit()


def _builtin_version_id(db_session) -> int:
    version = db_session.query(ModelVersionModel).filter_by(name="operation_classifier").first()
    if version:
        return version.id
    version = ModelVersionModel(name="operation_classifier", version="keyword-0.1.0",
                                algorithm="keyword", artifact_path="builtin", is_active=True)
    db_session.add(version)
    db_session.flush()
    return version.id


def test_retrain_skips_when_below_minimum_samples(db_session, comptable_user):
    _seed_validated_invoices(db_session, comptable_user, n_per_class=2)  # << MIN_TRAINING_SAMPLES
    report = retrain(db_session)
    assert report["status"] == "SKIPPED"


def test_retrain_trains_and_compares_both_algorithms(db_session, comptable_user):
    n = max(MIN_TRAINING_SAMPLES // 2 + 1, 16)
    _seed_validated_invoices(db_session, comptable_user, n_per_class=n)

    report = retrain(db_session)

    assert report["status"] in ("PROMOTED", "TRAINED_NOT_PROMOTED")
    algorithms = {c["algorithm"] for c in report["candidates"]}
    assert algorithms == {"tfidf+logreg-calibrated", "tfidf+xgboost-calibrated"}

    versions = db_session.query(ModelVersionModel).filter_by(
        name="operation_classifier").filter(ModelVersionModel.algorithm != "keyword").all()
    assert len(versions) == 2  # une version par algorithme comparé
    active_versions = [v for v in versions if v.is_active]
    if report["status"] == "PROMOTED":
        assert len(active_versions) == 1
        assert active_versions[0].algorithm == report["algorithm"]
    else:
        assert active_versions == []


def test_retrain_does_not_regress_active_version(db_session, comptable_user, monkeypatch):
    """Une version active très performante ne doit jamais être remplacée
    par un candidat moins bon (protection anti-régression). Les deux
    fonctions d'entraînement sont substituées par des versions déterministes
    pour tester l'arithmétique de décision indépendamment des aléas réels
    d'un entraînement ML (la comparaison des deux algorithmes elle-même
    est déjà couverte par test_retrain_trains_and_compares_both_algorithms)."""
    n = max(MIN_TRAINING_SAMPLES // 2 + 1, 16)
    _seed_validated_invoices(db_session, comptable_user, n_per_class=n)

    monkeypatch.setattr(training, "CANDIDATE_ALGORITHMS", [
        ("tfidf+logreg-calibrated", lambda docs, labels: ("pipeline-lr", 0.60, 0.55)),
        ("tfidf+xgboost-calibrated", lambda docs, labels: ("pipeline-xgb", 0.65, 0.60)),
    ])

    unbeatable = ModelVersionModel(
        name="operation_classifier", version="9.9.9", algorithm="tfidf+logreg-calibrated",
        artifact_path="builtin", accuracy=1.0, f1_score=0.90,
        training_samples=1000, is_active=True)
    db_session.add(unbeatable)
    db_session.commit()

    report = retrain(db_session)

    assert report["status"] == "TRAINED_NOT_PROMOTED"
    assert report["algorithm"] == "tfidf+xgboost-calibrated"  # meilleur des deux candidats (0.60 > 0.55)
    db_session.refresh(unbeatable)
    assert unbeatable.is_active is True

    new_versions = db_session.query(ModelVersionModel).filter(
        ModelVersionModel.version != "9.9.9", ModelVersionModel.algorithm != "keyword").all()
    assert len(new_versions) == 2
    assert all(not v.is_active for v in new_versions)  # aucun des deux candidats n'est activé
