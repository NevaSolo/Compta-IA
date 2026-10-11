"""Personnalisation : thèmes, couleurs d'accent et images (photo de profil,
logo d'entreprise). Les images sont ré-encodées côté serveur : on ne stocke
jamais le fichier envoyé tel quel (métadonnées EXIF, contenu actif, bombes de
décompression)."""
import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

THEMES = ("auto", "light", "dark")
ACCENTS = ("blue", "emerald", "violet", "rose", "amber", "slate")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
AVATAR_SIZE = 256   # carré, recadré au centre
LOGO_MAX = 512      # le logo garde ses proportions et sa transparence


class InvalidImageError(ValueError):
    pass


def _open(content: bytes) -> Image.Image:
    if len(content) > MAX_IMAGE_BYTES:
        raise InvalidImageError(f"Image trop volumineuse (maximum {MAX_IMAGE_BYTES // 1024 // 1024} Mo).")
    try:
        image = Image.open(io.BytesIO(content))
        if image.format not in ("PNG", "JPEG", "WEBP"):
            raise InvalidImageError("Format non accepté : utilisez PNG, JPEG ou WebP.")
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise InvalidImageError("Image trop grande (dimensions).")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Fichier image illisible.") from exc
    return ImageOps.exif_transpose(image)  # respecte l'orientation des photos de téléphone


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def process_avatar(content: bytes) -> bytes:
    image = _open(content).convert("RGBA")
    return _encode(ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS))


def process_logo(content: bytes) -> bytes:
    image = _open(content).convert("RGBA")
    image.thumbnail((LOGO_MAX, LOGO_MAX), Image.LANCZOS)
    return _encode(image)


def branding_dir() -> Path:
    path = Path(get_settings().upload_dir) / "branding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(name: str, data: bytes) -> str:
    """Écrit `branding/<name>` ; le nom est construit par le code (ids), jamais
    à partir d'une entrée utilisateur."""
    (branding_dir() / name).write_bytes(data)
    return name


def read_image(name: str) -> bytes | None:
    path = branding_dir() / Path(name).name  # Path.name : aucune traversée de dossier
    return path.read_bytes() if path.is_file() else None


def delete_image(name: str | None) -> None:
    if name:
        (branding_dir() / Path(name).name).unlink(missing_ok=True)


def image_version(name: str | None) -> int | None:
    """Horodatage du fichier : sert à invalider le cache côté navigateur."""
    if not name:
        return None
    path = branding_dir() / Path(name).name
    return int(path.stat().st_mtime) if path.is_file() else None
