"""Stockage des factures sur le système de fichiers local.
Les fichiers ne sont jamais stockés en BLOB (anti-pattern validé en Phase 3)."""
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.domain.ports import FileStorage


class LocalFileStorage(FileStorage):
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or get_settings().upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, filename: str) -> str:
        """Nom de fichier aléatoire (UUID) : évite les collisions et
        neutralise toute injection de chemin via le nom d'origine."""
        extension = Path(filename).suffix.lower()
        safe_name = f"{uuid.uuid4().hex}{extension}"
        path = self.base_dir / safe_name
        path.write_bytes(content)
        return str(path)

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def delete(self, path: str) -> None:
        """Supprime un fichier du stockage ; ignore un fichier déjà absent et refuse tout
        chemin situé hors du dossier de stockage (jamais de suppression arbitraire)."""
        target = Path(path).resolve()
        if self.base_dir.resolve() not in target.parents:
            return
        target.unlink(missing_ok=True)
