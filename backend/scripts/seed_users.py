"""Crée l'entreprise de démonstration et les utilisateurs initiaux
(admin plateforme + comptable rattaché à l'entreprise démo).
Usage :  python -m scripts.seed_users   (depuis backend/, .env configuré)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402
from app.infrastructure.db.database import SessionLocal  # noqa: E402
from app.infrastructure.db.models import CompanyModel, UserModel  # noqa: E402
from sqlalchemy import select  # noqa: E402

DEMO_COMPANY_NAME = "Entreprise Démonstration"

USERS = [
    # (email, mot de passe, nom, rôle, appartient à l'entreprise démo ?)
    ("admin@compta-ia.mg", "Admin2026!", "Administrateur", "ADMIN", False),
    ("comptable@compta-ia.mg", "Compta2026!", "Comptable Démonstration", "COMPTABLE", True),
]


def main() -> None:
    db = SessionLocal()
    try:
        company = db.scalar(select(CompanyModel).where(CompanyModel.name == DEMO_COMPANY_NAME))
        if company is None:
            company = CompanyModel(name=DEMO_COMPANY_NAME)
            db.add(company)
            db.flush()
            print(f"+ Entreprise « {DEMO_COMPANY_NAME} » créée (id={company.id})")
        else:
            print(f"= Entreprise « {DEMO_COMPANY_NAME} » existe déjà (id={company.id})")

        for email, password, full_name, role, in_demo_company in USERS:
            if db.scalar(select(UserModel).where(UserModel.email == email)):
                print(f"= {email} existe déjà")
                continue
            db.add(UserModel(email=email, password_hash=hash_password(password),
                             full_name=full_name, role=role,
                             company_id=company.id if in_demo_company else None))
            print(f"+ {email} créé ({role})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
