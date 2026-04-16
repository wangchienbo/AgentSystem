"""UserManager — 封装用户/权限/角色管理。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UserManager:
    """Handles user, permission, and role operations."""

    def __init__(
        self,
        user_service: Any = None,
        permission_service: Any = None,
    ) -> None:
        self._user_service = user_service
        self._permission_service = permission_service

    def execute(self, operation: str, target: str, params: dict) -> dict:
        handler = {
            "grant_admin": self._grant_admin,
            "grant_root": self._grant_root,
            "revoke_role": self._revoke_role,
            "show_permissions": self._show_permissions,
            "list_users": self._list_users,
            "show_self": self._show_self,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _grant_admin(self, target: str, params: dict) -> dict:
        if not self._permission_service:
            return {"status": "error", "message": "权限服务未加载"}
        target_user = params.get("target_user", target)
        try:
            self._permission_service.grant_role(target_user, "admin")
            return {"status": "success", "message": f"已将 {target_user} 提升为 admin"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _grant_root(self, target: str, params: dict) -> dict:
        if not self._permission_service:
            return {"status": "error", "message": "权限服务未加载"}
        target_user = params.get("target_user", target)
        try:
            self._permission_service.grant_role(target_user, "root")
            return {"status": "success", "message": f"已将 {target_user} 提升为 root"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _revoke_role(self, target: str, params: dict) -> dict:
        if not self._permission_service:
            return {"status": "error", "message": "权限服务未加载"}
        target_user = params.get("target_user", target)
        try:
            self._permission_service.revoke_role(target_user)
            return {"status": "success", "message": f"已撤销 {target_user} 的管理角色"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _show_permissions(self, target: str, params: dict) -> dict:
        if not self._permission_service:
            return {"status": "error", "message": "权限服务未加载"}
        target_user = params.get("target_user", target)
        try:
            perms = self._permission_service.get_permissions(target_user)
            return {"status": "success", "data": perms}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _list_users(self, target: str, params: dict) -> dict:
        if not self._user_service:
            return {"status": "error", "message": "用户服务未加载"}
        try:
            users = self._user_service.list_users()
            return {"status": "success", "data": {"users": users, "total": len(users)}}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _show_self(self, target: str, params: dict) -> dict:
        return self._show_permissions(target, params)
