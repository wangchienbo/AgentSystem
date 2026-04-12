"""User Service — multi-user management for AgentSystem App-OS.

Analogous to /etc/passwd + user home directory management in a Unix OS.
Handles user registration, profile management, resource initialization,
and user enumeration.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class UserServiceError(ValueError):
    pass


class UserRecord:
    """User profile record."""

    def __init__(
        self,
        user_id: str,
        created_at: str | None = None,
        display_name: str = "",
        metadata: dict[str, Any] | None = None,
        status: str = "active",
    ) -> None:
        self.user_id = user_id
        self.created_at = created_at or datetime.now(UTC).isoformat()
        self.display_name = display_name or user_id
        self.metadata = metadata or {}
        self.status = status
        self.last_login_at: str | None = None
        self.login_count: int = 0

    def record_login(self) -> None:
        self.last_login_at = datetime.now(UTC).isoformat()
        self.login_count += 1

    def update_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "display_name": self.display_name,
            "metadata": self.metadata,
            "status": self.status,
            "last_login_at": self.last_login_at,
            "login_count": self.login_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserRecord":
        record = cls(
            user_id=data["user_id"],
            created_at=data.get("created_at"),
            display_name=data.get("display_name", ""),
            metadata=data.get("metadata", {}),
            status=data.get("status", "active"),
        )
        record.last_login_at = data.get("last_login_at")
        record.login_count = data.get("login_count", 0)
        return record


class UserService:
    """Multi-user management service.

    Responsibilities:
    1. User registration and profile management
    2. User resource initialization (memory, interactive app workspace)
    3. User enumeration and lookup
    4. Soft delete (status = "deleted")
    """

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._users_dir = Path(base) / "users"
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._users: dict[str, UserRecord] = {}
        self._load_existing_users()

    def register_user(
        self,
        user_id: str,
        display_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> UserRecord:
        """Register a new user.

        Args:
            user_id: Unique user identifier (login name)
            display_name: Human-readable name (defaults to user_id)
            metadata: Arbitrary user metadata

        Returns:
            UserRecord for the new user

        Raises:
            UserServiceError: If user_id already exists
        """
        if user_id in self._users:
            raise UserServiceError(f"User already exists: {user_id}")

        record = UserRecord(
            user_id=user_id,
            display_name=display_name,
            metadata=metadata,
        )
        self._users[user_id] = record
        self._persist_user(record)
        return record

    def get_user(self, user_id: str) -> UserRecord | None:
        """Get user by ID. Returns None if not found."""
        return self._users.get(user_id)

    def require_user(self, user_id: str) -> UserRecord:
        """Get user by ID. Raises error if not found."""
        user = self._users.get(user_id)
        if not user:
            raise UserServiceError(f"User not found: {user_id}")
        return user

    def list_users(self, status: str | None = None) -> list[UserRecord]:
        """List all users, optionally filtered by status."""
        users = list(self._users.values())
        if status:
            users = [u for u in users if u.status == status]
        return users

    def update_user(self, user_id: str, **kwargs) -> UserRecord:
        """Update user profile fields."""
        user = self.require_user(user_id)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
            elif key == "metadata":
                user.metadata.update(value)
            else:
                user.update_metadata(key, value)
        self._persist_user(user)
        return user

    def delete_user(self, user_id: str) -> None:
        """Soft delete a user (sets status to 'deleted')."""
        user = self.require_user(user_id)
        user.status = "deleted"
        self._persist_user(user)

    def record_login(self, user_id: str) -> UserRecord:
        """Record a user login event."""
        user = self.require_user(user_id)
        user.record_login()
        self._persist_user(user)
        return user

    def user_exists(self, user_id: str) -> bool:
        """Check if a user exists."""
        return user_id in self._users

    def get_or_create(self, user_id: str, display_name: str = "") -> UserRecord:
        """Get existing user or create new one (idempotent login)."""
        if user_id in self._users:
            user = self._users[user_id]
            user.record_login()
            self._persist_user(user)
            return user
        return self.register_user(user_id, display_name)

    def get_user_count(self) -> int:
        """Get total number of registered users."""
        return len(self._users)

    def _persist_user(self, user: UserRecord) -> None:
        path = self._users_dir / f"{user.user_id}.json"
        try:
            path.write_text(json.dumps(user.to_dict(), indent=2, ensure_ascii=False))
        except OSError as e:
            raise UserServiceError(f"Failed to persist user {user.user_id}: {e}")

    def _load_existing_users(self) -> None:
        for path in self._users_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                user = UserRecord.from_dict(data)
                self._users[user.user_id] = user
            except Exception:
                continue
