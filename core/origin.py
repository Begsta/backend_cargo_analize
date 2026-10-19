"""Проверка Origin изменяющих запросов с cookie из браузера."""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from core.config import settings


class OriginGuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            own_origin = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            if origin and origin != own_origin and origin not in settings.CORS_ORIGINS:
                response = JSONResponse(
                    status_code=403, content={"detail": "Недопустимый Origin"}
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
