from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.money import money
from app.core.slug import unique_slug
from app.core.storage import get_storage
from app.modules.catalog.models import (
    Brand,
    Category,
    Manufacturer,
    Product,
    ProductAttribute,
    ProductCategory,
    ProductMedia,
)
from app.modules.identity.models import User


def _live(model, row_id: UUID, session: Session):
    row = session.get(model, row_id)
    if row is None or row.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return row


def create_named(session: Session, model, actor: User, name: str, parent_id: UUID | None = None):
    if parent_id is not None:
        _live(Category, parent_id, session)
    row = model(name=name.strip(), slug=unique_slug(session, model, name))
    if parent_id is not None:
        row.parent_id = parent_id
    session.add(row)
    session.flush()
    record_audit(session, actor.id, f"{model.__tablename__}.create", model.__tablename__, row.id, after={"name": row.name})
    session.commit()
    session.refresh(row)
    return row


def update_named(session: Session, model, actor: User, row_id: UUID, name: str | None, parent_id: UUID | None, parent_set: bool):
    row = _live(model, row_id, session)
    before = {"name": row.name}
    if name is not None:
        row.name = name.strip()
        row.slug = unique_slug(session, model, row.name, exclude_id=row.id)
    if parent_set and model is Category:
        if parent_id == row.id:
            raise HTTPException(status_code=400, detail="A category cannot be its own parent")
        if parent_id is not None:
            _live(Category, parent_id, session)
        row.parent_id = parent_id
    record_audit(session, actor.id, f"{model.__tablename__}.update", model.__tablename__, row.id, before=before, after={"name": row.name})
    session.commit()
    session.refresh(row)
    return row


def archive_named(session: Session, model, actor: User, row_id: UUID):
    row = _live(model, row_id, session)
    row.archived_at = utc_now()
    record_audit(session, actor.id, f"{model.__tablename__}.archive", model.__tablename__, row.id)
    session.commit()
    return row


def list_named(session: Session, model):
    return session.scalars(select(model).where(model.archived_at.is_(None)).order_by(model.name)).all()


def _sync_links(session: Session, product: Product, category_ids: list[UUID], attributes: list[tuple[str, str]]) -> None:
    for category_id in category_ids:
        _live(Category, category_id, session)
    session.execute(delete(ProductCategory).where(ProductCategory.product_id == product.id))
    session.execute(delete(ProductAttribute).where(ProductAttribute.product_id == product.id))
    session.flush()
    for category_id in category_ids:
        session.add(ProductCategory(product_id=product.id, category_id=category_id))
    for name, value in attributes:
        session.add(ProductAttribute(product_id=product.id, name=name.strip(), value=value.strip()))


def create_product(session: Session, actor: User, data: dict) -> Product:
    if data.get("brand_id"):
        _live(Brand, data["brand_id"], session)
    if data.get("manufacturer_id"):
        _live(Manufacturer, data["manufacturer_id"], session)
    product = Product(
        name=data["name"].strip(),
        slug=unique_slug(session, Product, data["name"]),
        sku=data["sku"].strip(),
        description=data.get("description") or "",
        manufacturer_id=data.get("manufacturer_id"),
        brand_id=data.get("brand_id"),
        status="draft",
        is_featured=data.get("is_featured", False),
        is_searchable=data.get("is_searchable", True),
        price=money(data["price"]),
        mrp=None if data.get("mrp") is None else money(data["mrp"]),
    )
    session.add(product)
    session.flush()
    _sync_links(session, product, data.get("category_ids") or [], [(item["name"], item["value"]) for item in data.get("attributes") or []])
    record_audit(session, actor.id, "product.create", "product", product.id, after={"name": product.name, "sku": product.sku})
    session.commit()
    session.refresh(product)
    return product


