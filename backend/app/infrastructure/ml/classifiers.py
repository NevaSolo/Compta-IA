"""Classification du type d'opération et suggestion de comptes (Phase 6,
étapes 6-7).

Deux implémentations du port OperationClassifier :
- KeywordClassifier : version 0.1.0 d'amorçage (cold start), dictionnaire
  multilingue déterministe — active tant que < 150 factures validées ;
- SklearnClassifier : TF-IDF + régression logistique calibrée, chargée
  depuis un artefact joblib versionné (model_versions).

Le suggesteur de comptes est CONTRAINT par la liste `candidates` de la
règle comptable : le ML n'impute jamais hors du cadre du PCG.
"""
import logging
from pathlib import Path

from app.core.config import get_settings
from app.domain.entities import OperationType, Supplier
from app.domain.ports import (
    AccountSuggester, AccountSuggestion, ClassificationResult, OperationClassifier,
)

logger = logging.getLogger(__name__)

# Dictionnaire multilingue (fr / en / mg) par classe d'opération
KEYWORDS: dict[OperationType, list[str]] = {
    OperationType.ACHAT_IMMOBILISATION: [
        "ordinateur", "computer", "laptop", "serveur", "server", "imprimante",
        "printer", "vehicule", "véhicule", "voiture", "camion", "moto", "machine",
        "mobilier", "bureau", "furniture", "climatiseur", "materiel", "matériel",
        "equipement", "équipement", "equipment", "photocopieur", "fiara", "milina",
    ],
    OperationType.ACHAT_SERVICES: [
        "prestation", "service", "honoraires", "consulting", "conseil", "audit",
        "maintenance", "reparation", "réparation", "location", "loyer", "rent",
        "transport", "livraison", "delivery", "formation", "training", "assurance",
        "insurance", "publicite", "publicité", "advertising", "abonnement",
        "internet", "telephone", "téléphone", "electricite", "électricité",
        "jirama", "eau", "hofan-trano", "nettoyage", "gardiennage", "securite",
    ],
    OperationType.ACHAT_MARCHANDISES: [
        # Bug réel corrigé : "unité", "pièces", "qté", "article", "produit"
        # ont été retirés — ce sont des en-têtes de tableau génériques
        # (« Code article », « Unité de vente », « Qté ») présents sur
        # QUASIMENT TOUTE facture, quelle que soit sa nature. Leur présence
        # ici faisait basculer vers ACHAT_MARCHANDISES même une facture de
        # maintenance ou d'achat d'ordinateur (1 mot-clé métier réel contre
        # 2 mots-clés de tableau génériques). Ne restent que des termes
        # réellement indicatifs d'une revente/négoce de biens.
        "marchandise", "marchandises", "goods", "riz", "vary", "sac", "carton",
        "lot", "entola", "revente",
    ],
}

# Mots-clés → compte précis, pour affiner la suggestion PARMI les candidats
ACCOUNT_KEYWORDS: dict[str, list[str]] = {
    "6061": ["eau", "electricite", "électricité", "jirama", "energie", "énergie", "rano"],
    "6064": ["papier", "stylo", "fourniture", "bureau", "cartouche", "toner"],
    "613":  ["location", "loyer", "bail", "rent", "hofan-trano"],
    "615":  ["entretien", "reparation", "réparation", "maintenance", "repair"],
    "616":  ["assurance", "insurance", "prime"],
    "617":  ["etude", "étude", "recherche", "study"],
    "611":  ["sous-traitance", "subcontract"],
    "621":  ["interim", "intérim", "personnel exterieur"],
    "622":  ["honoraires", "avocat", "notaire", "expert", "comptable", "consulting", "conseil", "audit"],
    "623":  ["publicite", "publicité", "advertising", "annonce", "affiche", "marketing"],
    "624":  ["transport", "livraison", "fret", "delivery", "shipping"],
    "625":  ["mission", "deplacement", "déplacement", "hotel", "hôtel", "restaurant", "billet"],
    "626":  ["telephone", "téléphone", "internet", "timbre", "postal", "telma", "orange", "airtel"],
    "627":  ["frais bancaires", "commission", "agios", "banque"],
    "2181": ["vehicule", "véhicule", "voiture", "camion", "moto", "fiara"],
    "2182": ["ordinateur", "computer", "laptop", "serveur", "imprimante", "printer", "scanner"],
    "2183": ["mobilier", "bureau", "chaise", "table", "armoire", "furniture"],
    "204":  ["logiciel", "software", "licence", "license"],
}


