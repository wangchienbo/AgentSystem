"""Master Control — 系统级唯一入口（Kernel Space）。

所有系统操作（App/Skill/Path/权限/建议）的统一执行入口。
不直接与用户对话，通过交互层间接交互。

设计原则:
- 权限检查集中: 所有操作必须经过 MasterControl.auth_check
- 调用路由统一: 根据 tool category 路由到对应 Worker
- 审计日志: 所有操作记录到审计日志
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    """Single audit log entry."""
    timestamp: str
    user_id: str
    operation: str
    target: str
    params: dict
    result: str  # "granted" | "denied" | "executed" | "error"
    message: str = ""


@dataclass
class AuthRequest:
    """Permission authorization request."""
    user_id: str
    user_role: str  # user | admin | root | system
    operation: str
    target: str
    params: dict = field(default_factory=dict)


@dataclass
class AuthResponse:
    """Permission authorization response."""
    status: str  # granted | denied | pending
    message: str = ""
    required_role: str | None = None
    impact: dict | None = None  # dry-run analysis


ROLE_LEVEL: dict[str, int] = {
    "user": 0,
    "admin": 1,
    "root": 2,
    "system": 99,
}


class MasterControl:
    """系统级主控（Kernel）。

    所有系统操作的唯一入口：
    - 权限审批 (auth_check)
    - 操作执行 (execute)
    - 系统建议 (suggest)
    - 状态查询 (query)
    """

    def __init__(self) -> None:
        self._workers: dict[str, Any] = {}
        self._audit_log: list[AuditRecord] = []
        self._suggestions: dict[str, dict] = {}
        self._tool_registry = None  # set via set_tool_registry
        self._permission_service = None  # set via set_permission_service

    def set_tool_registry(self, registry) -> None:
        self._tool_registry = registry

    def set_permission_service(self, service) -> None:
        self._permission_service = service

    def register_worker(self, name: str, worker: Any) -> None:
        """Register a subordinate worker (domain service)."""
        self._workers[name] = worker

    def get_worker(self, name: str) -> Any | None:
        return self._workers.get(name)

    # -- Permission Layer ---------------------------------------------------

    def auth_check(self, request: AuthRequest) -> AuthResponse:
        """Check if user has permission to perform the operation.

        Rules:
        1. user.role_level >= target.owner_role_level → granted
        2. Otherwise → denied with required_role hint
        """
        user_level = ROLE_LEVEL.get(request.user_role, 0)

        # Root/system can do anything
        if user_level >= ROLE_LEVEL["root"]:
            return AuthResponse(
                status="granted",
                message=f"用户 {request.user_id} ({request.user_role}) 权限通过",
            )

        # Check specific operation permissions
        required_role = self._resolve_required_role(request)
        required_level = ROLE_LEVEL.get(required_role, 0)

        if user_level >= required_level:
            return AuthResponse(
                status="granted",
                message=f"用户 {request.user_id} ({request.user_role}) 权限通过",
            )

        return AuthResponse(
            status="denied",
            message=f"权限不足: 需要 {required_role} 角色，当前为 {request.user_role}",
            required_role=required_role,
        )

    def _resolve_required_role(self, request: AuthRequest) -> str:
        """Resolve the minimum role required for an operation."""
        # Permission operations need root
        if request.operation in ("grant_admin", "grant_root", "revoke_role"):
            return "root"

        # System-level operations need admin
        if request.operation in ("create_skill", "modify_skill", "delete_skill"):
            return "admin"

        # System suggestions need admin for approval
        if request.operation in ("suggest_approve", "system_upgrade"):
            return "admin"

        # User can modify their own apps
        if request.operation in ("create_app", "modify_app", "delete_app"):
            return "user"

        # Default: user level is enough for read/query operations
        return "user"

    # -- Execute Layer ------------------------------------------------------

    async def execute(
        self,
        operation: str,
        user_id: str,
        user_role: str,
        target: str = "",
        params: dict | None = None,
    ) -> dict:
        """Unified execution entry point.

        Flow:
        1. Auth check
        2. Dry-run analysis (for complex ops)
        3. Route to appropriate worker
        4. Record audit
        5. Return result
        """
        params = params or {}

        # 1. Auth check
        auth = self.auth_check(AuthRequest(
            user_id=user_id,
            user_role=user_role,
            operation=operation,
            target=target,
            params=params,
        ))

        if auth.status != "granted":
            self._record_audit(user_id, operation, target, params, "denied", auth.message)
            return {"status": "denied", "message": auth.message, "required_role": auth.required_role}

        # 2. Route to worker
        worker = self._resolve_worker(operation)
        if worker is None:
            return {"status": "error", "message": f"未找到处理 {operation} 的 Worker"}

        # 3. Execute
        try:
            if hasattr(worker, "execute") and callable(worker.execute):
                result = worker.execute(operation, target, params)
            elif hasattr(worker, operation) and callable(getattr(worker, operation)):
                result = getattr(worker, operation)(target, params)
            else:
                result = {"status": "error", "message": f"Worker 不支持 {operation}"}

            self._record_audit(user_id, operation, target, params, "executed", str(result))
            return result

        except Exception as e:
            logger.exception("MasterControl execute error: %s", operation)
            self._record_audit(user_id, operation, target, params, "error", str(e))
            return {"status": "error", "message": str(e)}

    def _resolve_worker(self, operation: str) -> Any | None:
        """Route operation to the appropriate worker."""
        # App lifecycle/management → app_management_worker
        if operation in (
            "create_app", "start_app", "stop_app", "pause_app", "resume_app",
            "list_apps", "query_app", "modify_app", "delete_app",
            "install_app", "uninstall_app",
        ):
            return self._workers.get("app_management")

        # User/permission → user_manager
        if operation in (
            "grant_admin", "grant_root", "revoke_role",
            "show_permissions", "list_users", "show_self",
        ):
            return self._workers.get("user_manager")

        # Skill management → skill_manager
        if operation in ("create_skill", "modify_skill", "delete_skill", "list_skills"):
            return self._workers.get("skill_manager")

        # App refinement → refinement_worker
        if operation in ("refine_app", "add_skill_to_app", "remove_skill_from_app"):
            return self._workers.get("refinement")

        # System suggestions → suggestion_worker
        if operation in ("suggest", "suggest_revise", "suggest_approve"):
            return self._workers.get("suggestion")

        # File/persistence → file_worker
        if operation in ("save_state", "load_state", "upgrade", "rollback"):
            return self._workers.get("file_worker")

        # Package management → package_manager (from asset_center)
        if operation in (
            "package_list_installed", "package_show", "package_build",
            "package_install", "package_uninstall", "package_rollback", "package_search",
        ):
            return self._workers.get("package_manager")

        return None

    # -- Suggestion Layer ---------------------------------------------------

    def suggest(self, user_id: str, category: str, problem: str, expectation: str = "") -> dict:
        """Submit a system-level suggestion.

        Returns feasibility analysis + modification plan.
        """
        suggestion_id = f"sgt_{int(datetime.now().timestamp())}"

        # Analyze which module is affected
        affected_module = self._analyze_suggestion(category)
        if affected_module is None:
            return {
                "status": "error",
                "message": f"无法识别建议类别: {category}",
            }

        # Generate a plan
        plan = self._generate_plan(affected_module, problem, expectation)

        self._suggestions[suggestion_id] = {
            "user_id": user_id,
            "category": category,
            "problem": problem,
            "expectation": expectation,
            "affected_module": affected_module,
            "plan": plan,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

        return {
            "status": "pending",
            "suggestion_id": suggestion_id,
            "affected_module": affected_module,
            "plan": plan,
            "required_role": "admin",
        }

    def _analyze_suggestion(self, category: str) -> str | None:
        """Map suggestion category to affected system module."""
        mapping = {
            "intent_understanding": "intent_analyzer",
            "app_creation": "app_assembler",
            "skill_management": "skill_manager",
            "permission": "user_manager",
            "system_upgrade": "file_worker",
        }
        return mapping.get(category)

    def _generate_plan(self, module: str, problem: str, expectation: str) -> dict:
        """Generate a modification plan for the affected module."""
        return {
            "module": module,
            "problem": problem,
            "expectation": expectation,
            "suggested_actions": [
                f"检查 {module} 的当前配置",
                f"评估修改 {module} 的影响范围",
            ],
            "risk_level": "low",
            "estimated_impact": "待评估",
        }

    # -- Query Layer (read-only) --------------------------------------------

    def query(self, query_type: str, params: dict | None = None) -> dict:
        """Read-only system state query."""
        params = params or {}

        if query_type == "system_status":
            return self._query_system_status()
        elif query_type == "audit_log":
            return self._query_audit_log(params)
        elif query_type == "architecture":
            return self._query_architecture()
        elif query_type == "suggestions":
            return self._query_suggestions(params)
        else:
            return {"status": "error", "message": f"未知查询类型: {query_type}"}

    def _query_system_status(self) -> dict:
        worker_count = len(self._workers)
        audit_count = len(self._audit_log)
        suggestion_count = len(self._suggestions)
        return {
            "status": "healthy",
            "workers": worker_count,
            "audit_entries": audit_count,
            "pending_suggestions": suggestion_count,
        }

    def _query_audit_log(self, params: dict) -> dict:
        limit = params.get("limit", 20)
        records = self._audit_log[-limit:]
        return {
            "total": len(self._audit_log),
            "records": [
                {
                    "timestamp": r.timestamp,
                    "user_id": r.user_id,
                    "operation": r.operation,
                    "target": r.target,
                    "result": r.result,
                }
                for r in records
            ],
        }

    def _query_architecture(self) -> dict:
        return {
            "workers": list(self._workers.keys()),
            "suggestions": len(self._suggestions),
            "audit_entries": len(self._audit_log),
        }

    def _query_suggestions(self, params: dict) -> dict:
        suggestion_id = params.get("suggestion_id")
        if suggestion_id:
            suggestion = self._suggestions.get(suggestion_id)
            if suggestion:
                return {"status": "found", "suggestion": suggestion}
            return {"status": "not_found"}
        return {
            "suggestions": {
                sid: {"category": s["category"], "status": s["status"], "created_at": s["created_at"]}
                for sid, s in self._suggestions.items()
            },
        }

    # -- Audit ---------------------------------------------------------------

    def _record_audit(
        self, user_id: str, operation: str, target: str,
        params: dict, result: str, message: str = "",
    ) -> None:
        record = AuditRecord(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            operation=operation,
            target=target,
            params=params,
            result=result,
            message=message,
        )
        self._audit_log.append(record)
        # Keep last 1000 entries
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]
