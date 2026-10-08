"""Tests d'intégration de l'authentification et du RBAC."""


def test_login_success(client, comptable_user):
    response = client.post("/api/auth/login", json={
        "email": "comptable@test.mg", "password": "Compta1234!"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "COMPTABLE"
    assert "access_token" in body


def test_login_wrong_password(client, comptable_user):
    response = client.post("/api/auth/login", json={
        "email": "comptable@test.mg", "password": "MauvaisMotDePasse"})
    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post("/api/auth/login", json={
        "email": "inconnu@test.mg", "password": "peu-importe123"})
    assert response.status_code == 401


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "comptable@test.mg"


def test_comptable_cannot_create_user(client, auth_headers):
    """RBAC : la création d'utilisateur est réservée à l'Administrateur."""
    response = client.post("/api/auth/users", headers=auth_headers, json={
        "email": "nouveau@test.mg", "password": "Password1234",
        "full_name": "Nouveau", "role": "COMPTABLE"})
    assert response.status_code == 403


def test_admin_can_create_user(client, db_session, admin_user, company):
    login = client.post("/api/auth/login", json={
        "email": "admin@test.mg", "password": "Admin1234!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post("/api/auth/users", headers=headers, json={
        "email": "nouveau@test.mg", "password": "Password1234",
        "full_name": "Nouveau Comptable", "role": "COMPTABLE", "company_id": company.id})
    assert response.status_code == 201
    assert response.json()["role"] == "COMPTABLE"


def test_admin_creating_comptable_without_company_fails(client, admin_user):
    headers = _admin_headers(client)
    response = client.post("/api/auth/users", headers=headers, json={
        "email": "orphelin@test.mg", "password": "Password1234",
        "full_name": "Orphelin", "role": "COMPTABLE"})
    assert response.status_code == 422


def test_health_endpoint_is_public(client):
    assert client.get("/api/health").status_code == 200


def _admin_headers(client):
    login = client.post("/api/auth/login", json={
        "email": "admin@test.mg", "password": "Admin1234!"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class TestUserManagement:
    """Gestion des utilisateurs (Admin) — cas d'utilisation "Gérer les
    utilisateurs et les rôles" du diagramme de cas d'utilisation."""

    def test_admin_can_deactivate_a_user(self, client, db_session, admin_user, comptable_user):
        headers = _admin_headers(client)
        response = client.patch(f"/api/auth/users/{comptable_user.id}/active",
                                headers=headers, json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        # Le compte désactivé ne peut plus se connecter.
        login = client.post("/api/auth/login", json={
            "email": "comptable@test.mg", "password": "Compta1234!"})
        assert login.status_code == 401

    def test_admin_cannot_deactivate_own_account(self, client, admin_user):
        headers = _admin_headers(client)
        response = client.patch(f"/api/auth/users/{admin_user.id}/active",
                                headers=headers, json={"is_active": False})
        assert response.status_code == 422

    def test_comptable_cannot_deactivate_a_user(self, client, auth_headers, admin_user):
        response = client.patch(f"/api/auth/users/{admin_user.id}/active",
                                headers=auth_headers, json={"is_active": False})
        assert response.status_code == 403

    def test_deactivate_unknown_user_returns_404(self, client, admin_user):
        headers = _admin_headers(client)
        response = client.patch("/api/auth/users/9999/active",
                                headers=headers, json={"is_active": False})
        assert response.status_code == 404

    def test_admin_can_list_users(self, client, admin_user, comptable_user):
        headers = _admin_headers(client)
        response = client.get("/api/auth/users", headers=headers)
        assert response.status_code == 200
        emails = {u["email"] for u in response.json()}
        assert "admin@test.mg" in emails and "comptable@test.mg" in emails
