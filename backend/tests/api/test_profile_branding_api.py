"""Personnalisation du profil (photo, thème, mot de passe) et identité visuelle
de l'entreprise (logo, nom) : droits, validation des images, cloisonnement."""
import io

import pytest
from PIL import Image

from app.core import branding
from app.core.security import hash_password
from app.infrastructure.db.models import CompanyModel, UserModel


@pytest.fixture(autouse=True)
def isolated_branding_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "branding_dir", lambda: tmp_path)


def _png(size=(600, 300), color=(200, 30, 30, 255), fmt="PNG"):
    buffer = io.BytesIO()
    image = Image.new("RGBA" if fmt == "PNG" else "RGB", size, color if fmt == "PNG" else color[:3])
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _files(content, name="x.png", mime="image/png"):
    return {"file": (name, content, mime)}


def _login(client, email, password):
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def company_admin(db_session, company):
    user = UserModel(email="boss@test.mg", full_name="Chef Entreprise", role="ENTREPRISE_ADMIN",
                     company_id=company.id, password_hash=hash_password("Boss12345!"))
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def boss_headers(client, company_admin):
    return _login(client, "boss@test.mg", "Boss12345!")


@pytest.fixture()
def other_company_admin_headers(client, db_session):
    other = CompanyModel(name="Autre Société")
    db_session.add(other)
    db_session.commit()
    db_session.add(UserModel(email="other@test.mg", full_name="Autre Chef", role="ENTREPRISE_ADMIN",
                             company_id=other.id, password_hash=hash_password("Other12345!")))
    db_session.commit()
    return _login(client, "other@test.mg", "Other12345!")


class TestProfile:
    def test_default_theme_and_accent(self, client, auth_headers):
        me = client.get("/api/auth/me", headers=auth_headers).json()
        assert (me["theme"], me["accent"]) == ("auto", "blue")
        assert me["avatar_version"] is None and me["company_logo_version"] is None

    def test_update_name_theme_and_accent(self, client, auth_headers):
        response = client.patch("/api/auth/me/profile", headers=auth_headers,
                                json={"full_name": "Nouveau Nom", "theme": "dark", "accent": "violet"})
        assert response.status_code == 200
        me = client.get("/api/auth/me", headers=auth_headers).json()
        assert (me["full_name"], me["theme"], me["accent"]) == ("Nouveau Nom", "dark", "violet")

    @pytest.mark.parametrize("payload", [{"theme": "neon"}, {"accent": "pink"}, {"full_name": "A"}])
    def test_invalid_values_are_rejected(self, client, auth_headers, payload):
        assert client.patch("/api/auth/me/profile", headers=auth_headers, json=payload).status_code == 422

    def test_profile_cannot_change_role_or_company(self, client, auth_headers, comptable_user):
        client.patch("/api/auth/me/profile", headers=auth_headers,
                     json={"role": "ADMIN", "company_id": 999})
        me = client.get("/api/auth/me", headers=auth_headers).json()
        assert me["role"] == "COMPTABLE" and me["company_id"] == comptable_user.company_id

    def test_change_password(self, client, auth_headers):
        bad = client.post("/api/auth/me/password", headers=auth_headers,
                          json={"current_password": "faux", "new_password": "Nouveau1234!"})
        assert bad.status_code == 422
        ok = client.post("/api/auth/me/password", headers=auth_headers,
                         json={"current_password": "Compta1234!", "new_password": "Nouveau1234!"})
        assert ok.status_code == 204
        assert client.post("/api/auth/login", json={
            "email": "comptable@test.mg", "password": "Nouveau1234!"}).status_code == 200
        assert client.post("/api/auth/login", json={
            "email": "comptable@test.mg", "password": "Compta1234!"}).status_code == 401

    def test_new_password_must_be_long_and_different(self, client, auth_headers):
        short = client.post("/api/auth/me/password", headers=auth_headers,
                            json={"current_password": "Compta1234!", "new_password": "court"})
        same = client.post("/api/auth/me/password", headers=auth_headers,
                           json={"current_password": "Compta1234!", "new_password": "Compta1234!"})
        assert short.status_code == 422 and same.status_code == 422


