"""Trace utilities — trace ID generation and propagation helpers."""
from __future__ import annotations

import uuid
from typing import Any

from app.models.request_context import RequestContext


def new_trace_id() -> str:
    """Generate a short trace ID."""
    return f"t-{uuid.uuid4().hex[:12]}"


def new_request_id() -> str:
    """Generate a request ID."""
    return str(uuid.uuid4())


def extract_trace(config: dict[str, Any]) -> dict[str, str]:
    """Extract trace fields from request config."""
    return {
        "trace_id": config.get("__trace_id__", ""),
        "request_id": config.get("__request_id__", ""),
        "user_id": config.get("__user_id__", ""),
        "app_instance_id": config.get("__app_instance_id__", ""),
        "caller_id": config.get("__caller_id__", "unknown"),
    }


def format_trace_line(config: dict[str, Any]) -> str:
    """One-line trace string for log prefix."""
    t = extract_trace(config)
    return f"[{t['trace_id']} user={t['user_id']} app={t['app_instance_id']} caller={t['caller_id']}]"


def inject_trace(config: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    """Inject trace fields from RequestContext into config."""
    return ctx.inject_into_config(config)
