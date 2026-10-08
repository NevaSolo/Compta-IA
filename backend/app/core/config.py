"""Configuration centrale de l'application, chargée depuis les variables
d'environnement (fichier .env). Toute la configuration transite par cet
objet unique : aucune constante magique ailleurs dans le code."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de données
    database_url: str = "mysql+pymysql://compta_user:compta_pass@localhost:3306/compta_ia_db"

    # Sécurité
    secret_key: str = "dev-secret-key-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Stockage
    upload_dir: str = "./storage/uploads"
    models_dir: str = "./storage/models"
    max_upload_size_mb: int = 15
    allowed_mime_types: tuple[str, ...] = ("application/pdf", "image/jpeg", "image/png")

    # OCR
    ocr_languages: str = "fr,en"
    ocr_fallback_threshold: float = 0.55
    ocr_reject_threshold: float = 0.40

    # Métier
    default_vat_rate: float = 0.20
    default_currency: str = "MGA"
    company_name: str = "Entreprise"

    # Score de confiance (poids validés en Phase 6)
    confidence_w_ocr: float = 0.25
    confidence_w_extraction: float = 0.30
    confidence_w_classification: float = 0.25
    confidence_w_accounts: float = 0.20

    # Réentraînement
    retrain_correction_threshold: int = 50

    @property
    def ocr_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
