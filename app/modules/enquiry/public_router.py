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

@router.post("/inquiries", status_code=status.HTTP_201_CREATED)
def post_inquiry(
    body: InquiryIn,
    x_guest_token: str | None = Header(default=None),
    user: User | None = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> dict:
    data = body.model_dump()
    inquiry = create_inquiry(session, user, x_guest_token, data)
    return inquiry_out(session, inquiry)

@router.get("/inquiries")
def inquiries(user: User = Depends(require_permission("inquiry.read")), session: Session = Depends(get_session)) -> list[dict]:
    return [inquiry_out(session, row) for row in list_inquiries(session, user)]

@router.get("/inquiries/{inquiry_id}")
def inquiry_detail(
    inquiry_id: UUID,
    user: User = Depends(require_permission("inquiry.read")),
    session: Session = Depends(get_session),
) -> dict:
    return inquiry_out(session, get_inquiry(session, user, inquiry_id))
