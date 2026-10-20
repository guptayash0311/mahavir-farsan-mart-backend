from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money_str
from app.modules.catalog.models import Brand, Category, Manufacturer, Product, ProductAttribute, ProductCategory, ProductMedia


def category_out(row: Category) -> dict:
    return {"id": row.id, "parent_id": row.parent_id, "name": row.name, "slug": row.slug}


def brand_out(row: Brand) -> dict:
    return {"id": row.id, "name": row.name, "slug": row.slug}


def manufacturer_out(row: Manufacturer) -> dict:
    return brand_out(row)


def first_image(session: Session, product_id: UUID) -> str | None:
    media = session.scalar(
        select(ProductMedia).where(ProductMedia.product_id == product_id).order_by(ProductMedia.sort_order, ProductMedia.created_at)
    )
    if media is None:
        return None
    return f"/api/v1/product-media/{media.id}"


def product_card(session: Session, product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "price": money_str(product.price),
        "mrp": None if product.mrp is None else money_str(product.mrp),
        "is_featured": product.is_featured,
        "image_url": first_image(session, product.id),
        "status": product.status,
    }


def product_detail(session: Session, product: Product) -> dict:
    categories = session.scalars(
        select(Category)
        .join(ProductCategory, ProductCategory.category_id == Category.id)
        .where(ProductCategory.product_id == product.id, Category.archived_at.is_(None))
    ).all()
    attributes = session.scalars(select(ProductAttribute).where(ProductAttribute.product_id == product.id)).all()
    media = session.scalars(
        select(ProductMedia).where(ProductMedia.product_id == product.id).order_by(ProductMedia.sort_order)
    ).all()
    brand = session.get(Brand, product.brand_id) if product.brand_id else None
    manufacturer = session.get(Manufacturer, product.manufacturer_id) if product.manufacturer_id else None
    body = product_card(session, product)
    body.update(
        {
            "sku": product.sku,
            "description": product.description,
            "is_searchable": product.is_searchable,
            "brand": None if brand is None or brand.archived_at else brand_out(brand),
            "manufacturer": None if manufacturer is None or manufacturer.archived_at else manufacturer_out(manufacturer),
            "categories": [category_out(row) for row in categories],
            "attributes": [{"id": row.id, "name": row.name, "value": row.value} for row in attributes],
            "media": [
                {
                    "id": row.id,
                    "sort_order": row.sort_order,
                    "content_type": row.content_type,
                    "url": f"/api/v1/product-media/{row.id}",
                }
                for row in media
            ],
        }
    )
    return body
