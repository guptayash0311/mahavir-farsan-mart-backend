from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.database import get_session
from app.core.deps import require_permission
from app.core.files import IMAGE_TYPES, MAX_IMAGE_BYTES, read_upload
from app.modules.cms.models import Campaign, Page
from app.modules.cms.schedule import campaign_is_active
from app.modules.cms.service import (
    banner_file,
    campaign_hero,
    campaign_public,
    create_campaign,
    create_page,
    page_payload,
    publish_campaign,
    save_banner,
    save_section,
    set_campaign_hero,
    update_campaign,
    update_page,
)
from app.modules.identity.models import User

router = APIRouter()


class PageIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: str | None = None


class PagePatch(BaseModel):
    title: str | None = None
    status: str | None = None


class SectionIn(BaseModel):
    page_id: UUID
    type: str
    title: str = ""
    subtitle: str = ""
    config: dict = {}
    sort_order: int = 0
    enabled: bool = True
    visible_from: datetime | None = None
    visible_until: datetime | None = None
    campaign_id: UUID | None = None


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    description: str = ""
    start_at: datetime
    end_at: datetime
    theme: dict = {}
    product_ids: list[UUID] = []
    category_ids: list[UUID] = []


class CampaignPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    theme: dict | None = None
    product_ids: list[UUID] | None = None
    category_ids: list[UUID] | None = None


class BannerIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    link_url: str = ""


def _published_page(session: Session, slug: str) -> Page:
    page = session.scalar(select(Page).where(Page.slug == slug, Page.status == "published"))
    if page is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return page

@router.get("/admin/pages")
def admin_pages(actor: User = Depends(require_permission("cms.manage")), session: Session = Depends(get_session)) -> list[dict]:
    return [page_payload(session, row, public=False) for row in session.scalars(select(Page).order_by(Page.title)).all()]

@router.post("/admin/pages", status_code=status.HTTP_201_CREATED)
def add_page(
    body: PageIn,
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return page_payload(session, create_page(session, actor, body.title, body.slug), public=False)

@router.patch("/admin/pages/{page_id}")
def edit_page(
    page_id: UUID,
    body: PagePatch,
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return page_payload(session, update_page(session, actor, page_id, body.title, body.status), public=False)

@router.post("/admin/pages/{page_id}/publish")
def publish_page(
    page_id: UUID,
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return page_payload(session, update_page(session, actor, page_id, None, "published"), public=False)

@router.post("/admin/page-sections", status_code=status.HTTP_201_CREATED)
def add_section(
    body: SectionIn,
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    section = save_section(session, actor, body.model_dump(), None)
    return {"id": section.id, "type": section.type, "sort_order": section.sort_order}

@router.patch("/admin/page-sections/{section_id}")
def edit_section(
    section_id: UUID,
    body: SectionIn,
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    section = save_section(session, actor, body.model_dump(), section_id)
    return {"id": section.id, "type": section.type, "sort_order": section.sort_order}

@router.post("/admin/banners", status_code=status.HTTP_201_CREATED)
async def add_banner(
    title: str = Form(...),
    link_url: str = Form(""),
    file: UploadFile | None = File(default=None),
    actor: User = Depends(require_permission("cms.manage")),
    session: Session = Depends(get_session),
) -> dict:
    data = content_type = None
    if file is not None:
        data, content_type = await read_upload(file, IMAGE_TYPES, MAX_IMAGE_BYTES)
    banner = save_banner(session, actor, title, link_url, data, content_type, None)
    return {"id": banner.id, "title": banner.title, "link_url": banner.link_url}

@router.get("/campaigns")
def campaigns(actor: User = Depends(require_permission("campaign.manage")), session: Session = Depends(get_session)) -> list[dict]:
    return [
        campaign_public(session, row, preview=True)
        for row in session.scalars(select(Campaign).where(Campaign.archived_at.is_(None)).order_by(Campaign.start_at.desc())).all()
    ]

@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def add_campaign(
    body: CampaignIn,
    actor: User = Depends(require_permission("campaign.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return campaign_public(session, create_campaign(session, actor, body.model_dump()), preview=True)

@router.patch("/campaigns/{campaign_id}")
def edit_campaign(
    campaign_id: UUID,
    body: CampaignPatch,
    actor: User = Depends(require_permission("campaign.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return campaign_public(
        session,
        update_campaign(session, actor, campaign_id, body.model_dump(), body.model_fields_set),
        preview=True,
    )

@router.post("/campaigns/{campaign_id}/publish")
def publish(
    campaign_id: UUID,
    actor: User = Depends(require_permission("campaign.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return campaign_public(session, publish_campaign(session, actor, campaign_id), preview=True)

@router.post("/campaigns/{campaign_id}/preview")
def preview(
    campaign_id: UUID,
    actor: User = Depends(require_permission("campaign.manage")),
    session: Session = Depends(get_session),
) -> dict:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return campaign_public(session, campaign, preview=True)

@router.post("/campaigns/{campaign_id}/hero", status_code=status.HTTP_201_CREATED)
async def upload_hero(
    campaign_id: UUID,
    file: UploadFile = File(...),
    actor: User = Depends(require_permission("campaign.manage")),
    session: Session = Depends(get_session),
) -> dict:
    data, content_type = await read_upload(file, IMAGE_TYPES, MAX_IMAGE_BYTES)
    return campaign_public(session, set_campaign_hero(session, actor, campaign_id, data, content_type), preview=True)


def _find_campaign(session: Session, key: str) -> Campaign:
    campaign = None
    try:
        campaign = session.get(Campaign, UUID(key))
    except ValueError:
        campaign = session.scalar(select(Campaign).where(Campaign.slug == key, Campaign.archived_at.is_(None)))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return campaign
