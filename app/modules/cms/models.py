import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKey


class Page(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "pages"

    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)


class PageSection(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "page_sections"

    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    subtitle: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visible_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visible_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)


class Banner(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "banners"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    link_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Campaign(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (Index("uq_campaigns_slug_live", "slug", unique=True, postgresql_where=text("archived_at IS NULL")),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    theme_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    hero_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hero_content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignProduct(Base):
    __tablename__ = "campaign_products"

    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id"), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CampaignCategory(Base):
    __tablename__ = "campaign_categories"

    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), primary_key=True)
