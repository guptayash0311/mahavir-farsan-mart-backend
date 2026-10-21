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

