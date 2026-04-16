"""Auth Service — authentication and session token management.

Provides:
1. Token generation and validation
2. Session lifecycle (create, validate, expire)
3. Permission checks (user can only access own resources)
4. Token refresh

Analogous to PAM + session management in Linux.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.user_service import UserService, UserServiceError


class AuthError(ValueError):
    pass


@dataclass
class SessionToken:
    """Represents an authenticated session."""
    token: str
    user_id: str
    created_at: float
    expires_at: float
    last_active: float
    ip_address: str = ""
    user_agent: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def touch(self) -> None:
        """Update last active time."""
        self.last_active = time.time()


class AuthService:
    """Authentication and session management.

    Usage:
        auth = AuthService(user_service)
        token = auth.create_session("alice")
        session = auth.validate_token(token)  # raises AuthError if invalid
    """

    def __init__(
        self,
        user_service: UserService | None = None,
        token_ttl: int = 86400,  # 24 hours
        max_sessions_per_user: int = 5,
    ) -> None:
        self._user_service = user_service
        self._token_ttl = token_ttl
        self._max_sessions = max_sessions_per_user
        # In-memory session store: token -> SessionToken
        self._sessions: dict[str, SessionToken] = {}
        # User -> active tokens
        self._user_sessions: dict[str, list[str]] = {}

    def create_session(
        self,
        user_id: str,
        ip_address: str = "",
        user_agent: str = "",
    ) -> str:
        """Create a new authenticated session.

        Args:
            user_id: User identifier
            ip_address: Client IP
            user_agent: Browser user agent

        Returns:
            Session token string

        Raises:
            AuthError: If user not found or max sessions exceeded
        """
        # Validate user exists
        if self._user_service:
            try:
                self._user_service.require_user(user_id)
            except UserServiceError as e:
                raise AuthError(str(e))

        # Enforce max sessions per user
        user_tokens = self._user_sessions.get(user_id, [])
        # Clean expired
        user_tokens = [
            t for t in user_tokens
            if t in self._sessions and not self._sessions[t].is_expired
        ]
        if len(user_tokens) >= self._max_sessions:
            # Expire oldest
            oldest = user_tokens[0]
            del self._sessions[oldest]
            user_tokens = user_tokens[1:]

        # Generate token
        token = self._generate_token(user_id)
        now = time.time()

        session = SessionToken(
            token=token,
            user_id=user_id,
            created_at=now,
            expires_at=now + self._token_ttl,
            last_active=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self._sessions[token] = session
        user_tokens.append(token)
        self._user_sessions[user_id] = user_tokens

        return token

    def validate_token(self, token: str) -> SessionToken:
        """Validate a session token.

        Returns:
            SessionToken if valid

        Raises:
            AuthError: If token is invalid or expired
        """
        if not token:
            raise AuthError("Missing authentication token")

        session = self._sessions.get(token)
        if not session:
            raise AuthError("Invalid session token")

        if session.is_expired:
            del self._sessions[token]
            raise AuthError("Session expired")

        # Update last active
        session.touch()
        return session

    def revoke_token(self, token: str) -> bool:
        """Revoke a session token."""
        session = self._sessions.pop(token, None)
        if session:
            user_tokens = self._user_sessions.get(session.user_id, [])
            if token in user_tokens:
                user_tokens.remove(token)
        return session is not None

    def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user."""
        user_tokens = self._user_sessions.pop(user_id, [])
        count = 0
        for token in user_tokens:
            if self._sessions.pop(token, None):
                count += 1
        return count

    def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get active sessions for a user."""
        user_tokens = self._user_sessions.get(user_id, [])
        sessions = []
        for token in user_tokens:
            session = self._sessions.get(token)
            if session and not session.is_expired:
                sessions.append({
                    "token_preview": token[:12] + "...",
                    "created_at": session.created_at,
                    "last_active": session.last_active,
                    "ip_address": session.ip_address,
                    "user_agent": session.user_agent,
                })
        return sessions

    def refresh_token(self, token: str) -> str:
        """Refresh a session token, extending its TTL."""
        session = self.validate_token(token)
        session.expires_at = time.time() + self._token_ttl
        session.touch()
        return token

    def count_active_sessions(self) -> int:
        """Count all active (non-expired) sessions."""
        return sum(1 for s in self._sessions.values() if not s.is_expired)

    def _generate_token(self, user_id: str) -> str:
        """Generate a cryptographically random token."""
        random_bytes = os.urandom(32)
        token_data = f"{user_id}:{time.time()}:{random_bytes.hex()}"
        return hashlib.sha256(token_data.encode()).hexdigest()
