"""
Simple in-memory sliding-window rate limiter (per client IP).

For multi-process / multi-host deployments, swap the in-memory store
for a Redis-backed implementation (e.g. slowapi + redis).
"""

import logging
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # ip → deque of request timestamps within the window
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        ip = _get_client_ip(request)
        now = time.monotonic()
        window = settings.RATE_LIMIT_WINDOW
        limit = settings.RATE_LIMIT_REQUESTS

        with self._lock:
            bucket = self._buckets[ip]
            # Drop timestamps outside the sliding window
            while bucket and bucket[0] < now - window:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = int(window - (now - bucket[0])) + 1
                logger.warning("Rate limit exceeded for IP %s", ip)
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": f"Too many requests. Max {limit} per {window}s.",
                        "retry_after_seconds": retry_after,
                    },
                )

            bucket.append(now)

        return await call_next(request)


def _get_client_ip(request: Request) -> str:
    # Respect X-Forwarded-For when behind a proxy/load balancer
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
