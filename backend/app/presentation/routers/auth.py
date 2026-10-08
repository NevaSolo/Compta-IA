"""Router d'authentification et de gestion des utilisateurs.

Deux niveaux d'administration :
- ADMIN : administrateur global de la plateforme, voit/gère tous les
  comptes de toutes les entreprises, peut créer des ENTREPRISE_ADMIN.
- ENTREPRISE_ADMIN : ne voit/gère que les comptes COMPTABLE de SA PROPRE
  entreprise (portée imposée par son company_id, jamais par le client).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases import AuthenticateUserUseCase, UseCaseError
from app.core.dependencies import get_current_user, require_company_admin
from app.core.security import hash_password
from app.domain.entities import Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAuditRepository, MySQLCompanyRepository, MySQLUserRepository,
)
from app.presentation.schemas import (
    LoginRequest, TokenResponse, UserActiveUpdate, UserCreate, UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


def _to_out(user: User, company_name: str | None = None) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                   role=user.role.value, company_id=user.company_id,
                   company_name=company_name, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse,
             summary="Connexion (JWT)")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        return AuthenticateUserUseCase(MySQLUserRepository(db)).execute(
            payload.email, payload.password)
    except UseCaseError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/me", response_model=UserOut, summary="Profil courant")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = (MySQLCompanyRepository(db).get_by_id(user.company_id)
              if user.company_id else None)
    return _to_out(user, company.name if company else None)


@router.post("/users", response_model=UserOut, status_code=201,
             summary="Créer un utilisateur (Admin ou Admin d'entreprise)")
def create_user(payload: UserCreate, caller: User = Depends(require_company_admin),
                db: Session = Depends(get_db)):
    role = Role(payload.role)

    if caller.role == Role.ENTREPRISE_ADMIN:
        # Portée strictement imposée : jamais de compte ADMIN/ENTREPRISE_ADMIN
        # créé par un admin d'entreprise, jamais pour une autre société que
        # la sienne — company_id du payload ignoré, pas seulement validé.
        if role != Role.COMPTABLE:
            raise HTTPException(
                status_code=403,
                detail="Un administrateur d'entreprise ne peut créer que des comptes Comptable")
        company_id = caller.company_id
    else:  # caller.role == Role.ADMIN
        if role == Role.ADMIN:
            company_id = None  # un admin plateforme n'appartient à aucune entreprise
        else:
            if payload.company_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="company_id requis pour créer un compte Entreprise Admin ou Comptable")
            if MySQLCompanyRepository(db).get_by_id(payload.company_id) is None:
                raise HTTPException(status_code=404, detail="Entreprise introuvable")
            company_id = payload.company_id

    repo = MySQLUserRepository(db)
    if repo.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    user = repo.create(User(id=None, email=payload.email, full_name=payload.full_name,
                            role=role, company_id=company_id,
                            password_hash=hash_password(payload.password)))
    MySQLAuditRepository(db).log(caller.id, "USER_CREATED", "user", user.id,
                                 new_value={"email": user.email, "role": user.role.value,
                                            "company_id": company_id})
    return _to_out(user)


@router.get("/users", response_model=list[UserOut],
            summary="Lister les utilisateurs (Admin : tous ; Admin d'entreprise : les siens)")
def list_users(caller: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    scope = None if caller.role == Role.ADMIN else caller.company_id
    users = MySQLUserRepository(db).list_all(scope)
    companies = MySQLCompanyRepository(db)
    company_names: dict[int, str] = {}
    out = []
    for u in users:
        name = None
        if u.company_id:
            if u.company_id not in company_names:
                company = companies.get_by_id(u.company_id)
                company_names[u.company_id] = company.name if company else ""
            name = company_names[u.company_id] or None
        out.append(_to_out(u, name))
    return out


@router.patch("/users/{user_id}/active", response_model=UserOut,
              summary="Activer/désactiver un utilisateur")
def set_user_active(user_id: int, payload: UserActiveUpdate,
                    caller: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    if user_id == caller.id and not payload.is_active:
        raise HTTPException(status_code=422, detail="Vous ne pouvez pas désactiver votre propre compte")
    repo = MySQLUserRepository(db)
    target = repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if caller.role == Role.ENTREPRISE_ADMIN and (
            target.company_id != caller.company_id or target.role != Role.COMPTABLE):
        # 404 plutôt que 403 : ne pas confirmer l'existence d'un compte
        # hors de la portée de l'appelant.
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user = repo.set_active(user_id, payload.is_active)
    MySQLAuditRepository(db).log(caller.id, "USER_ACTIVATED" if payload.is_active else "USER_DEACTIVATED",
                                 "user", user_id, new_value={"is_active": payload.is_active})
    return _to_out(user)