class TestAvatar:
    def test_upload_is_square_256_and_served(self, client, auth_headers):
        response = client.put("/api/auth/me/avatar", headers=auth_headers, files=_files(_png((800, 400))))
        assert response.status_code == 200
        assert response.json()["avatar_version"] is not None
        image = Image.open(io.BytesIO(client.get("/api/auth/me/avatar", headers=auth_headers).content))
        assert image.size == (256, 256)

    def test_jpeg_is_accepted_and_reencoded_as_png(self, client, auth_headers):
        jpeg = _png((300, 300), fmt="JPEG")
        assert client.put("/api/auth/me/avatar", headers=auth_headers,
                          files=_files(jpeg, "p.jpg", "image/jpeg")).status_code == 200
        served = client.get("/api/auth/me/avatar", headers=auth_headers)
        assert served.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(served.content)).format == "PNG"

    @pytest.mark.parametrize("content", [
        b"pas une image",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    ])
    def test_non_raster_content_is_rejected(self, client, auth_headers, content):
        assert client.put("/api/auth/me/avatar", headers=auth_headers,
                          files=_files(content)).status_code == 422

    def test_oversized_file_is_rejected(self, client, auth_headers):
        assert client.put("/api/auth/me/avatar", headers=auth_headers,
                          files=_files(b"0" * (branding.MAX_IMAGE_BYTES + 1))).status_code == 422

    def test_delete_avatar(self, client, auth_headers):
        client.put("/api/auth/me/avatar", headers=auth_headers, files=_files(_png()))
        assert client.delete("/api/auth/me/avatar", headers=auth_headers).json()["avatar_version"] is None
        assert client.get("/api/auth/me/avatar", headers=auth_headers).status_code == 404

    def test_requires_authentication(self, client):
        assert client.get("/api/auth/me/avatar").status_code == 401


class TestCompanyBranding:
    def test_company_admin_sets_logo_keeping_aspect_ratio_and_transparency(
            self, client, boss_headers, company):
        response = client.put(f"/api/companies/{company.id}/logo", headers=boss_headers,
                              files=_files(_png((1200, 600), (0, 0, 0, 0))))
        assert response.status_code == 200
        logo = Image.open(io.BytesIO(
            client.get(f"/api/companies/{company.id}/logo", headers=boss_headers).content))
        assert logo.size == (512, 256) and logo.mode == "RGBA"
        assert logo.getpixel((10, 10))[3] == 0  # la transparence est conservée

    def test_every_member_sees_the_logo_and_name_in_me(
            self, client, boss_headers, auth_headers, company):
        client.put(f"/api/companies/{company.id}/logo", headers=boss_headers, files=_files(_png()))
        client.patch(f"/api/companies/{company.id}/branding", headers=boss_headers,
                     json={"name": "Ma Société SARL"})
        me = client.get("/api/auth/me", headers=auth_headers).json()  # un simple comptable
        assert me["company_name"] == "Ma Société SARL"
        assert me["company_logo_version"] is not None
        assert client.get(f"/api/companies/{company.id}/logo", headers=auth_headers).status_code == 200

    def test_accountant_cannot_change_branding(self, client, auth_headers, company):
        assert client.put(f"/api/companies/{company.id}/logo", headers=auth_headers,
                          files=_files(_png())).status_code == 403
        assert client.patch(f"/api/companies/{company.id}/branding", headers=auth_headers,
                            json={"name": "Piratée"}).status_code == 403

    def test_other_company_is_invisible_and_untouchable(
            self, client, boss_headers, other_company_admin_headers, company):
        client.put(f"/api/companies/{company.id}/logo", headers=boss_headers, files=_files(_png()))
        assert client.get(f"/api/companies/{company.id}/logo",
                          headers=other_company_admin_headers).status_code == 404
        assert client.put(f"/api/companies/{company.id}/logo", headers=other_company_admin_headers,
                          files=_files(_png())).status_code == 404
        assert client.patch(f"/api/companies/{company.id}/branding", headers=other_company_admin_headers,
                            json={"name": "Vol"}).status_code == 404

    def test_global_admin_can_manage_any_company(self, client, admin_user, company):
        headers = _login(client, "admin@test.mg", "Admin1234!")
        assert client.put(f"/api/companies/{company.id}/logo", headers=headers,
                          files=_files(_png())).status_code == 200
        assert client.patch(f"/api/companies/{company.id}/branding", headers=headers,
                            json={"name": "Renommée"}).json()["name"] == "Renommée"

    def test_delete_logo(self, client, boss_headers, company):
        client.put(f"/api/companies/{company.id}/logo", headers=boss_headers, files=_files(_png()))
        assert client.delete(f"/api/companies/{company.id}/logo",
                             headers=boss_headers).json()["logo_version"] is None
        assert client.get(f"/api/companies/{company.id}/logo", headers=boss_headers).status_code == 404

    def test_invalid_logo_is_rejected(self, client, boss_headers, company):
        assert client.put(f"/api/companies/{company.id}/logo", headers=boss_headers,
                          files=_files(b"GIF89a-pas-un-png")).status_code == 422
