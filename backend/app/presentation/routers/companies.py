"""Router de gestion des entreprises (multi-tenant) — réservé à
l'administrateur global de la plateforme."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import branding
from app.core.dependencies import get_current_user, require_admin, require_company_admin
from app.domain.entities import Company, Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import MySQLAuditRepository, MySQLCompanyRepository
from app.presentation.schemas import (
    CompanyActiveUpdate, CompanyBrandingUpdate, CompanyCreate, CompanyOut,
)

router = APIRouter(prefix="/api/companies", tags=["Entreprises"])


def _to_out(company: Company) -> CompanyOut:
    return CompanyOut(id=company.id, name=company.name, nif=company.nif,
                      stat=company.stat, address=company.address,
                      is_active=company.is_active,
                      logo_version=branding.image_version(company.logo_path))


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


# ------------------------------------------------- Identité visuelle (logo, nom)
def _company_for_members(company_id: int, user: User, db: Session) -> Company:
    """Entreprise visible par ses membres (et par l'ADMIN global) : 404 sinon,
    pour ne pas révéler l'existence d'une autre entreprise."""
    company = MySQLCompanyRepository(db).get_by_id(company_id)
    if company is None or (user.role != Role.ADMIN and user.company_id != company_id):
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return company


def _company_for_editing(company_id: int, user: User, db: Session) -> Company:
    return _company_for_members(company_id, user, db)  # le rôle est déjà imposé par la dépendance


@router.get("/{company_id}/logo", summary="Logo de l'entreprise (membres de l'entreprise)")
def get_logo(company_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    company = _company_for_members(company_id, user, db)
    data = branding.read_image(company.logo_path) if company.logo_path else None
    if data is None:
        raise HTTPException(status_code=404, detail="Aucun logo")
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.put("/{company_id}/logo", response_model=CompanyOut,
            summary="Définir le logo (Admin d'entreprise ou Admin)")
async def upload_logo(company_id: int, file: UploadFile = File(...),
                      user: User = Depends(require_company_admin),
                      db: Session = Depends(get_db)):
    _company_for_editing(company_id, user, db)
    try:
        data = branding.process_logo(await file.read())
    except branding.InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    name = branding.save_image(f"company_{company_id}.png", data)
    company = MySQLCompanyRepository(db).update_branding(company_id, logo_path=name)
    MySQLAuditRepository(db).log(user.id, "COMPANY_LOGO_UPDATED", "company", company_id)
    return _to_out(company)


@router.delete("/{company_id}/logo", response_model=CompanyOut,
               summary="Supprimer le logo (Admin d'entreprise ou Admin)")
def delete_logo(company_id: int, user: User = Depends(require_company_admin),
                db: Session = Depends(get_db)):
    company = _company_for_editing(company_id, user, db)
    branding.delete_image(company.logo_path)
    updated = MySQLCompanyRepository(db).update_branding(company_id, logo_path=None)
    MySQLAuditRepository(db).log(user.id, "COMPANY_LOGO_REMOVED", "company", company_id)
    return _to_out(updated)


@router.patch("/{company_id}/branding", response_model=CompanyOut,
              summary="Modifier le nom affiché (Admin d'entreprise ou Admin)")
def update_company_name(company_id: int, payload: CompanyBrandingUpdate,
                        user: User = Depends(require_company_admin),
                        db: Session = Depends(get_db)):
    company = _company_for_editing(company_id, user, db)
    updated = MySQLCompanyRepository(db).update_branding(company_id, name=payload.name.strip())
    MySQLAuditRepository(db).log(user.id, "COMPANY_RENAMED", "company", company_id,
                                 old_value={"name": company.name},
                                 new_value={"name": updated.name})
    return _to_out(updated)
