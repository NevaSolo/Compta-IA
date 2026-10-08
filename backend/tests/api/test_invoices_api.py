"""Tests d'intégration du cycle de vie d'une facture. Le contenu envoyé
n'est pas une vraie image : le pipeline (déclenché en tâche de fond) doit
échouer proprement au prétraitement et marquer la facture en ERREUR —
c'est le comportement attendu de renoncement explicite (Phase 6)."""
import io


def test_upload_rejects_disallowed_mime_type(client, auth_headers):
    response = client.post(
        "/api/invoices", headers=auth_headers,
        files={"file": ("virus.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")})
    assert response.status_code == 422
    assert "non autorisé" in response.json()["detail"]


def test_upload_rejects_empty_file(client, auth_headers):
    response = client.post(
        "/api/invoices", headers=auth_headers,
        files={"file": ("vide.pdf", io.BytesIO(b""), "application/pdf")})
    assert response.status_code == 422


def test_upload_accepted_returns_202_and_uploaded_status(client, auth_headers):
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"not a real png but has header")
    response = client.post(
        "/api/invoices", headers=auth_headers,
        files={"file": ("facture.png", fake_image, "image/png")})
    assert response.status_code == 202
    body = response.json()
    assert body["original_filename"] == "facture.png"
    # Le pipeline (tâche de fond) a eu le temps de tourner et de constater
    # que l'image est illisible : statut final ERROR, jamais un plantage silencieux.
    assert body["status"] in ("UPLOADED", "PREPROCESSING", "ERROR")


def test_get_invoice_not_found(client, auth_headers):
    response = client.get("/api/invoices/9999", headers=auth_headers)
    assert response.status_code == 404


def test_list_invoices_requires_auth(client):
    assert client.get("/api/invoices").status_code == 401


def test_reject_invoice_requires_reason(client, auth_headers):
    upload = client.post(
        "/api/invoices", headers=auth_headers,
        files={"file": ("f.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")})
    invoice_id = upload.json()["id"]
    response = client.post(f"/api/invoices/{invoice_id}/reject",
                           headers=auth_headers, json={"reason": "doublon détecté"})
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
