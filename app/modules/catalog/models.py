import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import ArchiveMixin, TimestampMixin, UUIDPrimaryKey


class Category(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (Index("uq_categories_slug_live", "slug", unique=True, postgresql_where=text("archived_at IS NULL")),)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)


class Brand(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (Index("uq_brands_slug_live", "slug", unique=True, postgresql_where=text("archived_at IS NULL")),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)


class Manufacturer(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "manufacturers"
    __table_args__ = (Index("uq_manufacturers_slug_live", "slug", unique=True, postgresql_where=text("archived_at IS NULL")),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)


class Product(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("uq_products_slug_live", "slug", unique=True, postgresql_where=text("archived_at IS NULL")),
        Index("uq_products_sku_live", "sku", unique=True, postgresql_where=text("archived_at IS NULL")),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manufacturers.id"), nullable=True, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("product_id", "category_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), primary_key=True)


class ProductAttribute(UUIDPrimaryKey, Base):
    __tablename__ = "product_attributes"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class ProductMedia(UUIDPrimaryKey, Base):
    __tablename__ = "product_media"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
