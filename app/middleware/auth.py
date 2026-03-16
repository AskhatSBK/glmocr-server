"""
API key authentication middleware.

If no API keys are configured (API_KEYS is empty), auth is disabled —
convenient for local development.

Clients pass the key via:
  Authorization: Bearer <key>
  OR
  X-API-Key: <key>
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

# Paths that never require auth
_PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        keys = settings.api_keys_set

        # Auth disabled — let everything through
        if not settings.ENABLE_AUTH or not keys:
            return await call_next(request)

        # Public paths always pass
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = _extract_key(request)
        if not provided or provided not in keys:
            logger.warning(
                "Unauthorized request from %s to %s",
                request.client.host if request.client else "unknown",
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "detail": "Valid API key required. "
                              "Pass it as 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.",
                },
            )

        return await call_next(request)


def _extract_key(request: Request) -> str | None:
    # Authorization: Bearer <key>
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    # X-API-Key: <key>
    return request.headers.get("X-API-Key", "").strip() or None
