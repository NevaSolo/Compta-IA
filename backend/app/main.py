"""Point d'entrée FastAPI.

Lancement :  uvicorn app.main:app --reload
Swagger :    http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.presentation.routers import auth, companies, entries, invoices, misc

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(
    title="Compta-IA — Génération automatique des écritures comptables",
    description=(
        "Système intelligent de génération automatique des écritures comptables "
        "à partir de factures commerciales (OCR + NLP + moteur de règles PCG "
        "malgache 2005 + Machine Learning). L'IA propose, le comptable dispose : "
        "aucune écriture n'est enregistrée sans validation humaine."),
    version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(invoices.router)
app.include_router(entries.router)
app.include_router(misc.router)


@app.get("/api/health", tags=["Système"])
def health():
    return {"status": "ok"}
