from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.deps import get_current_user, get_optional_user, require_permission
from app.modules.commerce.service import (
    add_cart_item,
    add_wishlist_item,
    cart_payload,
    convert_inquiry,
    create_inquiry,
    delete_cart_item,
    get_inquiry,
    get_order,
    get_profile,
    inquiry_out,
    list_inquiries,
    list_orders,
    order_out,
    remove_wishlist_item,
    update_cart_item,
    update_inquiry_status,
    update_profile,
    wishlist_payload,
    _cart_for,
)
from app.modules.identity.access import user_has_permission
from app.modules.identity.models import User

router = APIRouter()


class ProfilePatch(BaseModel):
    full_name: str | None = None
    phone: str | None = None


class CartItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemPatch(BaseModel):
    quantity: int = Field(ge=0, le=99)


class WishlistIn(BaseModel):
    product_id: UUID


class InquiryItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class InquiryIn(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    message: str = ""
    items: list[InquiryItemIn] = []
    from_cart: bool = False


class InquiryPatch(BaseModel):
    status: str


def _cart_user(user: User | None, session: Session) -> User | None:
    if user is None:
        return None
    if not user_has_permission(session, user, "cart.manage"):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Permission denied")
    return user

@router.get("/profile")
def read_profile(user: User = Depends(require_permission("profile.read")), session: Session = Depends(get_session)) -> dict:
    profile = get_profile(session, user)
    return {"full_name": profile.full_name, "phone": profile.phone, "email": user.email}

@router.patch("/profile")
def patch_profile(
    body: ProfilePatch,
    user: User = Depends(require_permission("profile.update")),
    session: Session = Depends(get_session),
) -> dict:
    profile = update_profile(session, user, body.full_name, body.phone)
    return {"full_name": profile.full_name, "phone": profile.phone, "email": user.email}

@router.get("/cart")
def read_cart(
    x_guest_token: str | None = Header(default=None),
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    actor = None if user is None else _cart_user(user, session)
    return cart_payload(session, _cart_for(session, actor, x_guest_token, create=False))

@router.post("/cart/items", status_code=status.HTTP_201_CREATED)
def post_cart_item(
    body: CartItemIn,
    x_guest_token: str | None = Header(default=None),
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    return add_cart_item(session, _cart_user(user, session), x_guest_token, body.product_id, body.quantity)

@router.patch("/cart/items/{item_id}")
def patch_cart_item(
    item_id: UUID,
    body: CartItemPatch,
    x_guest_token: str | None = Header(default=None),
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    return update_cart_item(session, _cart_user(user, session), x_guest_token, item_id, body.quantity)

@router.delete("/cart/items/{item_id}")
def remove_cart_item(
    item_id: UUID,
    x_guest_token: str | None = Header(default=None),
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    return delete_cart_item(session, _cart_user(user, session), x_guest_token, item_id)

@router.get("/wishlist")
def read_wishlist(user: User = Depends(require_permission("wishlist.manage")), session: Session = Depends(get_session)) -> dict:
    return wishlist_payload(session, user)

@router.post("/wishlist/items", status_code=status.HTTP_201_CREATED)
def post_wishlist(
    body: WishlistIn,
    user: User = Depends(require_permission("wishlist.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return add_wishlist_item(session, user, body.product_id)

@router.delete("/wishlist/items/{product_id}")
def delete_wishlist(
    product_id: UUID,
    user: User = Depends(require_permission("wishlist.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return remove_wishlist_item(session, user, product_id)

@router.get("/orders")
def orders(user: User = Depends(require_permission("order.read")), session: Session = Depends(get_session)) -> list[dict]:
    return [order_out(session, row) for row in list_orders(session, user)]

@router.get("/orders/{order_id}")
def order_detail(
    order_id: UUID,
    user: User = Depends(require_permission("order.read")),
    session: Session = Depends(get_session),
) -> dict:
    return order_out(session, get_order(session, user, order_id))

