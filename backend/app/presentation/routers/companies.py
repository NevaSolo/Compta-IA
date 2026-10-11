"""Router de gestion des entreprises (multi-tenant) — réservé à
l'administrateur global de la plateforme."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import branding
from app.core.dependencies import get_current_user, require_admin, require_company_admin
from app.domain.entities import Company, Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAuditRepository, MySQLChartRepository, MySQLCompanyRepository, MySQLEntryRepository,
    MySQLExchangeRateRepository,
)
from app.presentation.schemas import (
    ChartChoice, CompanyActiveUpdate, CompanyBrandingUpdate, CompanyCreate, CompanyOut,
    CurrencyUpdate, ExchangeRateIn, ExchangeRateOut,
)

router = APIRouter(prefix="/api/companies", tags=["Entreprises"])


def _to_out(company: Company) -> CompanyOut:
    return CompanyOut(id=company.id, name=company.name, nif=company.nif,
                      stat=company.stat, address=company.address,
                      is_active=company.is_active,
                      logo_version=branding.image_version(company.logo_path),
                      base_currency=company.base_currency, chart_id=company.chart_id)


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


# ------------------------------------------------ Devise et taux de change
@router.patch("/{company_id}/currency", response_model=CompanyOut,
              summary="Définir la devise de tenue de comptabilité (Admin d'entreprise ou Admin)")
def set_base_currency(company_id: int, payload: CurrencyUpdate,
                      user: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    company = _company_for_editing(company_id, user, db)
    if payload.base_currency == company.base_currency:
        return _to_out(company)
    if MySQLEntryRepository(db).count_validated(company_id) > 0:
        # Mélanger deux devises dans un même journal validé fausserait les totaux.
        raise HTTPException(
            status_code=409,
            detail="La devise ne peut plus être changée : des écritures sont déjà validées "
                   f"en {company.base_currency}.")
    updated = MySQLCompanyRepository(db).set_base_currency(company_id, payload.base_currency)
    MySQLAuditRepository(db).log(user.id, "COMPANY_CURRENCY_CHANGED", "company", company_id,
                                 old_value={"base_currency": company.base_currency},
                                 new_value={"base_currency": payload.base_currency})
    return _to_out(updated)


def _rate_out(rate) -> ExchangeRateOut:
    return ExchangeRateOut(id=rate.id, currency=rate.currency, rate=rate.rate,
                           effective_date=rate.effective_date)


@router.get("/{company_id}/rates", response_model=list[ExchangeRateOut],
            summary="Taux de change de l'entreprise (membres)")
def list_rates(company_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    _company_for_members(company_id, user, db)
    return [_rate_out(r) for r in MySQLExchangeRateRepository(db).list_for_company(company_id)]


@router.post("/{company_id}/rates", response_model=ExchangeRateOut, status_code=201,
             summary="Ajouter ou remplacer un taux (Admin d'entreprise ou Admin)")
def save_rate(company_id: int, payload: ExchangeRateIn,
              user: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    company = _company_for_editing(company_id, user, db)
    if payload.currency == company.base_currency:
        raise HTTPException(status_code=422,
                            detail="Pas de taux pour la devise de l'entreprise elle-même")
    rate = MySQLExchangeRateRepository(db).upsert(
        company_id, payload.currency, payload.rate, payload.effective_date)
    MySQLAuditRepository(db).log(user.id, "EXCHANGE_RATE_SAVED", "company", company_id,
                                 new_value={"currency": payload.currency, "rate": str(payload.rate),
                                            "effective_date": payload.effective_date.isoformat()})
    return _rate_out(rate)


@router.delete("/{company_id}/rates/{rate_id}", status_code=204,
               summary="Supprimer un taux (Admin d'entreprise ou Admin)")
def delete_rate(company_id: int, rate_id: int, user: User = Depends(require_company_admin),
                db: Session = Depends(get_db)):
    _company_for_editing(company_id, user, db)
    if not MySQLExchangeRateRepository(db).delete(company_id, rate_id):
        raise HTTPException(status_code=404, detail="Taux introuvable")
    MySQLAuditRepository(db).log(user.id, "EXCHANGE_RATE_DELETED", "company", company_id,
                                 old_value={"rate_id": rate_id})
    return Response(status_code=204)


# ------------------------------------------------------- Plan comptable
@router.put("/{company_id}/chart", response_model=CompanyOut,
            summary="Choisir le plan comptable de l'entreprise (Admin d'entreprise ou Admin)")
def choose_chart(company_id: int, payload: ChartChoice,
                 user: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    company = _company_for_editing(company_id, user, db)
    chart = MySQLChartRepository(db).get_by_id(payload.chart_id)
    if chart is None:
        raise HTTPException(status_code=404, detail="Plan comptable introuvable")
    if payload.chart_id == company.chart_id:
        return _to_out(company)
    if MySQLEntryRepository(db).count_for_company(company_id) > 0:
        # Les écritures existantes pointent vers les comptes de l'ancien plan.
        raise HTTPException(
            status_code=409,
            detail="Le plan comptable ne peut plus être changé : des écritures existent déjà "
                   "avec le plan actuel.")
    updated = MySQLCompanyRepository(db).set_chart(company_id, payload.chart_id)
    MySQLAuditRepository(db).log(user.id, "COMPANY_CHART_CHOSEN", "company", company_id,
                                 old_value={"chart_id": company.chart_id},
                                 new_value={"chart_id": payload.chart_id, "chart": chart.code})
    return _to_out(updated)
