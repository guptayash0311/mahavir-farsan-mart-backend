from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole


def role_names(session: Session, user: User) -> list[str]:
    rows = session.scalars(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    ).all()
    return sorted(rows)


def permission_codes(session: Session, user: User) -> list[str]:
    names = set(role_names(session, user))
    if "super_admin" in names:
        return list(PERMISSIONS)
    codes = session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
    ).all()
    return sorted(set(codes))


def user_has_permission(session: Session, user: User, code: str) -> bool:
    return code in permission_codes(session, user)


def ensure_identity_seed(session: Session) -> None:
    roles: dict[str, Role] = {}
    for name in ROLE_PERMISSIONS:
        role = session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name)
            session.add(role)
            session.flush()
        roles[name] = role
    permissions: dict[str, Permission] = {}
    for code in PERMISSIONS:
        permission = session.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code)
            session.add(permission)
            session.flush()
        permissions[code] = permission
    for role_name, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            link = session.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == roles[role_name].id,
                    RolePermission.permission_id == permissions[code].id,
                )
            )
            if link is None:
                session.add(RolePermission(role_id=roles[role_name].id, permission_id=permissions[code].id))
    session.flush()


def assign_role(session: Session, user_id: UUID, role_name: str) -> None:
    role = session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise ValueError(f"Unknown role {role_name}")
    exists = session.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    if exists is None:
        session.add(UserRole(user_id=user_id, role_id=role.id))
