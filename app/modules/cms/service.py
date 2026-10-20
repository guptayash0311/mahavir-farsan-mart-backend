from datetime import datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.slug import unique_slug
from app.core.storage import get_storage
from app.modules.catalog.models import Category, Product
from app.modules.catalog.present import category_out, product_card
from app.modules.cms.models import Banner, Campaign, CampaignCategory, CampaignProduct, Page, PageSection
from app.modules.cms.schedule import campaign_is_active, section_is_visible
from app.modules.identity.models import User

SECTION_TYPES = {
    "hero",
    "banner",
    "product_grid",
    "category_grid",
    "rich_text",
    "image_text",
    "announcement",
    "campaign_highlight",
    "contact_cta",
}


def _uuids(values) -> list[UUID]:
    parsed: list[UUID] = []
    for value in values or []:
        try:
            parsed.append(UUID(str(value)))
        except ValueError:
            continue
    return parsed


def campaign_public(session: Session, campaign: Campaign, preview: bool) -> dict:
    now = utc_now()
    active = campaign_is_active(campaign.status, campaign.start_at, campaign.end_at, now, campaign.archived_at)
    if not preview and not active:
        raise HTTPException(status_code=404, detail="Resource not found")
    product_ids = session.scalars(
        select(CampaignProduct.product_id).where(CampaignProduct.campaign_id == campaign.id).order_by(CampaignProduct.sort_order)
    ).all()
    products = []
    for product_id in product_ids:
        product = session.get(Product, product_id)
        if product and product.status == "published" and product.archived_at is None:
            products.append(product_card(session, product))
    category_ids = session.scalars(select(CampaignCategory.category_id).where(CampaignCategory.campaign_id == campaign.id)).all()
    categories = []
    for category_id in category_ids:
        category = session.get(Category, category_id)
        if category and category.archived_at is None:
            categories.append(category_out(category))
    return {
        "id": campaign.id,
        "name": campaign.name,
        "slug": campaign.slug,
        "description": campaign.description,
        "start_at": campaign.start_at,
        "end_at": campaign.end_at,
        "status": campaign.status,
        "theme": campaign.theme_json or {},
        "hero_url": None if campaign.hero_storage_key is None else f"/api/v1/campaigns/{campaign.id}/hero",
        "active": active,
        "preview": preview,
        "products": products,
        "categories": categories,
    }


def _section_payload(session: Session, section: PageSection, now: datetime) -> dict:
    config = section.config_json or {}
    products = []
    categories = []
    banners = []
    if section.type == "product_grid":
        wanted = _uuids(config.get("product_ids"))
        if wanted:
            rows = [session.get(Product, product_id) for product_id in wanted]
        elif config.get("category_id"):
            from app.modules.catalog.models import ProductCategory

            try:
                category_id = UUID(str(config["category_id"]))
            except ValueError:
                category_id = None
            rows = []
            if category_id:
                rows = session.scalars(
                    select(Product)
                    .join(ProductCategory, ProductCategory.product_id == Product.id)
                    .where(
                        ProductCategory.category_id == category_id,
                        Product.status == "published",
                        Product.archived_at.is_(None),
                    )
                ).all()
        else:
            rows = session.scalars(
                select(Product).where(Product.is_featured.is_(True), Product.status == "published", Product.archived_at.is_(None))
            ).all()
        products = [product_card(session, row) for row in rows if row and row.status == "published" and row.archived_at is None]
    if section.type == "category_grid":
        wanted = _uuids(config.get("category_ids"))
        if wanted:
            rows = [session.get(Category, category_id) for category_id in wanted]
        else:
            rows = session.scalars(select(Category).where(Category.archived_at.is_(None), Category.parent_id.is_(None))).all()
        categories = [category_out(row) for row in rows if row and row.archived_at is None]
    if section.type == "banner":
        rows = session.scalars(select(Banner).where(Banner.enabled.is_(True)).order_by(Banner.sort_order)).all()
        banners = [
            {
                "id": row.id,
                "title": row.title,
                "link_url": row.link_url,
                "image_url": None if row.storage_key is None else f"/api/v1/banners/{row.id}/file",
            }
            for row in rows
        ]
    return {
        "id": section.id,
        "type": section.type,
        "title": section.title,
        "subtitle": section.subtitle,
        "config": config,
        "sort_order": section.sort_order,
        "products": products,
        "categories": categories,
        "banners": banners,
        "campaign_id": section.campaign_id,
    }