def update_product(session: Session, actor: User, product_id: UUID, data: dict, fields: set[str]) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    before = {"name": product.name, "status": product.status}
    if "name" in fields and data.get("name") is not None:
        product.name = data["name"].strip()
        product.slug = unique_slug(session, Product, product.name, exclude_id=product.id)
    if "sku" in fields and data.get("sku") is not None:
        product.sku = data["sku"].strip()
    if "description" in fields and data.get("description") is not None:
        product.description = data["description"]
    if "price" in fields and data.get("price") is not None:
        product.price = money(data["price"])
    if "mrp" in fields:
        product.mrp = None if data.get("mrp") is None else money(data["mrp"])
    if "is_featured" in fields and data.get("is_featured") is not None:
        product.is_featured = data["is_featured"]
    if "is_searchable" in fields and data.get("is_searchable") is not None:
        product.is_searchable = data["is_searchable"]
    if "brand_id" in fields:
        if data.get("brand_id"):
            _live(Brand, data["brand_id"], session)
        product.brand_id = data.get("brand_id")
    if "manufacturer_id" in fields:
        if data.get("manufacturer_id"):
            _live(Manufacturer, data["manufacturer_id"], session)
        product.manufacturer_id = data.get("manufacturer_id")
    if "category_ids" in fields or "attributes" in fields:
        category_ids = data.get("category_ids")
        if category_ids is None:
            category_ids = [
                row.category_id
                for row in session.scalars(select(ProductCategory).where(ProductCategory.product_id == product.id)).all()
            ]
        attributes = data.get("attributes")
        if attributes is None:
            attributes = [
                {"name": row.name, "value": row.value}
                for row in session.scalars(select(ProductAttribute).where(ProductAttribute.product_id == product.id)).all()
            ]
        _sync_links(session, product, category_ids, [(item["name"], item["value"]) for item in attributes])
    record_audit(session, actor.id, "product.update", "product", product.id, before=before, after={"name": product.name})
    session.commit()
    session.refresh(product)
    return product


def set_product_status(session: Session, actor: User, product_id: UUID, status: str) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    before = product.status
    product.status = status
    product.archived_at = utc_now() if status == "archived" else None
    record_audit(
        session,
        actor.id,
        "product.publish" if status == "published" else "product.archive",
        "product",
        product.id,
        before={"status": before},
        after={"status": status},
    )
    session.commit()
    session.refresh(product)
    return product


def visible_to(session: Session, product: Product | None, can_manage: bool) -> Product:
    if product is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if can_manage:
        return product
    if product.archived_at is not None or product.status != "published":
        raise HTTPException(status_code=404, detail="Resource not found")
    return product


def list_products(session: Session, *, manage: bool, q: str | None, category_id: UUID | None, brand_id: UUID | None, manufacturer_id: UUID | None, featured: bool | None):
    stmt = select(Product)
    if manage:
        stmt = stmt.where(Product.archived_at.is_(None))
    else:
        stmt = stmt.where(Product.status == "published", Product.archived_at.is_(None))
    if q:
        stmt = stmt.where(Product.is_searchable.is_(True), Product.name.ilike(f"%{q}%"))
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    if manufacturer_id:
        stmt = stmt.where(Product.manufacturer_id == manufacturer_id)
    if featured is not None:
        stmt = stmt.where(Product.is_featured.is_(featured))
    if category_id:
        stmt = stmt.join(ProductCategory, ProductCategory.product_id == Product.id).where(ProductCategory.category_id == category_id)
    return stmt.order_by(Product.name)


def add_media(session: Session, actor: User, product_id: UUID, data: bytes, content_type: str) -> ProductMedia:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    key = f"products/{product.id}/{uuid4()}"
    get_storage().put(key, data, content_type)
    current = session.scalars(select(ProductMedia.sort_order).where(ProductMedia.product_id == product.id)).all()
    media = ProductMedia(
        product_id=product.id,
        storage_key=key,
        content_type=content_type,
        sort_order=(max(current) + 1) if current else 0,
        created_at=utc_now(),
    )
    session.add(media)
    record_audit(session, actor.id, "product.media", "product", product.id, after={"content_type": content_type})
    session.commit()
    session.refresh(media)
    return media


def media_bytes(session: Session, media_id: UUID, can_manage: bool) -> tuple[bytes, str]:
    media = session.get(ProductMedia, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    product = session.get(Product, media.product_id)
    visible_to(session, product, can_manage)
    return get_storage().get(media.storage_key), media.content_type
