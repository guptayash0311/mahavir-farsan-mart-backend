from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.notify import deliver
from app.core.security import decode_access_token, encode_access_token, hash_password, hash_token, new_token, verify_password
from app.modules.identity.access import assign_role, permission_codes, role_names, user_has_permission
from app.modules.identity.models import PasswordResetToken, RefreshToken, Role, User, UserRole
from app.modules.identity.schemas import TokenOut, UserOut


def _tokens(session: Session, user: User) -> TokenOut:
    access, expires_in = encode_access_token(user.id)
    raw_refresh = new_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=utc_now() + timedelta(days=get_settings().jwt_refresh_days),
        )
    )
    return TokenOut(access_token=access, refresh_token=raw_refresh, expires_in=expires_in)


def _email_taken(session: Session, email: str) -> bool:
    return session.scalar(select(User).where(User.email == email)) is not None


def register_customer(session: Session, email: str, password: str, full_name: str) -> TokenOut:
    from app.modules.commerce.models import CustomerProfile

    normalized = email.lower()
    if _email_taken(session, normalized):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=normalized, password_hash=hash_password(password), is_active=True)
    session.add(user)
    session.flush()
    assign_role(session, user.id, "customer")
    session.add(CustomerProfile(user_id=user.id, full_name=full_name.strip(), phone=""))
    record_audit(session, user.id, "user.register", "user", user.id, after={"email": normalized})
    tokens = _tokens(session, user)
    session.commit()
    return tokens


def login(session: Session, email: str, password: str, guest_token: str | None) -> TokenOut:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")
    if guest_token:
        from app.modules.commerce.service import merge_guest_cart

        merge_guest_cart(session, user.id, guest_token)
    tokens = _tokens(session, user)
    session.commit()
    return tokens


def refresh(session: Session, raw_token: str) -> TokenOut:
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    now = utc_now()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")
    row.revoked_at = now
    tokens = _tokens(session, user)
    session.commit()
    return tokens


def logout(session: Session, raw_token: str) -> None:
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = utc_now()
        session.commit()


def forgot_password(session: Session, email: str) -> str | None:
    user = session.scalar(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    raw = None
    if user is not None:
        raw = new_token()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        deliver("log", user.email, "Reset your Mahavir Farsan Mart password", f"reset_token={raw}")
        session.commit()
    if get_settings().app_env == "production":
        return None
    return raw


def reset_password(session: Session, raw_token: str, password: str) -> None:
    row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token)))
    now = utc_now()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=400, detail="Reset token is invalid")
    user = session.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Reset token is invalid")
    user.password_hash = hash_password(password)
    row.used_at = now
    for token in session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))):
        token.revoked_at = now
    record_audit(session, user.id, "user.password_reset", "user", user.id)
    session.commit()


def user_from_access_token(session: Session, token: str) -> User:
    try:
        user_id = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    user = session.get(User, user_id)
    if user is None or not user.is_active or user.archived_at is not None:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return user


def to_user_out(session: Session, user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, is_active=user.is_active, roles=role_names(session, user))


def list_users(session: Session, page: int, page_size: int) -> tuple[list[User], int]:
    total = session.scalar(select(func.count()).select_from(User)) or 0
    rows = session.scalars(select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def create_user(session: Session, actor: User, email: str, password: str, full_name: str, role: str) -> User:
    from app.modules.commerce.models import CustomerProfile

    if role not in {"customer", "admin", "super_admin"}:
        raise HTTPException(status_code=400, detail="Unknown role")
    if role == "super_admin" and not user_has_permission(session, actor, "role.manage"):
        raise HTTPException(status_code=403, detail="Permission denied")
    normalized = email.lower()
    if _email_taken(session, normalized):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=normalized, password_hash=hash_password(password), is_active=True)
    session.add(user)
    session.flush()
    assign_role(session, user.id, role)
    session.add(CustomerProfile(user_id=user.id, full_name=full_name.strip(), phone=""))
    record_audit(session, actor.id, "user.create", "user", user.id, after={"email": normalized, "role": role})
    session.commit()
    session.refresh(user)
    return user


def set_active(session: Session, actor: User, user_id: UUID, active: bool) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot change your own activation")
    names = set(role_names(session, user))
    if names & {"admin", "super_admin"} and not user_has_permission(session, actor, "user.manage"):
        raise HTTPException(status_code=403, detail="Permission denied")
    before = user.is_active
    user.is_active = active
    if not active:
        now = utc_now()
        for token in session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        ):
            token.revoked_at = now
    record_audit(
        session,
        actor.id,
        "user.activate" if active else "user.deactivate",
        "user",
        user.id,
        before={"is_active": before},
        after={"is_active": active},
    )
    session.commit()
    session.refresh(user)
    return user


def replace_roles(session: Session, actor: User, user_id: UUID, roles: list[str]) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    unknown = [name for name in roles if session.scalar(select(Role).where(Role.name == name)) is None]
    if unknown:
        raise HTTPException(status_code=400, detail="Unknown role")
    before = role_names(session, user)
    session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    session.flush()
    for name in roles:
        assign_role(session, user.id, name)
    record_audit(session, actor.id, "user.roles", "user", user.id, before={"roles": before}, after={"roles": roles})
    session.commit()
    session.refresh(user)
    return user


def bootstrap_admin(session: Session) -> None:
    settings = get_settings()
    email = settings.bootstrap_admin_email.strip().lower()
    password = settings.bootstrap_admin_password
    if not email or not password:
        return
    count = session.scalar(select(func.count()).select_from(User)) or 0
    if count:
        return
    from app.modules.commerce.models import CustomerProfile

    user = User(email=email, password_hash=hash_password(password), is_active=True)
    session.add(user)
    session.flush()
    assign_role(session, user.id, "super_admin")
    session.add(CustomerProfile(user_id=user.id, full_name="Super Admin", phone=""))
    record_audit(session, user.id, "user.bootstrap", "user", user.id, after={"email": email})