def page_payload(session: Session, page: Page, public: bool) -> dict:
    now = utc_now()
    sections = session.scalars(select(PageSection).where(PageSection.page_id == page.id).order_by(PageSection.sort_order)).all()
    visible = []
    for section in sections:
        if public and not section_is_visible(section.enabled, section.visible_from, section.visible_until, now):
            continue
        visible.append(_section_payload(session, section, now))
    active = None
    for campaign in session.scalars(select(Campaign).where(Campaign.archived_at.is_(None))).all():
        if campaign_is_active(campaign.status, campaign.start_at, campaign.end_at, now, campaign.archived_at):
            active = {"id": campaign.id, "name": campaign.name, "slug": campaign.slug, "description": campaign.description}
            break
    return {
        "id": page.id,
        "slug": page.slug,
        "title": page.title,
        "status": page.status,
        "sections": visible,
        "active_campaign": active,
    }


def create_page(session: Session, actor: User, title: str, slug: str | None) -> Page:
    page = Page(title=title.strip(), slug=unique_slug(session, Page, slug or title), status="draft")
    session.add(page)
    record_audit(session, actor.id, "page.create", "page", page.id, after={"title": page.title})
    session.commit()
    session.refresh(page)
    return page


def update_page(session: Session, actor: User, page_id: UUID, title: str | None, status: str | None) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if title is not None:
        page.title = title.strip()
    if status is not None:
        if status not in {"draft", "published"}:
            raise HTTPException(status_code=400, detail="Unknown page status")
        page.status = status
    record_audit(session, actor.id, "page.update", "page", page.id, after={"status": page.status, "title": page.title})
    session.commit()
    session.refresh(page)
    return page


def save_section(session: Session, actor: User, data: dict, section_id: UUID | None) -> PageSection:
    if data["type"] not in SECTION_TYPES:
        raise HTTPException(status_code=400, detail="Unknown section type")
    page = session.get(Page, data["page_id"])
    if page is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if section_id is None:
        section = PageSection(page_id=page.id, type=data["type"])
        session.add(section)
    else:
        section = session.get(PageSection, section_id)
        if section is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        section.type = data["type"]
    section.title = data.get("title") or ""
    section.subtitle = data.get("subtitle") or ""
    section.config_json = data.get("config") or {}
    section.sort_order = data.get("sort_order") or 0
    section.enabled = True if data.get("enabled") is None else data["enabled"]
    section.visible_from = data.get("visible_from")
    section.visible_until = data.get("visible_until")
    section.campaign_id = data.get("campaign_id")
    record_audit(session, actor.id, "page_section.save", "page_section", section.id, after={"type": section.type})
    session.commit()
    session.refresh(section)
    return section


def create_campaign(session: Session, actor: User, data: dict) -> Campaign:
    campaign = Campaign(
        name=data["name"].strip(),
        slug=unique_slug(session, Campaign, data.get("slug") or data["name"]),
        description=data.get("description") or "",
        start_at=data["start_at"],
        end_at=data["end_at"],
        status="draft",
        theme_json=data.get("theme") or {},
    )
    if campaign.end_at < campaign.start_at:
        raise HTTPException(status_code=400, detail="Campaign end is before the start")
    session.add(campaign)
    session.flush()
    _set_collection(session, campaign, data.get("product_ids") or [], data.get("category_ids") or [])
    record_audit(session, actor.id, "campaign.create", "campaign", campaign.id, after={"name": campaign.name})
    session.commit()
    session.refresh(campaign)
    return campaign


