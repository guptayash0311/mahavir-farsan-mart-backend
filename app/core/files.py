from fastapi import HTTPException, UploadFile

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_TYPES = IMAGE_TYPES | {"application/pdf"}
MAX_IMAGE_BYTES = 5_000_000
MAX_DOCUMENT_BYTES = 10_000_000


def _matches(data: bytes, content_type: str) -> bool:
    if content_type == "application/pdf":
        return data.startswith(b"%PDF")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8")
    if content_type == "image/webp":
        return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


async def read_upload(upload: UploadFile, allowed: set[str], max_bytes: int) -> tuple[bytes, str]:
    data = await upload.read()
    content_type = upload.content_type or ""
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail="File is too large")
    if content_type not in allowed or not _matches(data, content_type):
        raise HTTPException(status_code=400, detail="File type is not allowed")
    return data, content_type
