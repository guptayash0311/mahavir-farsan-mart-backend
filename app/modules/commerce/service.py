import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.modules.catalog.models import Product
from app.modules.catalog.present import product_card
from app.modules.commerce.models import (
    Cart,
    CartItem,
    CustomerProfile,
    Inquiry,
    InquiryItem,
    Order,
    OrderItem,
    Wishlist,
    WishlistItem,
)
from app.modules.identity.access import user_has_permission
from app.modules.identity.models import User

GUEST_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,80}$")


def get_profile(session: Session, user: User) -> CustomerProfile:
    profile = session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
    if profile is None:
        profile = CustomerProfile(user_id=user.id, full_name="", phone="")
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def update_profile(session: Session, user: User, full_name: str | None, phone: str | None) -> CustomerProfile:
    profile = get_profile(session, user)
    if full_name is not None:
        profile.full_name = full_name.strip()
    if phone is not None:
        profile.phone = phone.strip()
    record_audit(session, user.id, "profile.update", "customer_profile", profile.id, after={"full_name": profile.full_name})
    session.commit()
    session.refresh(profile)
    return profile


def _published_product(session: Session, product_id: UUID) -> Product:
    product = session.get(Product, product_id)
    if product is None or product.archived_at is not None or product.status != "published":
        raise HTTPException(status_code=404, detail="Resource not found")
    return product


def _cart_for(session: Session, user: User | None, guest_token: str | None, create: bool) -> Cart | None:
    if user is not None:
        cart = session.scalar(select(Cart).where(Cart.user_id == user.id, Cart.status == "active"))
        if cart is None and create:
            cart = Cart(user_id=user.id, status="active")
            session.add(cart)
            session.flush()
        return cart
    if not guest_token or not GUEST_TOKEN.match(guest_token):
        if create:
            raise HTTPException(status_code=401, detail="Guest token or login required")
        return None
    cart = session.scalar(select(Cart).where(Cart.guest_token == guest_token, Cart.status == "active"))
    if cart is None and create:
        cart = Cart(guest_token=guest_token, status="active")
        session.add(cart)
        session.flush()
    return cart


def cart_payload(session: Session, cart: Cart | None) -> dict:
    if cart is None:
        return {"id": None, "items": []}
    items = []
    for item in session.scalars(select(CartItem).where(CartItem.cart_id == cart.id)).all():
        product = session.get(Product, item.product_id)
        if product is None:
            continue
        card = product_card(session, product)
        card["item_id"] = item.id
        card["quantity"] = item.quantity
        items.append(card)
    return {"id": cart.id, "items": items}


def add_cart_item(session: Session, user: User | None, guest_token: str | None, product_id: UUID, quantity: int) -> dict:
    product = _published_product(session, product_id)
    cart = _cart_for(session, user, guest_token, create=True)
    assert cart is not None
    item = session.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product.id))
    if item is None:
        item = CartItem(cart_id=cart.id, product_id=product.id, quantity=min(quantity, 99))
        session.add(item)
    else:
        item.quantity = min(item.quantity + quantity, 99)
    session.commit()
    return cart_payload(session, cart)


def update_cart_item(session: Session, user: User | None, guest_token: str | None, item_id: UUID, quantity: int) -> dict:
    cart = _cart_for(session, user, guest_token, create=False)
    item = session.get(CartItem, item_id)
    if cart is None or item is None or item.cart_id != cart.id:
        raise HTTPException(status_code=404, detail="Resource not found")
    if quantity <= 0:
        session.delete(item)
    else:
        item.quantity = min(quantity, 99)
    session.commit()
    return cart_payload(session, cart)


def delete_cart_item(session: Session, user: User | None, guest_token: str | None, item_id: UUID) -> dict:
    return update_cart_item(session, user, guest_token, item_id, 0)


def merge_guest_cart(session: Session, user_id: UUID, guest_token: str) -> None:
    if not GUEST_TOKEN.match(guest_token):
        return
    guest = session.scalar(select(Cart).where(Cart.guest_token == guest_token, Cart.status == "active"))
    if guest is None:
        return
    account = session.scalar(select(Cart).where(Cart.user_id == user_id, Cart.status == "active"))
    if account is None:
        guest.user_id = user_id
        guest.guest_token = None
        session.flush()
        return
    for item in session.scalars(select(CartItem).where(CartItem.cart_id == guest.id)).all():
        existing = session.scalar(select(CartItem).where(CartItem.cart_id == account.id, CartItem.product_id == item.product_id))
        if existing is None:
            item.cart_id = account.id
        else:
            existing.quantity = min(existing.quantity + item.quantity, 99)
            session.delete(item)
    guest.status = "merged"
    session.flush()


def _wishlist(session: Session, user: User, create: bool) -> Wishlist | None:
    wishlist = session.scalar(select(Wishlist).where(Wishlist.user_id == user.id))
    if wishlist is None and create:
        wishlist = Wishlist(user_id=user.id)
        session.add(wishlist)
        session.flush()
    return wishlist


def wishlist_payload(session: Session, user: User) -> dict:
    wishlist = _wishlist(session, user, create=False)
    items = []
    if wishlist is not None:
        for item in session.scalars(select(WishlistItem).where(WishlistItem.wishlist_id == wishlist.id)).all():
            product = session.get(Product, item.product_id)
            if product and product.status == "published" and product.archived_at is None:
                items.append(product_card(session, product))
    return {"items": items}


