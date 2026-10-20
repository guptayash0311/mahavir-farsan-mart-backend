import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.core.clock import utc_now
from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def encode_access_token(user_id: UUID) -> tuple[str, int]:
    settings = get_settings()
    minutes = settings.jwt_access_minutes
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "exp": utc_now() + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, minutes * 60


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except InvalidTokenError as exc:
        raise ValueError("Invalid access token") from exc
    if payload.get("typ") != "access" or not payload.get("sub"):
        raise ValueError("Invalid access token")
    try:
        return UUID(payload["sub"])
    except ValueError as exc:
        raise ValueError("Invalid access token") from exc
