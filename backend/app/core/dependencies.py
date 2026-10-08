"""Injection de dépendances FastAPI : session BDD, utilisateur courant
(JWT) et contrôle RBAC. C'est ici — et uniquement ici — que la couche
présentation est câblée aux implémentations concrètes de l'infrastructure."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.domain.entities import Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import MySQLUserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Jeton invalide ou expiré",
                            headers={"WWW-Authenticate": "Bearer"})
    user = MySQLUserRepository(db).get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Utilisateur inconnu ou désactivé")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Réservé au rôle Administrateur")
    return user


def require_company_admin(user: User = Depends(get_current_user)) -> User:
    """Réservé à l'administrateur global OU à l'admin d'une entreprise —
    la portée exacte (toutes entreprises vs la sienne) est ensuite tranchée
    dans chaque endpoint via user.role/user.company_id."""
    if user.role not in (Role.ADMIN, Role.ENTREPRISE_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Réservé aux administrateurs")
    return user
