"""User Service — multi-user management for AgentSystem App-OS.

Commercial-grade: password auth, Linux-style role-based access control.
Roles: root (UID 0), admin (sudo), user (regular)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# ===========================================================================
# Permission constants (Linux-inspired)
# ===========================================================================

class Role:
    """Linux-inspired role hierarchy."""
    ROOT = "root"       # UID 0 — superuser, no restrictions
    ADMIN = "admin"     # sudo group — manage users + system config
    USER = "user"       # regular user — own resources only


class Permission:
    """Resource action permissions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    GRANT = "grant"     # change ownership / grant roles


# Permission matrix: (role, resource_owner) → allowed actions
# resource_owner == "own" means the actor owns the resource
# resource_owner == "other" means someone else owns it
# resource_owner == "system" means system-wide resource
PERMISSION_MATRIX: dict[tuple[str, str], set[str]] = {
    # root: unlimited access to everything
    (Role.ROOT, "own"):    {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE, Permission.GRANT},
    (Role.ROOT, "other"):  {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE, Permission.GRANT},
    (Role.ROOT, "system"): {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE, Permission.GRANT},

    # admin: full access to own, limited to others (read only), no system-level
    (Role.ADMIN, "own"):   {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE},
    (Role.ADMIN, "other"): {Permission.READ},
    (Role.ADMIN, "system"): set(),

    # user: only own resources
    (Role.USER, "own"):    {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE},
    (Role.USER, "other"):  {Permission.READ},
    (Role.USER, "system"): set(),
}

# Operations that always require root
ROOT_ONLY_OPS: set[str] = {
    "wipe_all_users",
    "create_root",
    "demote_root",
    "grant_root",
    "system_config",
    "delete_admin",
}

# Operations that require admin or root
ADMIN_OPS: set[str] = {
    "list_all_users",
    "delete_user",
    "grant_admin",
    "revoke_admin",
    "grant_sudo",
    "revoke_sudo",
    "view_all_resources",
}


# ===========================================================================
# Exceptions
# ===========================================================================

class UserServiceError(ValueError):
    pass


class PermissionDenied(UserServiceError):
    """Raised when a user lacks permission for an operation."""
    pass


# ===========================================================================
# Password helpers
# ===========================================================================

def hash_password(password: str) -> str:
    """Hash password with salt. Format: salt$hash."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored salt$hash."""
    if "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


# ===========================================================================
# User Record
# ===========================================================================