def update_campaign(session: Session, actor: User, campaign_id: UUID, data: dict, fields: set[str]) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if "name" in fields and data.get("name"):
        campaign.name = data["name"].strip()
        campaign.slug = unique_slug(session, Campaign, campaign.name, exclude_id=campaign.id)
    if "description" in fields:
        campaign.description = data.get("description") or ""
    if "start_at" in fields and data.get("start_at"):
        campaign.start_at = data["start_at"]
    if "end_at" in fields and data.get("end_at"):
        campaign.end_at = data["end_at"]
    if campaign.end_at < campaign.start_at:
        raise HTTPException(status_code=400, detail="Campaign end is before the start")
    if "theme" in fields and data.get("theme") is not None:
        campaign.theme_json = data["theme"]
    if "product_ids" in fields or "category_ids" in fields:
        product_ids = data["product_ids"] if "product_ids" in fields else None
        category_ids = data["category_ids"] if "category_ids" in fields else None
        if product_ids is None:
            product_ids = session.scalars(select(CampaignProduct.product_id).where(CampaignProduct.campaign_id == campaign.id)).all()
        if category_ids is None:
            category_ids = session.scalars(
                select(CampaignCategory.category_id).where(CampaignCategory.campaign_id == campaign.id)
            ).all()
        _set_collection(session, campaign, list(product_ids), list(category_ids))
    record_audit(session, actor.id, "campaign.update", "campaign", campaign.id, after={"name": campaign.name})
    session.commit()
    session.refresh(campaign)
    return campaign


def _set_collection(session: Session, campaign: Campaign, product_ids: list[UUID], category_ids: list[UUID]) -> None:
    from sqlalchemy import delete

    session.execute(delete(CampaignProduct).where(CampaignProduct.campaign_id == campaign.id))
    session.execute(delete(CampaignCategory).where(CampaignCategory.campaign_id == campaign.id))
    for index, product_id in enumerate(product_ids):
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        session.add(CampaignProduct(campaign_id=campaign.id, product_id=product_id, sort_order=index))
    for category_id in category_ids:
        if session.get(Category, category_id) is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        session.add(CampaignCategory(campaign_id=campaign.id, category_id=category_id))


def publish_campaign(session: Session, actor: User, campaign_id: UUID) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    campaign.status = "published"
    record_audit(session, actor.id, "campaign.publish", "campaign", campaign.id, after={"status": "published"})
    session.commit()
    session.refresh(campaign)
    return campaign


def save_banner(session: Session, actor: User, title: str, link_url: str, data: bytes | None, content_type: str | None, banner_id: UUID | None) -> Banner:
    if banner_id is None:
        banner = Banner(title=title.strip(), link_url=link_url, sort_order=0, enabled=True)
        session.add(banner)
        session.flush()
    else:
        banner = session.get(Banner, banner_id)
        if banner is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        banner.title = title.strip()
        banner.link_url = link_url
    if data is not None and content_type is not None:
        key = f"banners/{banner.id}/{uuid4()}"
        get_storage().put(key, data, content_type)
        banner.storage_key = key
        banner.content_type = content_type
    record_audit(session, actor.id, "banner.save", "banner", banner.id, after={"title": banner.title})
    session.commit()
    session.refresh(banner)
    return banner


def banner_file(session: Session, banner_id: UUID) -> tuple[bytes, str]:
    banner = session.get(Banner, banner_id)
    if banner is None or not banner.enabled or not banner.storage_key:
        raise HTTPException(status_code=404, detail="Resource not found")
    return get_storage().get(banner.storage_key), banner.content_type or "application/octet-stream"


def campaign_hero(session: Session, campaign_id: UUID, preview: bool) -> tuple[bytes, str]:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or not campaign.hero_storage_key:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not preview and not campaign_is_active(campaign.status, campaign.start_at, campaign.end_at, utc_now(), campaign.archived_at):
        raise HTTPException(status_code=404, detail="Resource not found")
    return get_storage().get(campaign.hero_storage_key), campaign.hero_content_type or "application/octet-stream"


def set_campaign_hero(session: Session, actor: User, campaign_id: UUID, data: bytes, content_type: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    key = f"campaigns/{campaign.id}/{uuid4()}"
    get_storage().put(key, data, content_type)
    campaign.hero_storage_key = key
    campaign.hero_content_type = content_type
    record_audit(session, actor.id, "campaign.hero", "campaign", campaign.id)
    session.commit()
    session.refresh(campaign)
    return campaign
