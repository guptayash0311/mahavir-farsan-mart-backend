from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.deps import require_permission
from app.core.files import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, read_upload
from app.modules.documents.service import (
    add_version,
    create_document,
    document_out,
    file_bytes,
    list_documents,
    set_visibility,
    update_document,
)
from app.modules.identity.models import User

router = APIRouter()


class DocumentPatch(BaseModel):
    category: str | None = None
    title: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None


@router.get("/documents/public")
def public_documents(session: Session = Depends(get_session)) -> list[dict]:
    rows = list_documents(session, public_only=True)
    payload = []
    for row in rows:
        body = document_out(session, row)
        body["file_url"] = f"/api/v1/documents/public/{row.id}/file"
        payload.append(body)
    return payload


@router.get("/documents/public/{document_id}/file")
def public_file(document_id: UUID, session: Session = Depends(get_session)) -> Response:
    data, content_type, filename = file_bytes(session, document_id, public_only=True)
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/documents")
def documents(actor: User = Depends(require_permission("document.read")), session: Session = Depends(get_session)) -> list[dict]:
    return [document_out(session, row) for row in list_documents(session, public_only=False)]


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    category: str = Form(...),
    issue_date: str = Form(""),
    expiry_date: str = Form(""),
    file: UploadFile = File(...),
    actor: User = Depends(require_permission("document.upload")),
    session: Session = Depends(get_session),
) -> dict:
    data, content_type = await read_upload(file, DOCUMENT_TYPES, MAX_DOCUMENT_BYTES)
    document = create_document(
        session,
        actor,
        category,
        title,
        date.fromisoformat(issue_date) if issue_date else None,
        date.fromisoformat(expiry_date) if expiry_date else None,
        data,
        content_type,
        file.filename or "file",
    )
    return document_out(session, document)


@router.patch("/documents/{document_id}")
def patch_document(
    document_id: UUID,
    body: DocumentPatch,
    actor: User = Depends(require_permission("document.upload")),
    session: Session = Depends(get_session),
) -> dict:
    return document_out(session, update_document(session, actor, document_id, body.model_dump()))


@router.post("/documents/{document_id}/versions", status_code=status.HTTP_201_CREATED)
async def upload_version(
    document_id: UUID,
    file: UploadFile = File(...),
    actor: User = Depends(require_permission("document.upload")),
    session: Session = Depends(get_session),
) -> dict:
    data, content_type = await read_upload(file, DOCUMENT_TYPES, MAX_DOCUMENT_BYTES)
    return document_out(session, add_version(session, actor, document_id, data, content_type, file.filename or "file"))


@router.post("/documents/{document_id}/publish")
def publish_document(
    document_id: UUID,
    actor: User = Depends(require_permission("document.publish")),
    session: Session = Depends(get_session),
) -> dict:
    return document_out(session, set_visibility(session, actor, document_id, "public"))


@router.post("/documents/{document_id}/archive")
def archive_document(
    document_id: UUID,
    actor: User = Depends(require_permission("document.publish")),
    session: Session = Depends(get_session),
) -> dict:
    return document_out(session, set_visibility(session, actor, document_id, "archived"))


@router.get("/documents/{document_id}/file")
def admin_file(
    document_id: UUID,
    actor: User = Depends(require_permission("document.read")),
    session: Session = Depends(get_session),
) -> Response:
    data, content_type, filename = file_bytes(session, document_id, public_only=False)
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})
