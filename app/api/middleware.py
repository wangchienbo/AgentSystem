"""ASGI middleware for security headers, request logging, and rate limiting."""

from __future__ import annotations

import os
import time
import logging
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, and duration."""

    def __init__(self, app, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self._exclude_paths = set(exclude_paths or ["/health", "/docs", "/openapi.json", "/redoc"])

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Skip logging for excluded paths
        if any(request.url.path.startswith(p) for p in self._exclude_paths):
            return await call_next(request)

        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter using token bucket algorithm.

    Per-IP rate limiting with configurable limits.
    NOT suitable for multi-process deployment — use Redis for that.
    """

    def __init__(
        self,
        app,
        *,
        requests_per_minute: int = 60,
        burst: int = 10,
        exclude_paths: list[str] | None = None,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self._rpm = requests_per_minute
        self._burst = burst
        self._exclude_paths = set(exclude_paths or ["/health"])
        self._exclude_prefixes = tuple(exclude_prefixes or ["/static/", "/docs", "/openapi.json"])
        # {ip: [(timestamp, ...), ...]}
        self._buckets: dict[str, list[float]] = defaultdict(list)
        # Cleanup interval: prune entries older than 2 minutes
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, respecting X-Forwarded-For behind proxy."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old_entries(self):
        """Remove entries older than 2 minutes."""
        cutoff = time.time() - 120
        for ip in list(self._buckets.keys()):
            self._buckets[ip] = [t for t in self._buckets[ip] if t > cutoff]
            if not self._buckets[ip]:
                del self._buckets[ip]
        self._last_cleanup = time.time()

    def _is_allowed(self, ip: str) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.time()

        # Periodic cleanup
        if now - self._last_cleanup > 60:
            self._cleanup_old_entries()

        # Get requests in the last minute
        window_start = now - 60
        recent = [t for t in self._buckets[ip] if t > window_start]

        if len(recent) >= self._rpm:
            # Rate limited
            oldest = min(recent) if recent else now
            retry_after = int(oldest + 60 - now) + 1
            self._buckets[ip] = recent  # Prune old entries
            return False, max(retry_after, 1)

        # Allow and record
        recent.append(now)
        self._buckets[ip] = recent
        return True, 0

    async def dispatch(self, request: Request, call_next):
        # Check exclusions
        path = request.url.path
        if path in self._exclude_paths:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in self._exclude_prefixes):
            return await call_next(request)

        ip = self._get_client_ip(request)
        allowed, retry_after = self._is_allowed(ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self._rpm)
        return response


def setup_middleware(app):
    """Add all security and operational middleware to the FastAPI app."""

    # CORS — allow configured origins (default: same-origin)
    allowed_origins = os.environ.get("AGENTSYSTEM_CORS_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],  # TODO: tighten in production
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Request logging
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths=["/health", "/docs", "/openapi.json", "/redoc"],
    )

    # Rate limiting
    rpm = int(os.environ.get("AGENTSYSTEM_RATE_LIMIT_RPM", "120"))
    app.add_middleware(
        RateLimiterMiddleware,
        requests_per_minute=rpm,
        exclude_paths=["/health"],
        exclude_prefixes=["/static/", "/docs", "/openapi.json"],
    )
