"""Installe les plans comptables du catalogue (idempotent) et rattache
l'entreprise de démonstration au plan malgache si elle n'en a pas.
Usage :  python -m scripts.install_charts   (depuis backend/, .env configuré)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog.installer import install_catalog  # noqa: E402
from app.infrastructure.db.database import SessionLocal  # noqa: E402

if __name__ == "__main__":
    db = SessionLocal()
    try:
        for code, report in install_catalog(db).items():
            print(f"{code} : {report}")
    finally:
        db.close()
