"""Permission registry — user permission self-registration table.

Tracks user roles and provides permission checks for asset operations.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

ROLE_LEVEL: dict[str, int] = {"user": 0, "admin": 1, "root": 2}


@dataclass
class UserPermission:
    user_id: str
    role: str = "user"
    role_level: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        self.role_level = ROLE_LEVEL.get(self.role, 0)
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class PermissionRegistry:
    """User permission self-registration table.

    Each user self-registers on first access.
    Roles can be upgraded by higher-level users.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: dict[str, UserPermission] = {}

    # -- Self-registration -------------------------------------------------

    def ensure_user(self, user_id: str, default_role: str = "user") -> UserPermission:
        """Ensure a user exists in the registry. Creates with default_role if missing."""
        with self._lock:
            if user_id not in self._users:
                self._users[user_id] = UserPermission(user_id=user_id, role=default_role)
            return self._users[user_id]

    # -- CRUD --------------------------------------------------------------

    def register_user(self, user_id: str, role: str = "user") -> UserPermission:
        with self._lock:
            user = UserPermission(user_id=user_id, role=role)
            self._users[user_id] = user
            return user

    def update_role(self, user_id: str, new_role: str) -> UserPermission | None:
        with self._lock:
            if user_id not in self._users:
                return None
            self._users[user_id].role = new_role
            self._users[user_id].role_level = ROLE_LEVEL.get(new_role, 0)
            self._users[user_id].updated_at = datetime.now(UTC).isoformat()
            return self._users[user_id]

    def get_user(self, user_id: str) -> UserPermission | None:
        return self._users.get(user_id)

    def get_role(self, user_id: str) -> str | None:
        user = self._users.get(user_id)
        return user.role if user else None

    def list_users(self) -> list[UserPermission]:
        return list(self._users.values())

    # -- Permission checks -------------------------------------------------

    def check_permission(self, user_id: str, required_level: int) -> bool:
        """Check if user has at least the required role level."""
        user = self._users.get(user_id)
        if not user:
            return False
        return user.role_level >= required_level

    def check_role(self, user_id: str, required_role: str) -> bool:
        required_level = ROLE_LEVEL.get(required_role, 999)
        return self.check_permission(user_id, required_level)

    def can_modify_asset(self, user_id: str, asset_owner_role: str) -> bool:
        """Check if user can modify an asset based on owner_role comparison.

        Rule: user's role level >= asset's owner_role level → can modify.
        """
        user = self._users.get(user_id)
        if not user:
            return False
        required_level = ROLE_LEVEL.get(asset_owner_role, 999)
        return user.role_level >= required_level

    def stats(self) -> dict:
        with self._lock:
            role_counts: dict[str, int] = {}
            for u in self._users.values():
                role_counts[u.role] = role_counts.get(u.role, 0) + 1
            return {
                "total_users": len(self._users),
                "role_counts": role_counts,
            }
