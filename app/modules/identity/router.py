from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.deps import get_current_user, require_permission
from app.core.pagination import Page, pagination_params
from app.modules.identity.access import permission_codes, role_names
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    ForgotIn,
    LoginIn,
    MeOut,
    MessageOut,
    RefreshIn,
    RegisterIn,
    ResetIn,
    RolesIn,
    TokenOut,
    UserCreate,
    UserOut,
)
from app.modules.identity.service import (
    create_user,
    forgot_password,
    list_users,
    login,
    logout,
    refresh,
    register_customer,
    replace_roles,
    reset_password,
    set_active,
    to_user_out,
)

router = APIRouter()


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, session: Session = Depends(get_session)) -> TokenOut:
    return register_customer(session, body.email, body.password, body.full_name)


@router.post("/auth/login", response_model=TokenOut)
def sign_in(body: LoginIn, session: Session = Depends(get_session)) -> TokenOut:
    return login(session, body.email, body.password, body.guest_token)


@router.post("/auth/refresh", response_model=TokenOut)
def refresh_session(body: RefreshIn, session: Session = Depends(get_session)) -> TokenOut:
    return refresh(session, body.refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(body: RefreshIn, session: Session = Depends(get_session)) -> Response:
    logout(session, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/forgot-password", response_model=MessageOut)
def forgot(body: ForgotIn, session: Session = Depends(get_session)) -> MessageOut:
    token = forgot_password(session, body.email)
    return MessageOut(message="If the account exists, a reset token has been issued.", reset_token=token)


@router.post("/auth/reset-password", response_model=MessageOut)
def reset(body: ResetIn, session: Session = Depends(get_session)) -> MessageOut:
    reset_password(session, body.token, body.password)
    return MessageOut(message="Password updated.")


@router.get("/auth/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        roles=role_names(session, user),
        permissions=permission_codes(session, user),
    )


@router.get("/users", response_model=Page[UserOut])
def users(
    params=Depends(pagination_params),
    actor: User = Depends(require_permission("user.read")),
    session: Session = Depends(get_session),
) -> Page[UserOut]:
    rows, total = list_users(session, params.page, params.page_size)
    return Page(
        items=[to_user_out(session, row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_user(
    body: UserCreate,
    actor: User = Depends(require_permission("user.manage")),
    session: Session = Depends(get_session),
) -> UserOut:
    user = create_user(session, actor, body.email, body.password, body.full_name, body.role)
    return to_user_out(session, user)


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate(
    user_id: UUID,
    actor: User = Depends(require_permission("user.deactivate")),
    session: Session = Depends(get_session),
) -> UserOut:
    return to_user_out(session, set_active(session, actor, user_id, False))


@router.post("/users/{user_id}/activate", response_model=UserOut)
def activate(
    user_id: UUID,
    actor: User = Depends(require_permission("user.manage")),
    session: Session = Depends(get_session),
) -> UserOut:
    return to_user_out(session, set_active(session, actor, user_id, True))


@router.put("/users/{user_id}/roles", response_model=UserOut)
def set_roles(
    user_id: UUID,
    body: RolesIn,
    actor: User = Depends(require_permission("role.manage")),
    session: Session = Depends(get_session),
) -> UserOut:
    return to_user_out(session, replace_roles(session, actor, user_id, body.roles))
