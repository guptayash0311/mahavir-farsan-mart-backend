from contextvars import ContextVar
from uuid import uuid4

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_id = headers.get("x-request-id") or str(uuid4())
        token = request_id_ctx.set(request_id)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_ctx.reset(token)
