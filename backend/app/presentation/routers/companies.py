"""Router de gestion des entreprises (multi-tenant) — réservé à
l'administrateur global de la plateforme."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.domain.entities import Company, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import MySQLAuditRepository, MySQLCompanyRepository
from app.presentation.schemas import CompanyActiveUpdate, CompanyCreate, CompanyOut

router = APIRouter(prefix="/api/companies", tags=["Entreprises"])


def _to_out(company: Company) -> CompanyOut:
    return CompanyOut(id=company.id, name=company.name, nif=company.nif,
                      stat=company.stat, address=company.address,
                      is_active=company.is_active)


@router.post("", response_model=CompanyOut, status_code=201,
             summary="Créer une entreprise (Admin)")
def create_company(payload: CompanyCreate, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    company = MySQLCompanyRepository(db).create(Company(
        id=None, name=payload.name, nif=payload.nif, stat=payload.stat,
        address=payload.address))
    MySQLAuditRepository(db).log(admin.id, "COMPANY_CREATED", "company", company.id,
                                 new_value={"name": company.name})
    return _to_out(company)


@router.get("", response_model=list[CompanyOut],
            summary="Lister les entreprises (Admin)")
def list_companies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_to_out(c) for c in MySQLCompanyRepository(db).list_all()]


@router.patch("/{company_id}/active", response_model=CompanyOut,
              summary="Activer/désactiver une entreprise (Admin)")
def set_company_active(company_id: int, payload: CompanyActiveUpdate,
                       admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    company = MySQLCompanyRepository(db).set_active(company_id, payload.is_active)
    if company is None:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    MySQLAuditRepository(db).log(
        admin.id, "COMPANY_ACTIVATED" if payload.is_active else "COMPANY_DEACTIVATED",
        "company", company_id, new_value={"is_active": payload.is_active})
    return _to_out(company)
