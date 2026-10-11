"""Router d'authentification et de gestion des utilisateurs.

Deux niveaux d'administration :
- ADMIN : administrateur global de la plateforme, voit/gère tous les
  comptes de toutes les entreprises, peut créer des ENTREPRISE_ADMIN.
- ENTREPRISE_ADMIN : ne voit/gère que les comptes COMPTABLE de SA PROPRE
  entreprise (portée imposée par son company_id, jamais par le client).
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.application.use_cases import AuthenticateUserUseCase, UseCaseError
from app.core.dependencies import get_current_user, require_company_admin
from app.core import branding
from app.core.security import hash_password, verify_password
from app.domain.entities import Company, Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAuditRepository, MySQLCompanyRepository, MySQLUserRepository,
)
from app.presentation.schemas import (
    LoginRequest, PasswordChange, ProfileUpdate, TokenResponse, UserActiveUpdate,
    UserCreate, UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


def _to_out(user: User, company: Company | None = None) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                   role=user.role.value, company_id=user.company_id,
                   company_name=company.name if company else None,
                   is_active=user.is_active, theme=user.theme, accent=user.accent,
                   avatar_version=branding.image_version(user.avatar_path),
                   company_logo_version=(branding.image_version(company.logo_path)
                                         if company else None))


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
    return _to_out(user, company)


def _own_profile(user: User, db: Session) -> UserOut:
    refreshed = MySQLUserRepository(db).get_by_id(user.id)
    company = (MySQLCompanyRepository(db).get_by_id(user.company_id)
               if user.company_id else None)
    return _to_out(refreshed, company)


@router.patch("/me/profile", response_model=UserOut,
              summary="Modifier mon nom, mon thème et ma couleur")
def update_my_profile(payload: ProfileUpdate, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude_none=True)
    if fields:
        MySQLUserRepository(db).update_profile(user.id, **fields)
    return _own_profile(user, db)


@router.post("/me/password", status_code=204, summary="Changer mon mot de passe")
def change_my_password(payload: PasswordChange, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=422, detail="Mot de passe actuel incorrect")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit être différent")
    MySQLUserRepository(db).update_profile(user.id, password_hash=hash_password(payload.new_password))
    MySQLAuditRepository(db).log(user.id, "PASSWORD_CHANGED", "user", user.id)
    return Response(status_code=204)


@router.put("/me/avatar", response_model=UserOut, summary="Définir ma photo de profil")
async def upload_my_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    try:
        data = branding.process_avatar(await file.read())
    except branding.InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    name = branding.save_image(f"user_{user.id}.png", data)
    MySQLUserRepository(db).update_profile(user.id, avatar_path=name)
    return _own_profile(user, db)


@router.delete("/me/avatar", response_model=UserOut, summary="Supprimer ma photo de profil")
def delete_my_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    branding.delete_image(user.avatar_path)
    MySQLUserRepository(db).update_profile(user.id, avatar_path=None)
    return _own_profile(user, db)


@router.get("/me/avatar", summary="Ma photo de profil")
def get_my_avatar(user: User = Depends(get_current_user)):
    data = branding.read_image(user.avatar_path) if user.avatar_path else None
    if data is None:
        raise HTTPException(status_code=404, detail="Aucune photo de profil")
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400"})


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
    cache: dict[int, Company | None] = {}
    out = []
    for u in users:
        if u.company_id and u.company_id not in cache:
            cache[u.company_id] = companies.get_by_id(u.company_id)
        out.append(_to_out(u, cache.get(u.company_id) if u.company_id else None))
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