class KeywordClassifier(OperationClassifier):
    """Classifieur d'amorçage : score = proportion de mots-clés de la classe
    présents dans le texte. Déterministe, explicable, multilingue."""

    VERSION = "keyword-0.1.0"

    def classify(self, text: str, supplier_name: str | None,
                 amount: float | None) -> ClassificationResult:
        lowered = f"{text} {supplier_name or ''}".lower()
        scores: dict[str, float] = {}
        for operation, keywords in KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in lowered)
            scores[operation.value] = hits
        total_hits = sum(scores.values())
        if total_hits == 0:
            # aucun indice : AUTRE avec probabilité faible → vigilance du comptable
            probabilities = {op.value: 0.25 for op in OperationType}
            return ClassificationResult(operation_type=OperationType.AUTRE,
                                        probability=0.25, probabilities=probabilities,
                                        model_version=self.VERSION)
        probabilities = {op: round(score / total_hits, 4) for op, score in scores.items()}
        probabilities[OperationType.AUTRE.value] = 0.0
        best = max(scores, key=scores.get)
        return ClassificationResult(
            operation_type=OperationType(best),
            probability=min(0.85, probabilities[best]),  # plafond : humilité du cold start
            probabilities=probabilities, model_version=self.VERSION)


class SklearnClassifier(OperationClassifier):
    """Classifieur statistique chargé depuis un artefact joblib
    (pipeline TF-IDF + LogisticRegression calibrée, produit par training.py)."""

    def __init__(self, artifact_path: str, version: str):
        import joblib
        self.pipeline = joblib.load(artifact_path)
        self.version = version

    def classify(self, text: str, supplier_name: str | None,
                 amount: float | None) -> ClassificationResult:
        document = f"{text} {supplier_name or ''}"
        probabilities = self.pipeline.predict_proba([document])[0]
        classes = list(self.pipeline.classes_)
        proba_map = {cls: round(float(p), 4) for cls, p in zip(classes, probabilities)}
        best = max(proba_map, key=proba_map.get)
        return ClassificationResult(operation_type=OperationType(best),
                                    probability=proba_map[best],
                                    probabilities=proba_map, model_version=self.version)


def load_active_classifier(db=None) -> OperationClassifier:
    """Charge la version active du classifieur depuis model_versions,
    sinon retombe sur le classifieur à mots-clés (cold start)."""
    if db is not None:
        try:
            from sqlalchemy import select
            from app.infrastructure.db.models import ModelVersionModel
            row = db.scalar(select(ModelVersionModel).where(
                ModelVersionModel.name == "operation_classifier",
                ModelVersionModel.is_active.is_(True)))
            if row and row.artifact_path != "builtin" and Path(row.artifact_path).exists():
                return SklearnClassifier(row.artifact_path, row.version)
        except Exception as exc:
            logger.warning("Chargement du modèle actif impossible (%s) : "
                           "repli sur le classifieur à mots-clés", exc)
    return KeywordClassifier()


class ConstrainedAccountSuggester(AccountSuggester):
    """Suggère le compte précis PARMI les candidats de la règle :
    1. compte habituel du fournisseur s'il figure dans les candidats (0,90) ;
    2. mots-clés du libellé → compte (0,75) ;
    3. compte par défaut de la règle (0,50)."""

    def __init__(self, account_code_by_id: dict[int, str] | None = None):
        self.account_code_by_id = account_code_by_id or {}

    def suggest(self, text: str, supplier: Supplier | None,
                candidates: list[str], default: str) -> AccountSuggestion:
        # 1. Historique fournisseur (signal le plus fiable)
        if supplier and supplier.default_account_id:
            code = self.account_code_by_id.get(supplier.default_account_id)
            if code and code in candidates:
                return AccountSuggestion(account_code=code, confidence=0.90,
                                         suggested_by_ml=True)
        # 2. Mots-clés du libellé
        lowered = text.lower()
        best_code, best_hits = None, 0
        for code in candidates:
            hits = sum(1 for kw in ACCOUNT_KEYWORDS.get(code, []) if kw in lowered)
            if hits > best_hits:
                best_code, best_hits = code, hits
        if best_code:
            return AccountSuggestion(account_code=best_code,
                                     confidence=min(0.75, 0.5 + 0.1 * best_hits),
                                     suggested_by_ml=True)
        # 3. Défaut de la règle
        return AccountSuggestion(account_code=default, confidence=0.50,
                                 suggested_by_ml=False)
