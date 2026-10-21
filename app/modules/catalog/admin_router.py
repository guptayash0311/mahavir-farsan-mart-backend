from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.deps import get_optional_user, require_permission
from app.core.files import IMAGE_TYPES, MAX_IMAGE_BYTES, read_upload
from app.core.pagination import Page, paginate_stmt, pagination_params
from app.modules.catalog.models import Brand, Category, Manufacturer, Product
from app.modules.catalog.present import brand_out, category_out, manufacturer_out, product_card, product_detail
from app.modules.catalog.service import (
    add_media,
    archive_named,
    create_named,
    create_product,
    list_named,
    list_products,
    media_bytes,
    set_product_status,
    update_named,
    update_product,
    visible_to,
)
from app.modules.identity.access import user_has_permission
from app.modules.identity.models import User

router = APIRouter()


class NamedIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None


class NamedPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: UUID | None = None


class AttributeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=500)


class ProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=80)
    description: str = ""
    price: str
    mrp: str | None = None
    manufacturer_id: UUID | None = None
    brand_id: UUID | None = None
    category_ids: list[UUID] = []
    attributes: list[AttributeIn] = []
    is_featured: bool = False
    is_searchable: bool = True


class ProductPatch(BaseModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    price: str | None = None
    mrp: str | None = None
    manufacturer_id: UUID | None = None
    brand_id: UUID | None = None
    category_ids: list[UUID] | None = None
    attributes: list[AttributeIn] | None = None
    is_featured: bool | None = None
    is_searchable: bool | None = None


def _decimals(data: dict) -> dict:
    from decimal import Decimal

    if data.get("price") is not None:
        data["price"] = Decimal(str(data["price"]))
    if "mrp" in data:
        data["mrp"] = None if data["mrp"] in (None, "") else Decimal(str(data["mrp"]))
    if data.get("attributes") is not None:
        data["attributes"] = [item.model_dump() if hasattr(item, "model_dump") else item for item in data["attributes"]]
    return data


def _manage(user: User | None, session: Session) -> bool:
    return user is not None and user_has_permission(session, user, "product.update")

@router.post("/categories", status_code=status.HTTP_201_CREATED)
def add_category(
    body: NamedIn,
    actor: User = Depends(require_permission("category.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return category_out(create_named(session, Category, actor, body.name, body.parent_id))

@router.patch("/categories/{category_id}")
def edit_category(
    category_id: UUID,
    body: NamedPatch,
    actor: User = Depends(require_permission("category.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return category_out(
        update_named(session, Category, actor, category_id, body.name, body.parent_id, "parent_id" in body.model_fields_set)
    )

@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(
    category_id: UUID,
    actor: User = Depends(require_permission("category.manage")),
    session: Session = Depends(get_session),
) -> Response:
    archive_named(session, Category, actor, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/brands", status_code=status.HTTP_201_CREATED)
def add_brand(
    body: NamedIn,
    actor: User = Depends(require_permission("brand.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return brand_out(create_named(session, Brand, actor, body.name))

@router.patch("/brands/{brand_id}")
def edit_brand(
    brand_id: UUID,
    body: NamedPatch,
    actor: User = Depends(require_permission("brand.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return brand_out(update_named(session, Brand, actor, brand_id, body.name, None, False))

@router.delete("/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_brand(
    brand_id: UUID,
    actor: User = Depends(require_permission("brand.manage")),
    session: Session = Depends(get_session),
) -> Response:
    archive_named(session, Brand, actor, brand_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/manufacturers", status_code=status.HTTP_201_CREATED)
def add_manufacturer(
    body: NamedIn,
    actor: User = Depends(require_permission("manufacturer.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return manufacturer_out(create_named(session, Manufacturer, actor, body.name))

@router.patch("/manufacturers/{manufacturer_id}")
def edit_manufacturer(
    manufacturer_id: UUID,
    body: NamedPatch,
    actor: User = Depends(require_permission("manufacturer.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return manufacturer_out(update_named(session, Manufacturer, actor, manufacturer_id, body.name, None, False))

@router.delete("/manufacturers/{manufacturer_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_manufacturer(
    manufacturer_id: UUID,
    actor: User = Depends(require_permission("manufacturer.manage")),
    session: Session = Depends(get_session),
) -> Response:
    archive_named(session, Manufacturer, actor, manufacturer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/products", status_code=status.HTTP_201_CREATED)
def add_product(
    body: ProductWrite,
    actor: User = Depends(require_permission("product.create")),
    session: Session = Depends(get_session),
) -> dict:
    product = create_product(session, actor, _decimals(body.model_dump()))
    return product_detail(session, product)

@router.patch("/products/{product_id}")
def edit_product(
    product_id: UUID,
    body: ProductPatch,
    actor: User = Depends(require_permission("product.update")),
    session: Session = Depends(get_session),
) -> dict:
    data = _decimals(body.model_dump())
    return product_detail(session, update_product(session, actor, product_id, data, body.model_fields_set))

@router.post("/products/{product_id}/publish")
def publish_product(
    product_id: UUID,
    actor: User = Depends(require_permission("product.publish")),
    session: Session = Depends(get_session),
) -> dict:
    return product_detail(session, set_product_status(session, actor, product_id, "published"))

@router.post("/products/{product_id}/archive")
def archive_product(
    product_id: UUID,
    actor: User = Depends(require_permission("product.archive")),
    session: Session = Depends(get_session),
) -> dict:
    return product_detail(session, set_product_status(session, actor, product_id, "archived"))

@router.post("/products/{product_id}/media", status_code=status.HTTP_201_CREATED)
async def upload_media(
    product_id: UUID,
    file: UploadFile = File(...),
    actor: User = Depends(require_permission("product.update")),
    session: Session = Depends(get_session),
) -> dict:
    data, content_type = await read_upload(file, IMAGE_TYPES, MAX_IMAGE_BYTES)
    media = add_media(session, actor, product_id, data, content_type)
    return {"id": media.id, "url": f"/api/v1/product-media/{media.id}", "sort_order": media.sort_order}

