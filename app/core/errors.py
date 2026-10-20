import logging

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.request_id import request_id_ctx

logger = logging.getLogger(__name__)

STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def error_body(code: str, message: str, details: object = None) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_ctx.get(),
        }
    }


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    details = None if isinstance(exc.detail, str) else jsonable_encoder(exc.detail)
    return JSONResponse(status_code=exc.status_code, content=error_body(code, message, details))


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            jsonable_encoder(exc.errors()),
        ),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Something went wrong.", None),
    )
