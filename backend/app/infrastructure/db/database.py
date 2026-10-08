"""Connexion SQLAlchemy à MySQL 8. La session est fournie aux couches
supérieures par injection de dépendances (voir core/dependencies)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,   # évite les connexions mortes (timeout MySQL)
    pool_recycle=3600,
    # Sans ce paramètre, PyMySQL peut négocier un charset qui corrompt les
    # caractères accentués et cadratins (bug réel constaté : "—" stocké
    # comme "â€"") — utf8mb4 correspond au charset de la base (schema.sql).
    connect_args={"charset": "utf8mb4"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
