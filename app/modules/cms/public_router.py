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

@router.get("/pages/home")
def home(session: Session = Depends(get_session)) -> dict:
    return page_payload(session, _published_page(session, "home"), public=True)

@router.get("/pages/{slug}")
def page(slug: str, session: Session = Depends(get_session)) -> dict:
    return page_payload(session, _published_page(session, slug), public=True)

@router.get("/banners/{banner_id}/file")
def banner_download(banner_id: UUID, session: Session = Depends(get_session)) -> Response:
    data, content_type = banner_file(session, banner_id)
    return Response(content=data, media_type=content_type)

@router.get("/campaigns/active")
def active_campaigns(session: Session = Depends(get_session)) -> list[dict]:
    now = utc_now()
    rows = []
    for campaign in session.scalars(select(Campaign).where(Campaign.archived_at.is_(None))).all():
        if campaign_is_active(campaign.status, campaign.start_at, campaign.end_at, now, campaign.archived_at):
            rows.append(campaign_public(session, campaign, preview=False))
    return rows

@router.get("/campaigns/{key}")
def campaign_detail(key: str, session: Session = Depends(get_session)) -> dict:
    campaign = _find_campaign(session, key)
    return campaign_public(session, campaign, preview=False)

@router.get("/campaigns/{campaign_id}/hero")
def hero(campaign_id: UUID, session: Session = Depends(get_session)) -> Response:
    data, content_type = campaign_hero(session, campaign_id, preview=False)
    return Response(content=data, media_type=content_type)


def _find_campaign(session: Session, key: str) -> Campaign:
    campaign = None
    try:
        campaign = session.get(Campaign, UUID(key))
    except ValueError:
        campaign = session.scalar(select(Campaign).where(Campaign.slug == key, Campaign.archived_at.is_(None)))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return campaign
