from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.storage import get_storage
from app.modules.documents.models import Document, DocumentVersion
from app.modules.identity.models import User


def _latest(session: Session, document_id: UUID) -> DocumentVersion | None:
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )


def document_out(session: Session, document: Document) -> dict:
    latest = _latest(session, document.id)
    return {
        "id": document.id,
        "category": document.category,
        "title": document.title,
        "visibility": document.visibility,
        "issue_date": document.issue_date,
        "expiry_date": document.expiry_date,
        "version": None if latest is None else latest.version_number,
        "filename": None if latest is None else latest.filename,
        "file_url": None if latest is None else f"/api/v1/documents/{document.id}/file",
    }


def create_document(
    session: Session,
    actor: User,
    category: str,
    title: str,
    issue_date: date | None,
    expiry_date: date | None,
    data: bytes,
    content_type: str,
    filename: str,
) -> Document:
    document = Document(
        category=category.strip(),
        title=title.strip(),
        visibility="admin",
        issue_date=issue_date,
        expiry_date=expiry_date,
    )
    session.add(document)
    session.flush()
    _add_version(session, document, data, content_type, filename)
    record_audit(session, actor.id, "document.create", "document", document.id, after={"title": document.title})
    session.commit()
    session.refresh(document)
    return document


def _add_version(session: Session, document: Document, data: bytes, content_type: str, filename: str) -> DocumentVersion:
    current = _latest(session, document.id)
    number = 1 if current is None else current.version_number + 1
    key = f"documents/{document.id}/{number}-{uuid4()}"
    get_storage().put(key, data, content_type)
    version = DocumentVersion(
        document_id=document.id,
        storage_key=key,
        content_type=content_type,
        filename=filename or "file",
        version_number=number,
        created_at=utc_now(),
    )
    session.add(version)
    return version


def add_version(session: Session, actor: User, document_id: UUID, data: bytes, content_type: str, filename: str) -> Document:
    document = _editable(session, document_id)
    _add_version(session, document, data, content_type, filename)
    record_audit(session, actor.id, "document.version", "document", document.id)
    session.commit()
    session.refresh(document)
    return document


def update_document(session: Session, actor: User, document_id: UUID, data: dict) -> Document:
    document = _editable(session, document_id)
    for field in ("category", "title"):
        if data.get(field):
            setattr(document, field, data[field].strip())
    if "issue_date" in data:
        document.issue_date = data["issue_date"]
    if "expiry_date" in data:
        document.expiry_date = data["expiry_date"]
    record_audit(session, actor.id, "document.update", "document", document.id, after={"title": document.title})
    session.commit()
    session.refresh(document)
    return document


def set_visibility(session: Session, actor: User, document_id: UUID, visibility: str) -> Document:
    document = _editable(session, document_id)
    document.visibility = visibility
    action = "document.publish" if visibility == "public" else "document.archive"
    if visibility == "archived":
        document.archived_at = utc_now()
        document.visibility = "admin"
    record_audit(session, actor.id, action, "document", document.id, after={"visibility": document.visibility})
    session.commit()
    session.refresh(document)
    return document


def _editable(session: Session, document_id: UUID) -> Document:
    document = session.get(Document, document_id)
    if document is None or document.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return document


def list_documents(session: Session, public_only: bool) -> list[Document]:
    stmt = select(Document).where(Document.archived_at.is_(None)).order_by(Document.title)
    if public_only:
        stmt = stmt.where(Document.visibility == "public")
    return list(session.scalars(stmt).all())


def file_bytes(session: Session, document_id: UUID, public_only: bool) -> tuple[bytes, str, str]:
    document = session.get(Document, document_id)
    if document is None or document.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if public_only and document.visibility != "public":
        raise HTTPException(status_code=404, detail="Resource not found")
    version = _latest(session, document.id)
    if version is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return get_storage().get(version.storage_key), version.content_type, version.filename
