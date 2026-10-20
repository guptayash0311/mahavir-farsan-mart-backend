from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.identity.access import user_has_permission
from app.modules.identity.models import User
from app.modules.identity.service import user_from_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_from_access_token(session, credentials.credentials)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User | None:
    if credentials is None:
        return None
    return user_from_access_token(session, credentials.credentials)


def require_permission(code: str):
    def checker(
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> User:
        if not user_has_permission(session, user, code):
            raise HTTPException(status_code=403, detail="Permission denied")
        return user

    return checker


def actor_id(user: User | None) -> UUID | None:
    return None if user is None else user.id
