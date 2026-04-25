"""Permission Skill — manage user roles and permissions through the LightBrain Gateway.

Root users can grant/revoke roles and manage permissions through natural language
commands in the chat interface, not just REST API calls.

Commands (root only):
- "给 {user} 管理员权限" / "grant admin to {user}"
- "撤销 {user} 的管理员权限" / "revoke admin from {user}"
- "查看 {user} 的权限" / "show permissions for {user}"
- "列出所有用户" / "list all users"
- "把 {user} 升级为 root" / "promote {user} to root"

Regular users can only view their own permissions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.user_service import UserService, Role, Permission, PermissionDenied


@dataclass
class PermissionCommand:
    """Parsed permission management command."""
    action: str  # grant_role, revoke_role, show_permissions, list_users, show_self
    target_user_id: str = ""
    new_role: str = ""
    raw_input: str = ""
    allow_self_modification: bool = False  # Allow self-mod in system evolution context


# Intent patterns for permission commands
PERMISSION_INTENT_PATTERNS: list[tuple[str, str]] = [
    # Grant admin role
    (r"(给|授予|赋|提升|升级)\s*([^\s，,。.!！]+)\s*(管理员|admin|sudo)", "grant_admin"),
    (r"(grant|give)\s*(admin|sudo|manager)\s*(to|for)\s*([^\s，,。.!！]+)", "grant_admin_en"),
    # Grant root role
    (r"(给|授予|赋|提升|升级)\s*([^\s，,。.!！]+)\s*(root|超级管理员|最高权限)", "grant_root"),
    (r"(promote|upgrade)\s*([^\s，,。.!！]+)\s*to\s*root", "grant_root_en"),
    # Revoke role
    (r"(撤销|取消|剥夺|移除|降级)\s*([^\s，,。.!！]+)\s*(的)?\s*(管理员|admin|sudo|权限|角色)", "revoke_role"),
    (r"(revoke|remove|demote)\s*(admin|sudo|role|permission)\s*(from|for)\s*([^\s，,。.!！]+)", "revoke_role_en"),
    # Show permissions
    (r"(查看|显示|查询)\s*([^\s，,。.!！]+)\s*(权限|角色|级别|身份)", "show_permissions"),
    (r"(show|check|get)\s*(permission|role)\s*(for|of)\s*([^\s，,。.!！]+)", "show_permissions_en"),
    # List users
    (r"(列出|查看|显示|查询)\s*(所有|全部)?.*(用户|成员|账号)", "list_users"),
    (r"(list|show|get)\s*(all\s*)?(user|member)", "list_users_en"),
    # My permissions
    (r"(我有?什么|我的|查看我的)\s*(权限|角色|级别|身份)", "show_self"),
    (r"(my|what\s*are\s*my)\s*(permission|role|level)", "show_self_en"),
]


def parse_permission_command(text: str, actor_id: str) -> PermissionCommand | None:
    """Parse a permission management command from natural language text.

    Returns PermissionCommand if matched, None otherwise.
    """
    for pattern, action in PERMISSION_INTENT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()

            if action in ("grant_admin", "grant_root"):
                target = groups[1] if len(groups) > 1 else ""
                role = Role.ROOT if "root" in action else Role.ADMIN
                return PermissionCommand(
                    action="grant_role",
                    target_user_id=target.strip(),
                    new_role=role,
                    raw_input=text,
                )

            if action in ("grant_admin_en", "grant_root_en"):
                target = groups[3] if len(groups) > 3 else groups[0]
                role = Role.ROOT if "root" in action else Role.ADMIN
                return PermissionCommand(
                    action="grant_role",
                    target_user_id=target.strip(),
                    new_role=role,
                    raw_input=text,
                )

            if action in ("revoke_role", "revoke_role_en"):
                target = groups[1] if len(groups) > 1 else (groups[3] if len(groups) > 3 else "")
                return PermissionCommand(
                    action="revoke_role",
                    target_user_id=target.strip(),
                    raw_input=text,
                )

            if action in ("show_permissions", "show_permissions_en"):
                target = groups[1] if len(groups) > 1 else (groups[3] if len(groups) > 3 else "")
                return PermissionCommand(
                    action="show_permissions",
                    target_user_id=target.strip(),
                    raw_input=text,
                )

            if action in ("list_users", "list_users_en"):
                return PermissionCommand(action="list_users", raw_input=text)

            if action in ("show_self", "show_self_en"):
                return PermissionCommand(
                    action="show_self",
                    target_user_id=actor_id,
                    raw_input=text,
                )

    return None


class PermissionSkillService:
    """Service for permission management through the chat interface."""

    def __init__(self, user_service: UserService) -> None:
        self._user_service = user_service

    def execute(self, command: PermissionCommand, actor_id: str) -> dict[str, Any]:
        """Execute a parsed permission command.

        Args:
            command: Parsed permission command
            actor_id: ID of the user issuing the command

        Returns:
            Result dict with status and message
        """
        actor = self._user_service.get_user(actor_id)
        if not actor:
            return {"success": False, "message": f"用户 '{actor_id}' 不存在"}

        if command.action == "grant_role":
            return self._grant_role(actor, command)
        elif command.action == "revoke_role":
            return self._revoke_role(actor, command)
        elif command.action == "show_permissions":
            return self._show_permissions(actor, command)
        elif command.action == "list_users":
            return self._list_users(actor)
        elif command.action == "show_self":
            return self._show_self(actor)

        return {"success": False, "message": f"未知权限命令: {command.action}"}

    def _grant_role(self, actor, command: PermissionCommand) -> dict[str, Any]:
        """Grant a role to a user."""
        if not actor.is_root and not actor.is_admin:
            return {
                "success": False,
                "message": f"❌ 你没有权限分配角色。你的角色是: {actor.role}。只有管理员和 root 可以分配角色。",
            }

        if command.new_role == Role.ROOT and not actor.is_root:
            return {
                "success": False,
                "message": "❌ 只有 root 用户才能授予 root 权限。",
            }

        target = self._user_service.get_user(command.target_user_id)
        if not target:
            return {"success": False, "message": f"❌ 用户 '{command.target_user_id}' 不存在"}

        # Allow self-modification in system evolution context
        if target.user_id == actor.user_id and not getattr(command, 'allow_self_modification', False):
            return {"success": False, "message": "❌ 不能修改自己的角色"}

        try:
            target.role = command.new_role
            self._user_service._persist_user(target)
            role_name = "root（超级管理员）" if command.new_role == Role.ROOT else "admin（管理员）"
            return {
                "success": True,
                "message": f"✅ 已将 {target.display_name}({target.user_id}) 升级为 {role_name}。",
                "user": target.to_safe_dict(),
            }
        except Exception as e:
            return {"success": False, "message": f"❌ 操作失败: {e}"}

    def _revoke_role(self, actor, command: PermissionCommand) -> dict[str, Any]:
        """Revoke admin/root role from a user."""
        if not actor.is_root and not actor.is_admin:
            return {
                "success": False,
                "message": f"❌ 你没有权限撤销角色。你的角色是: {actor.role}。",
            }

        target = self._user_service.get_user(command.target_user_id)
        if not target:
            return {"success": False, "message": f"❌ 用户 '{command.target_user_id}' 不存在"}

        if target.is_root and not actor.is_root:
            return {"success": False, "message": "❌ 只有 root 才能撤销其他 root 的角色。"}

        # Allow self-modification in system evolution context
        if target.user_id == actor.user_id and not getattr(command, 'allow_self_modification', False):
            return {"success": False, "message": "❌ 不能修改自己的角色。"}

        try:
            target.role = Role.USER
            self._user_service._persist_user(target)
            return {
                "success": True,
                "message": f"✅ 已撤销 {target.display_name}({target.user_id}) 的管理员权限，现为普通用户。",
                "user": target.to_safe_dict(),
            }
        except Exception as e:
            return {"success": False, "message": f"❌ 操作失败: {e}"}

    def _show_permissions(self, actor, command: PermissionCommand) -> dict[str, Any]:
        """Show permissions for a user."""
        # Regular users can only check their own permissions
        if not actor.is_admin and command.target_user_id != actor.user_id:
            return {
                "success": False,
                "message": "❌ 你只能查看自己的权限信息。",
            }

        target = self._user_service.get_user(command.target_user_id)
        if not target:
            return {"success": False, "message": f"❌ 用户 '{command.target_user_id}' 不存在"}

        from app.services.user_service import PERMISSION_MATRIX

        perms = PERMISSION_MATRIX.get((target.role, "own"), set())
        perms_other = PERMISSION_MATRIX.get((target.role, "other"), set())

        return {
            "success": True,
            "message": (
                f"📋 {target.display_name}({target.user_id}) 的权限信息：\n"
                f"  角色: {target.role}\n"
                f"  UID: {target.uid}\n"
                f"  自己的资源: {', '.join(sorted(perms)) or '无'}\n"
                f"  他人的资源: {', '.join(sorted(perms_other)) or '无'}\n"
                f"  拥有资源: {target.owned_resources}"
            ),
            "user": target.to_safe_dict(),
        }

    def _list_users(self, actor) -> dict[str, Any]:
        """List all users (admin+ only for full details)."""
        users = self._user_service.list_users()
        if actor.is_admin:
            user_list = "\n".join(
                f"  • {u.display_name}({u.user_id}) - {u.role} (UID:{u.uid}) - {u.status}"
                for u in users
            )
        else:
            user_list = "\n".join(
                f"  • {u.display_name}({u.user_id}) - {u.role}"
                for u in users
            )
        return {
            "success": True,
            "message": f"📋 系统用户列表（共 {len(users)} 人）：\n{user_list}",
            "count": len(users),
        }

    def _show_self(self, actor) -> dict[str, Any]:
        """Show the actor's own permissions."""
        from app.services.user_service import PERMISSION_MATRIX

        perms = PERMISSION_MATRIX.get((actor.role, "own"), set())
        perms_other = PERMISSION_MATRIX.get((actor.role, "other"), set())
        perms_system = PERMISSION_MATRIX.get((actor.role, "system"), set())

        return {
            "success": True,
            "message": (
                f"📋 你的权限信息：\n"
                f"  用户: {actor.display_name}({actor.user_id})\n"
                f"  角色: {actor.role}\n"
                f"  UID: {actor.uid}\n"
                f"  可操作自己的资源: {', '.join(sorted(perms)) or '无'}\n"
                f"  可操作他人的资源: {', '.join(sorted(perms_other)) or '无'}\n"
                f"  可操作系统资源: {', '.join(sorted(perms_system)) or '无'}\n"
                f"  拥有资源: {actor.owned_resources}"
            ),
            "user": actor.to_safe_dict(),
        }
