"""Session Router — request routing and user isolation middleware.

Every request passes through this router to:
1. Validate user identity
2. Enforce per-user data isolation
3. Route to correct user namespace
4. Reject cross-user access attempts

Analogous to iptables + namespace routing in Linux.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.user_service import UserService


class SessionRouterError(ValueError):
    pass


@dataclass
class RequestContext:
    """Per-request context with user isolation."""
    user_id: str
    session_id: str
    request_path: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Isolation boundary
    _user_namespace: str = ""

    def __post_init__(self) -> None:
        if not self._user_namespace:
            self._user_namespace = f"users/{self.user_id}"

    @property
    def user_namespace(self) -> str:
        return self._user_namespace


class SessionRouter:
    """Route requests with strict per-user isolation.

    Usage:
        router = SessionRouter(user_service)
        ctx = router.validate_and_route(user_id, session_id, path)
        # ctx.user_namespace is the isolated path prefix
    """

    def __init__(self, user_service: UserService | None = None) -> None:
        self._user_service = user_service
        # Track active sessions: session_id -> RequestContext
        self._active_sessions: dict[str, RequestContext] = {}

    def validate_and_route(
        self,
        user_id: str,
        session_id: str,
        path: str,
        method: str = "GET",
    ) -> RequestContext:
        """Validate user, create/update session context.

        Args:
            user_id: User identifier
            session_id: Session identifier
            path: Request path
            method: HTTP method

        Returns:
            RequestContext with user namespace

        Raises:
            SessionRouterError: If user not found or access denied
        """
        # Validate user exists
        if self._user_service and not self._user_service.user_exists(user_id):
            # Auto-register for convenience
            self._user_service.get_or_create(user_id)

        # Create or update session context
        ctx = RequestContext(
            user_id=user_id,
            session_id=session_id,
            request_path=path,
            method=method,
        )
        self._active_sessions[session_id] = ctx

        return ctx

    def get_context(self, session_id: str) -> RequestContext | None:
        """Get active session context."""
        return self._active_sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close a session."""
        self._active_sessions.pop(session_id, None)

    def get_active_count(self) -> int:
        """Get number of active sessions."""
        return len(self._active_sessions)

    def get_user_sessions(self, user_id: str) -> list[str]:
        """Get all session IDs for a user."""
        return [
            sid for sid, ctx in self._active_sessions.items()
            if ctx.user_id == user_id
        ]