class UserRecord:
    """User profile record with password, role, and sudoers."""

    def __init__(
        self,
        user_id: str,
        created_at: str | None = None,
        display_name: str = "",
        role: str = Role.USER,
        password_hash: str = "",
        metadata: dict[str, Any] | None = None,
        status: str = "active",
        sudoers: list[str] | None = None,
        owned_resources: dict[str, list[str]] | None = None,
    ) -> None:
        self.user_id = user_id
        self.created_at = created_at or datetime.now(UTC).isoformat()
        self.display_name = display_name or user_id
        self.role = role
        self.password_hash = password_hash
        self.metadata = metadata or {}
        self.status = status
        self.last_login_at: str | None = None
        self.login_count: int = 0
        self.sudoers = sudoers or []  # users this user has granted sudo to
        self.owned_resources = owned_resources or {
            "apps": [],
            "workspaces": [],
            "memories": [],
            "pipelines": [],
            "scripts": [],
            "sessions": [],
        }

    @property
    def is_root(self) -> bool:
        return self.role == Role.ROOT

    @property
    def is_admin(self) -> bool:
        return self.role in (Role.ROOT, Role.ADMIN)

    @property
    def uid(self) -> int:
        """Numeric UID for display/logging. root=0, admin=1-999, user=1000+."""
        if self.is_root:
            return 0
        if self.role == Role.ADMIN:
            return 100 + hash(self.user_id) % 900
        return 1000 + hash(self.user_id) % 9000

    def record_login(self) -> None:
        self.last_login_at = datetime.now(UTC).isoformat()
        self.login_count += 1

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return verify_password(password, self.password_hash)

    def check_permission(self, action: str, resource_owner_id: str | None = None) -> bool:
        """Check if this user has permission for the given action.

        Args:
            action: Permission constant (read/write/delete/execute/grant)
            resource_owner_id: owner of the target resource. None = system-level.
        """
        if resource_owner_id is None:
            owner_type = "system"
        elif resource_owner_id == self.user_id:
            owner_type = "own"
        else:
            owner_type = "other"

        allowed = PERMISSION_MATRIX.get((self.role, owner_type), set())
        return action in allowed

    def claim_resource(self, resource_type: str, resource_id: str) -> None:
        """Record ownership of a resource."""
        if resource_type not in self.owned_resources:
            self.owned_resources[resource_type] = []
        if resource_id not in self.owned_resources[resource_type]:
            self.owned_resources[resource_type].append(resource_id)

    def release_resource(self, resource_type: str, resource_id: str) -> None:
        """Remove ownership of a resource."""
        if resource_type in self.owned_resources:
            self.owned_resources[resource_type] = [
                r for r in self.owned_resources[resource_type] if r != resource_id
            ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "display_name": self.display_name,
            "role": self.role,
            "password_hash": self.password_hash,
            "metadata": self.metadata,
            "status": self.status,
            "last_login_at": self.last_login_at,
            "login_count": self.login_count,
            "sudoers": self.sudoers,
            "owned_resources": self.owned_resources,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Alias for to_safe_dict. Public-facing dict (no password hash)."""
        return self.to_safe_dict()

    def to_safe_dict(self) -> dict[str, Any]:
        """Public-facing dict (no password hash)."""
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "role": self.role,
            "status": self.status,
            "last_login_at": self.last_login_at,
            "login_count": self.login_count,
            "created_at": self.created_at,
            "uid": self.uid,
            "is_admin": self.is_admin,
            "is_root": self.is_root,
            "sudoers": self.sudoers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserRecord":
        record = cls(
            user_id=data["user_id"],
            created_at=data.get("created_at"),
            display_name=data.get("display_name", ""),
            role=data.get("role", Role.USER),
            password_hash=data.get("password_hash", ""),
            metadata=data.get("metadata", {}),
            status=data.get("status", "active"),
            sudoers=data.get("sudoers", []),
            owned_resources=data.get("owned_resources", {
                "apps": [], "workspaces": [], "memories": [],
                "pipelines": [], "scripts": [], "sessions": [],
            }),
        )
        record.last_login_at = data.get("last_login_at")
        record.login_count = data.get("login_count", 0)
        return record


# ===========================================================================
# User Service
# ===========================================================================

class UserService:
    """Multi-user management with password auth and Linux-style RBAC."""

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._users_dir = Path(base) / "users"
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._users: dict[str, UserRecord] = {}
        self._load_existing_users()

    # -- Registration --

    def register_user(
        self,
        user_id: str,
        password: str,
        display_name: str = "",
        role: str = Role.USER,
        created_by: str | None = None,
    ) -> UserRecord:
        if user_id in self._users:
            raise UserServiceError(f"User already exists: {user_id}")
        if len(password) < 4:
            raise UserServiceError("Password must be at least 4 characters")
        if created_by and created_by not in self._users:
            raise UserServiceError(f"Creator not found: {created_by}")
        # Only root can create root/admin users
        if created_by and role in (Role.ROOT, Role.ADMIN):
            creator = self._users[created_by]
            if not creator.is_root:
                raise PermissionDenied("Only root can create root/admin users")

        record = UserRecord(
            user_id=user_id,
            display_name=display_name,
            role=role,
        )
        record.set_password(password)
        self._users[user_id] = record
        self._persist_user(record)
        return record

    # -- Auth --

    def authenticate(self, user_id: str, password: str) -> UserRecord | None:
        """Returns UserRecord if auth succeeds, None otherwise."""
        user = self._users.get(user_id)
        if not user:
            return None
        if user.status == "deleted":
            return None
        if not user.check_password(password):
            return None
        user.record_login()
        self._persist_user(user)
        return user

    # -- Lookup --

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def require_user(self, user_id: str) -> UserRecord:
        user = self._users.get(user_id)
        if not user:
            raise UserServiceError(f"User not found: {user_id}")
        return user

    def list_users(self, status: str | None = None) -> list[UserRecord]:
        users = list(self._users.values())
        if status:
            users = [u for u in users if u.status == status]
        return sorted(users, key=lambda u: u.created_at, reverse=True)

    # -- Permission checking --

    def assert_permission(self, actor_id: str, action: str, resource_owner_id: str | None = None) -> UserRecord:
        """Check permission and raise PermissionDenied if not allowed.

        Returns the actor's UserRecord if permitted.
        """
        actor = self.require_user(actor_id)
        if not actor.check_permission(action, resource_owner_id):
            raise PermissionDenied(
                f"User '{actor_id}' ({actor.role}) lacks '{action}' permission "
                f"on resource owned by '{resource_owner_id or 'system'}'"
            )
        return actor

    def assert_operation(self, actor_id: str, operation: str) -> UserRecord:
        """Check if actor can perform a named operation.

        Returns the actor's UserRecord if permitted.
        """
        actor = self.require_user(actor_id)

        if operation in ROOT_ONLY_OPS:
            if not actor.is_root:
                raise PermissionDenied(
                    f"Operation '{operation}' requires root. User '{actor_id}' is '{actor.role}'"
                )
            return actor

        if operation in ADMIN_OPS:
            if not actor.is_admin:
                raise PermissionDenied(
                    f"Operation '{operation}' requires admin. User '{actor_id}' is '{actor.role}'"
                )
            return actor

        return actor

    # -- Resource ownership --

    def get_resource_owner(self, resource_type: str, resource_id: str) -> str | None:
        """Find who owns a resource. Returns user_id or None."""
        for uid, user in self._users.items():
            if resource_type in user.owned_resources:
                if resource_id in user.owned_resources[resource_type]:
                    return uid
        return None

    def transfer_ownership(self, actor_id: str, resource_type: str, resource_id: str, new_owner_id: str) -> None:
        """Transfer resource ownership. Requires admin/root."""
        self.assert_operation(actor_id, "grant_admin")  # admin-level op
        old_owner = self.get_resource_owner(resource_type, resource_id)
        if old_owner:
            old_user = self.require_user(old_owner)
            old_user.release_resource(resource_type, resource_id)
            self._persist_user(old_user)
        new_owner = self.require_user(new_owner_id)
        new_owner.claim_resource(resource_type, resource_id)
        self._persist_user(new_owner)

    # -- Admin / Root operations --

    def grant_role(self, actor_id: str, target_id: str, new_role: str) -> UserRecord:
        """Grant a role to a user. Actor must be admin (for admin role) or root (for root role)."""
        self.assert_operation(actor_id, "grant_admin")

        if new_role == Role.ROOT:
            self.assert_operation(actor_id, "grant_root")

        target = self.require_user(target_id)
        target.role = new_role
        self._persist_user(target)
        return target

    def revoke_role(self, actor_id: str, target_id: str) -> UserRecord:
        """Revoke admin/root role, demote to regular user."""
        actor = self.require_user(actor_id)
        target = self.require_user(target_id)

        if target.is_root and not actor.is_root:
            raise PermissionDenied("Only root can demote another root user")

        if target.is_root and actor.is_root and target.user_id == actor.user_id:
            raise PermissionDenied("Cannot demote yourself from root")

        target.role = Role.USER
        self._persist_user(target)
        return target

    def grant_sudo(self, actor_id: str, target_id: str) -> UserRecord:
        """Grant sudo privilege (admin role) to a user."""
        return self.grant_role(actor_id, target_id, Role.ADMIN)

    def revoke_sudo(self, actor_id: str, target_id: str) -> UserRecord:
        """Revoke sudo privilege from a user."""
        return self.revoke_role(actor_id, target_id)

    def update_user(self, user_id: str, **kwargs) -> UserRecord:
        user = self.require_user(user_id)
        for key, value in kwargs.items():
            if key == "password":
                user.set_password(value)
            elif hasattr(user, key):
                setattr(user, key, value)
            elif key == "metadata":
                user.metadata.update(value)
            else:
                user.update_metadata(key, value)
        self._persist_user(user)
        return user

    def delete_user(self, user_id: str) -> None:
        user = self.require_user(user_id)
        user.status = "deleted"
        self._persist_user(user)

    def hard_delete_user(self, user_id: str) -> None:
        """Permanently delete a user and their data file."""
        if user_id not in self._users:
            raise UserServiceError(f"User not found: {user_id}")
        del self._users[user_id]
        path = self._users_dir / f"{user_id}.json"
        if path.exists():
            path.unlink()

    def wipe_all_users(self) -> int:
        """Delete ALL users. Use with caution. Returns count deleted."""
        count = len(self._users)
        for uid in list(self._users.keys()):
            self.hard_delete_user(uid)
        return count

    def create_root(self, user_id: str, password: str, display_name: str = "") -> UserRecord:
        """Create a root user. Only works if no root exists yet."""
        roots = [u for u in self._users.values() if u.role == Role.ROOT and u.status == "active"]
        if roots:
            raise UserServiceError("A root user already exists")
        return self.register_user(user_id, password, display_name, role=Role.ROOT)

    def create_admin(self, user_id: str, password: str, display_name: str = "") -> UserRecord:
        """Create an admin user. Only works if no admin/root exists yet."""
        admins = [u for u in self._users.values() if u.is_admin and u.status == "active"]
        if admins:
            raise UserServiceError("An admin or root already exists")
        return self.register_user(user_id, password, display_name, role=Role.ADMIN)

    # -- Password change (self-service) --

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        user = self.require_user(user_id)
        if not user.check_password(old_password):
            raise UserServiceError("Current password is incorrect")
        if len(new_password) < 4:
            raise UserServiceError("New password must be at least 4 characters")
        user.set_password(new_password)
        self._persist_user(user)
        return True

    # -- Helpers --

    def user_exists(self, user_id: str) -> bool:
        return user_id in self._users

    def get_user_count(self, active_only: bool = True) -> int:
        if active_only:
            return sum(1 for u in self._users.values() if u.status == "active")
        return len(self._users)

    def get_root_users(self) -> list[UserRecord]:
        return [u for u in self._users.values() if u.role == Role.ROOT and u.status == "active"]

    def get_admin_users(self) -> list[UserRecord]:
        return [u for u in self._users.values() if u.is_admin and u.status == "active"]

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
