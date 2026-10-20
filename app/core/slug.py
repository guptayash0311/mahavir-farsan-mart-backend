import re

from sqlalchemy import select
from sqlalchemy.orm import Session


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] or "item"


def unique_slug(session: Session, model, source: str, exclude_id=None) -> str:
    base = slugify(source)
    candidate = base
    number = 2
    while True:
        stmt = select(model).where(model.slug == candidate)
        if hasattr(model, "archived_at"):
            stmt = stmt.where(model.archived_at.is_(None))
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        if session.scalars(stmt).first() is None:
            return candidate
        candidate = f"{base}-{number}"[:80]
        number += 1