def add_wishlist_item(session: Session, user: User, product_id: UUID) -> dict:
    product = _published_product(session, product_id)
    wishlist = _wishlist(session, user, create=True)
    assert wishlist is not None
    exists = session.scalar(
        select(WishlistItem).where(WishlistItem.wishlist_id == wishlist.id, WishlistItem.product_id == product.id)
    )
    if exists is None:
        session.add(WishlistItem(wishlist_id=wishlist.id, product_id=product.id, created_at=utc_now()))
    session.commit()
    return wishlist_payload(session, user)


def remove_wishlist_item(session: Session, user: User, product_id: UUID) -> dict:
    wishlist = _wishlist(session, user, create=False)
    if wishlist is not None:
        item = session.scalar(
            select(WishlistItem).where(WishlistItem.wishlist_id == wishlist.id, WishlistItem.product_id == product_id)
        )
        if item is not None:
            session.delete(item)
            session.commit()
    return wishlist_payload(session, user)


def _sees_all(session: Session, user: User | None) -> bool:
    return user is not None and user_has_permission(session, user, "inquiry.manage")


def create_inquiry(session: Session, user: User | None, guest_token: str | None, data: dict) -> Inquiry:
    items = list(data.get("items") or [])
    if data.get("from_cart"):
        cart = _cart_for(session, user, guest_token, create=False)
        if cart is not None:
            items = [
                {"product_id": row.product_id, "quantity": row.quantity}
                for row in session.scalars(select(CartItem).where(CartItem.cart_id == cart.id)).all()
            ]
    inquiry = Inquiry(
        user_id=None if user is None else user.id,
        name=(data.get("name") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        email=(data.get("email") or (user.email if user else "")).strip(),
        message=(data.get("message") or "").strip(),
        status="new",
    )
    if not inquiry.name:
        raise HTTPException(status_code=400, detail="Name is required")
    session.add(inquiry)
    session.flush()
    for raw in items:
        product = _published_product(session, raw["product_id"])
        session.add(InquiryItem(inquiry_id=inquiry.id, product_id=product.id, quantity=max(1, min(int(raw["quantity"]), 99))))
    record_audit(session, None if user is None else user.id, "inquiry.create", "inquiry", inquiry.id)
    from app.core.notify import deliver

    if inquiry.email:
        deliver("log", inquiry.email, "Inquiry received", f"Inquiry {inquiry.id} is {inquiry.status}.")
    session.commit()
    session.refresh(inquiry)
    return inquiry


def inquiry_out(session: Session, inquiry: Inquiry) -> dict:
    rows = session.scalars(select(InquiryItem).where(InquiryItem.inquiry_id == inquiry.id)).all()
    items = []
    for row in rows:
        product = session.get(Product, row.product_id)
        items.append(
            {
                "product_id": row.product_id,
                "quantity": row.quantity,
                "name": None if product is None else product.name,
                "slug": None if product is None else product.slug,
            }
        )
    return {
        "id": inquiry.id,
        "name": inquiry.name,
        "phone": inquiry.phone,
        "email": inquiry.email,
        "message": inquiry.message,
        "status": inquiry.status,
        "created_at": inquiry.created_at,
        "items": items,
    }


def list_inquiries(session: Session, user: User) -> list[Inquiry]:
    stmt = select(Inquiry).order_by(Inquiry.created_at.desc())
    if not _sees_all(session, user):
        stmt = stmt.where(Inquiry.user_id == user.id)
    return list(session.scalars(stmt).all())


def get_inquiry(session: Session, user: User, inquiry_id: UUID) -> Inquiry:
    inquiry = session.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not _sees_all(session, user) and inquiry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    return inquiry


def update_inquiry_status(session: Session, actor: User, inquiry_id: UUID, status: str) -> Inquiry:
    if status not in {"new", "reviewing", "accepted", "declined", "converted"}:
        raise HTTPException(status_code=400, detail="Unknown inquiry status")
    inquiry = session.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    before = inquiry.status
    inquiry.status = status
    record_audit(session, actor.id, "inquiry.update", "inquiry", inquiry.id, before={"status": before}, after={"status": status})
    session.commit()
    session.refresh(inquiry)
    return inquiry


def convert_inquiry(session: Session, actor: User, inquiry_id: UUID) -> Order:
    inquiry = session.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    existing = session.scalar(select(Order).where(Order.inquiry_id == inquiry.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Inquiry already has an order")
    order = Order(user_id=inquiry.user_id, inquiry_id=inquiry.id, status="requested")
    session.add(order)
    session.flush()
    for item in session.scalars(select(InquiryItem).where(InquiryItem.inquiry_id == inquiry.id)).all():
        product = session.get(Product, item.product_id)
        price = 0 if product is None else product.price
        session.add(OrderItem(order_id=order.id, product_id=item.product_id, quantity=item.quantity, unit_price=price))
    inquiry.status = "converted"
    record_audit(session, actor.id, "inquiry.convert", "order", order.id, after={"inquiry_id": str(inquiry.id)})
    session.commit()
    session.refresh(order)
    return order


def order_out(session: Session, order: Order) -> dict:
    items = []
    for row in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all():
        product = session.get(Product, row.product_id)
        items.append(
            {
                "product_id": row.product_id,
                "name": None if product is None else product.name,
                "quantity": row.quantity,
                "unit_price": f"{row.unit_price:.2f}",
            }
        )
    return {
        "id": order.id,
        "inquiry_id": order.inquiry_id,
        "user_id": order.user_id,
        "status": order.status,
        "created_at": order.created_at,
        "items": items,
    }


def list_orders(session: Session, user: User) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc())
    if not _sees_all(session, user):
        stmt = stmt.where(Order.user_id == user.id)
    return list(session.scalars(stmt).all())


def get_order(session: Session, user: User, order_id: UUID) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not _sees_all(session, user) and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    return order
