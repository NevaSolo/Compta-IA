"""Fixtures partagées : base SQLite en mémoire (miroir du schéma MySQL pour
les tests, aucune dépendance à un serveur MySQL réel) + client de test
FastAPI avec la dépendance get_db substituée."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.infrastructure.db.database import Base, get_db
from app.infrastructure.db.models import (
    AccountModel, AccountingRuleModel, ChartModel, CompanyModel, UserModel,
)
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def chart(db_session):
    """Plan comptable de test (équivalent du PCG malgache) : les entreprises de test
    en ont un, comme toute entreprise en production (choix obligatoire)."""
    row = db_session.query(ChartModel).filter_by(code="PCG_TEST").first()
    if row is None:
        row = ChartModel(code="PCG_TEST", name="Plan de test", country="MG", version="1")
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
    return row


@pytest.fixture()
def company(db_session, chart):
    """L'unique entreprise utilisée par la plupart des tests — comptable_user
    y est rattaché, ce qui rend le cloisonnement multi-tenant transparent
    pour tous les tests mono-entreprise existants."""
    row = CompanyModel(name="Entreprise Test", chart_id=chart.id)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture()
def admin_user(db_session):
    """L'ADMIN est l'administrateur global de la plateforme : aucune
    entreprise (company_id=None), il voit/gère tout."""
    user = UserModel(email="admin@test.mg", full_name="Admin Test", role="ADMIN",
                     password_hash=hash_password("Admin1234!"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def comptable_user(db_session, company):
    user = UserModel(email="comptable@test.mg", full_name="Comptable Test",
                     role="COMPTABLE", company_id=company.id,
                     password_hash=hash_password("Compta1234!"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(client, comptable_user):
    response = client.post("/api/auth/login", json={
        "email": "comptable@test.mg", "password": "Compta1234!"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def minimal_chart_of_accounts(db_session, chart):
    """Un sous-ensemble du plan comptable suffisant pour générer une écriture
    d'achat de marchandises de bout en bout."""
    accounts = [
        AccountModel(chart_id=chart.id, code="607", label="Achats de marchandises", account_class=6,
                    normal_balance="DEBIT"),
        AccountModel(chart_id=chart.id, code="4456", label="TVA déductible", account_class=4,
                    normal_balance="DEBIT"),
        AccountModel(chart_id=chart.id, code="401", label="Fournisseurs", account_class=4,
                    normal_balance="CREDIT"),
    ]
    db_session.add_all(accounts)
    db_session.add(AccountingRuleModel(
        chart_id=chart.id, code="R-ACHAT-MARCH-01", operation_type="ACHAT_MARCHANDISES",
        description="Achat de marchandises", priority=100,
        template={"lines": [
            {"role": "charge", "side": "D", "amount": "HT",
             "default_account": "607", "ml_refinable": True, "candidates": ["607"]},
            {"role": "tva", "side": "D", "amount": "VAT",
             "default_account": "4456", "ml_refinable": False},
            {"role": "tiers", "side": "C", "amount": "TTC",
             "default_account": "401", "ml_refinable": False},
        ]}))
    db_session.commit()
    return accounts
