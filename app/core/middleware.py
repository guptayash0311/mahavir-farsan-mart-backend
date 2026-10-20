from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import error_body
from app.core.rate_limit import allow

LIMITED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
}


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path") in LIMITED_PATHS:
            client = scope.get("client")
            address = client[0] if client else "unknown"
            if not allow(f"{address}:{scope['path']}", get_settings().rate_limit_per_minute):
                response = JSONResponse(status_code=429, content=error_body("rate_limited", "Too many requests"))
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
