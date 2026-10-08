"""Tests d'intégration du cloisonnement multi-entreprise (company_id) :
- un ADMIN d'entreprise ne gère que ses propres comptables ;
- une facture/écriture d'une entreprise est invisible depuis une autre ;
- seul l'ADMIN plateforme peut créer des entreprises."""
import io

from app.core.security import hash_password
from app.infrastructure.db.models import CompanyModel, InvoiceModel, UserModel


def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _make_entreprise_admin(db_session, company):
    user = UserModel(email="entreprise.admin@test.mg", full_name="Admin Entreprise",
                     role="ENTREPRISE_ADMIN", company_id=company.id,
                     password_hash=hash_password("EntAdmin1234!"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_other_company_with_comptable(db_session):
    other_company = CompanyModel(name="Autre Entreprise")
    db_session.add(other_company)
    db_session.flush()
    other_user = UserModel(email="autre.comptable@test.mg", full_name="Autre Comptable",
                           role="COMPTABLE", company_id=other_company.id,
                           password_hash=hash_password("Autre1234!"))
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_company)
    db_session.refresh(other_user)
    return other_company, other_user


class TestCompanyManagement:
    def test_admin_can_create_company(self, client, admin_user):
        headers = _login(client, "admin@test.mg", "Admin1234!")
        response = client.post("/api/companies", headers=headers, json={"name": "Nouvelle SARL"})
        assert response.status_code == 201
        assert response.json()["name"] == "Nouvelle SARL"

    def test_comptable_cannot_create_company(self, client, auth_headers):
        response = client.post("/api/companies", headers=auth_headers, json={"name": "Intrus SARL"})
        assert response.status_code == 403

    def test_entreprise_admin_cannot_create_company(self, client, db_session, company):
        _make_entreprise_admin(db_session, company)
        headers = _login(client, "entreprise.admin@test.mg", "EntAdmin1234!")
        response = client.post("/api/companies", headers=headers, json={"name": "Filiale SARL"})
        assert response.status_code == 403


class TestEntrepriseAdminScope:
    def test_entreprise_admin_can_create_comptable_in_own_company(
            self, client, db_session, company):
        _make_entreprise_admin(db_session, company)
        headers = _login(client, "entreprise.admin@test.mg", "EntAdmin1234!")
        response = client.post("/api/auth/users", headers=headers, json={
            "email": "nouveau.comptable@test.mg", "password": "Password1234",
            "full_name": "Nouveau Comptable", "role": "COMPTABLE"})
        assert response.status_code == 201
        assert response.json()["company_id"] == company.id

    def test_entreprise_admin_cannot_create_another_entreprise_admin(
            self, client, db_session, company):
        _make_entreprise_admin(db_session, company)
        headers = _login(client, "entreprise.admin@test.mg", "EntAdmin1234!")
        response = client.post("/api/auth/users", headers=headers, json={
            "email": "autre.admin@test.mg", "password": "Password1234",
            "full_name": "Autre Admin", "role": "ENTREPRISE_ADMIN"})
        assert response.status_code == 403

    def test_entreprise_admin_only_sees_own_company_users(
            self, client, db_session, company, comptable_user):
        _make_entreprise_admin(db_session, company)
        _make_other_company_with_comptable(db_session)
        headers = _login(client, "entreprise.admin@test.mg", "EntAdmin1234!")
        response = client.get("/api/auth/users", headers=headers)
        assert response.status_code == 200
        emails = {u["email"] for u in response.json()}
        assert "comptable@test.mg" in emails  # sa propre entreprise
        assert "autre.comptable@test.mg" not in emails  # entreprise différente

    def test_admin_sees_users_from_all_companies(self, client, admin_user, db_session, company):
        _make_entreprise_admin(db_session, company)
        _make_other_company_with_comptable(db_session)
        headers = _login(client, "admin@test.mg", "Admin1234!")
        response = client.get("/api/auth/users", headers=headers)
        emails = {u["email"] for u in response.json()}
        assert "autre.comptable@test.mg" in emails


class TestInvoiceCrossTenantIsolation:
    def test_comptable_cannot_access_invoice_from_other_company(
            self, client, db_session, auth_headers, comptable_user):
        _other_company, other_user = _make_other_company_with_comptable(db_session)
        other_invoice = InvoiceModel(
            company_id=other_user.company_id, uploaded_by=other_user.id,
            original_filename="secret.pdf", storage_path="/tmp/secret.pdf",
            mime_type="application/pdf", file_size=10, status="ENTRIES_PROPOSED")
        db_session.add(other_invoice)
        db_session.commit()
        db_session.refresh(other_invoice)

        response = client.get(f"/api/invoices/{other_invoice.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_uploaded_invoice_is_scoped_to_uploader_company(
            self, client, auth_headers, comptable_user):
        upload = client.post(
            "/api/invoices", headers=auth_headers,
            files={"file": ("f.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")})
        assert upload.json()["company_id"] == comptable_user.company_id

    def test_admin_can_access_invoice_from_any_company(
            self, client, db_session, admin_user):
        _other_company, other_user = _make_other_company_with_comptable(db_session)
        other_invoice = InvoiceModel(
            company_id=other_user.company_id, uploaded_by=other_user.id,
            original_filename="visible.pdf", storage_path="/tmp/visible.pdf",
            mime_type="application/pdf", file_size=10, status="ENTRIES_PROPOSED")
        db_session.add(other_invoice)
        db_session.commit()
        db_session.refresh(other_invoice)

        headers = _login(client, "admin@test.mg", "Admin1234!")
        response = client.get(f"/api/invoices/{other_invoice.id}", headers=headers)
        assert response.status_code == 200
