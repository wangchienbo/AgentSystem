"""AppManagementWorker — 封装 App 注册/生命周期/安装能力。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from app.runtime_paths import resolve_runtime_paths

logger = logging.getLogger(__name__)

# Governance imports (Phase I)
try:
    from app.governance.audit_logger import AuditLogger
    from app.governance.cost_quota import CostQuotaManager, QuotaExceededError
    from app.governance.policy_authority_service import PolicyAuthorityService, PolicyAuthorityError
    GOVERNANCE_ENABLED = True
except ImportError:
    GOVERNANCE_ENABLED = False
    AuditLogger = None  # type: ignore
    CostQuotaManager = None  # type: ignore
    QuotaExceededError = Exception  # type: ignore
    PolicyAuthorityService = None  # type: ignore
    PolicyAuthorityError = Exception  # type: ignore


class AppManagementWorker:
    """Handles all App lifecycle operations: create, start, stop, pause, resume,
    list, query, modify, delete, install, uninstall.
    """

    def __init__(
        self,
        app_registry: Any = None,
        lifecycle: Any = None,
        app_installer: Any = None,
        app_catalog: Any = None,
        tool_registry: Any = None,
        runtime_center: Any = None,
        audit_logger: Any = None,
        cost_quota_manager: Any = None,
        policy_authority_service: Any = None,
    ) -> None:
        self._app_registry = app_registry
        self._lifecycle = lifecycle
        self._app_installer = app_installer
        self._app_catalog = app_catalog
        self._tool_registry = tool_registry
        self._runtime_center = runtime_center
        # Governance services (Phase I)
        self._audit_logger = audit_logger or (AuditLogger() if GOVERNANCE_ENABLED else None)
        self._cost_quota_manager = cost_quota_manager or (CostQuotaManager() if GOVERNANCE_ENABLED else None)
        # PolicyAuthorityService requires store, so it must be injected from runtime.py
        self._policy_authority_service = policy_authority_service

    def execute(self, operation: str, target: str, params: dict) -> dict:
        """Dispatch to the appropriate method."""
        handler = {
            "create_app": self._create_app,
            "start_app": self._start_app,
            "stop_app": self._stop_app,
            "pause_app": self._pause_app,
            "resume_app": self._resume_app,
            "list_apps": self._list_apps,
            "query_app": self._query_app,
            "modify_app": self._modify_app,
            "delete_app": self._delete_app,
            "install_app": self._install_app,
            "uninstall_app": self._uninstall_app,
            "start_asset": self._start_asset,
            "stop_asset": self._stop_asset,
            "health_check_asset": self._health_check_asset,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _create_app(self, target: str, params: dict) -> dict:
        if not self._app_installer:
            return {"status": "error", "message": "AppInstaller 未加载"}
        
        # Governance: Check quota before operation
        user_id = params.get("user_id", "system")
        if self._cost_quota_manager:
            try:
                self._cost_quota_manager.check_and_consume("app_create", user_id)
            except QuotaExceededError as e:
                if self._audit_logger:
                    self._audit_logger.log("create_app", target, "failed", user_id, {"reason": "quota_exceeded", "error": str(e)})
                return {"status": "error", "message": f"配额不足：{str(e)}"}
        
        blueprint_id = params.get("blueprint_id", target)
        try:
            result = self._app_installer.install_app(
                blueprint_id=blueprint_id,
                user_id=user_id,
                app_instance_id=params.get("app_instance_id"),
            )
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("create_app", target, "success", user_id, {"blueprint_id": blueprint_id, "app_id": result.app_instance_id})
            return {"status": "success", "data": {"app_id": result.app_instance_id}}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("create_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _start_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        
        user_id = params.get("user_id", "system")
        try:
            self._lifecycle.transition(target, "start", reason=params.get("reason", "master_control.start_app"))
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("start_app", target, "success", user_id, {"reason": params.get("reason", "master_control.start_app")})
            return {"status": "success", "message": f"App {target} 已启动"}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("start_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _stop_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        user_id = params.get("user_id", "system")
        try:
            self._lifecycle.transition(target, "stop", reason=params.get("reason", "master_control.stop_app"))
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("stop_app", target, "success", user_id, {"reason": params.get("reason", "master_control.stop_app")})
            return {"status": "success", "message": f"App {target} 已停止"}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("stop_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _start_asset(self, target: str, params: dict) -> dict:
        result = self._start_app(target, params)
        if result.get("status") != "success":
            return result
        if self._runtime_center:
            try:
                instance = self._lifecycle.get_instance(target)
                entry = self._runtime_center.get(target)
                if entry is None:
                    # N3-08: Real subprocess launch if entry_point provided
                    pid = params.get("pid", 0)
                    endpoint = params.get("endpoint", "")
                    entry_point = params.get("entry_point", "")
                    if entry_point and pid == 0:
                        pid = self._launch_subprocess(entry_point, params)
                    if pid == 0:
                        # Fallback: simulate with current process
                        pid = os.getpid()
                        endpoint = params.get("endpoint", "http://127.0.0.1:0")

                    entry = self._runtime_center.register(
                        asset_id=target,
                        version=getattr(instance, "installed_version", "0.0.0") or "0.0.0",
                        pid=pid,
                        endpoint=endpoint,
                        owner=getattr(instance, "owner_user_id", "system"),
                    )
                    status_val = entry.status
                    if hasattr(status_val, 'value'):
                        status_val = status_val.value
                    # Map internal AssetState to external contract (running vs active)
                    status_str = "running" if status_val == "active" else status_val
                    result["data"] = {
                        "asset_id": entry.asset_id,
                        "status": status_str,
                        "pid": entry.metadata.get("pid", pid),
                        "endpoint": entry.metadata.get("endpoint", endpoint),
                        "version": entry.version,
                    }
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return result

    def _launch_subprocess(self, entry_point: str, params: dict) -> int:
        """Launch an asset as a real subprocess. Returns the child PID."""
        import shlex
        cmd = entry_point
        env = {**os.environ}
        env.update(params.get("env", {}))
        runtime_data_dir = Path(os.environ.get("AGENTSYSTEM_DATA_DIR") or resolve_runtime_paths().data_dir)
        cwd = str((Path(params.get("cwd") or runtime_data_dir).expanduser()).resolve())
        try:
            proc = subprocess.Popen(
                shlex.split(cmd) if " " in cmd else [cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cwd,
                start_new_session=True,
            )
            logger.info("Launched subprocess for asset: pid=%d, cmd=%s", proc.pid, cmd)
            return proc.pid
        except Exception as e:
            logger.error("Failed to launch subprocess: %s", e)
            raise

    def _stop_asset(self, target: str, params: dict) -> dict:
        result = self._stop_app(target, params)
        if result.get("status") != "success":
            return result
        if self._runtime_center:
            entry = self._runtime_center.get(target)
            entry_pid = entry.metadata.get("pid") if entry else None
            if entry_pid and entry_pid != os.getpid():
                # N3-08: Real process kill
                self._kill_subprocess(entry_pid)
            self._runtime_center.mark_stopped(target)
            self._runtime_center.unregister(target, pid=params.get("pid"))
        return {"status": "success", "message": f"Asset {target} 已停止"}

    def _kill_subprocess(self, pid: int) -> None:
        """Kill a running subprocess by PID. Graceful SIGTERM first, then SIGKILL."""
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("Sent SIGTERM to pid=%d", pid)
        except ProcessLookupError:
            return  # Already gone
        except OSError as e:
            logger.warning("Failed to send SIGTERM to pid=%d: %s", pid, e)
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info("Sent SIGKILL to pid=%d", pid)
            except OSError:
                pass  # Best effort

    def _health_check_asset(self, target: str, params: dict) -> dict:
        if not self._runtime_center:
            return {"status": "error", "message": "RuntimeCenter 未加载"}
        entry = self._runtime_center.get(target)
        if entry is None:
            return {"status": "not_found", "message": f"未找到运行中的资产: {target}"}

        # N3-08: Real process health check
        entry_pid = entry.metadata.get("pid") if entry else None
        process_alive = self._check_process_alive(entry_pid) if entry_pid else False
        runtime_status = entry.status if entry else None
        if not process_alive and runtime_status == "running":
            if self._runtime_center:
                self._runtime_center.mark_crashed(target)
            runtime_status = "crashed"

        return {
            "status": "success" if process_alive else "degraded",
            "data": {
                "asset_id": entry.asset_id,
                "status": runtime_status,
                "pid": entry_pid,
                "endpoint": entry.metadata.get("endpoint") if entry else None,
                "version": entry.version if entry else None,
                "process_alive": process_alive,
                "uptime": self._runtime_center.get_uptime(target) if self._runtime_center else None,
            },
        }

    @staticmethod
    def _check_process_alive(pid: int) -> bool:
        """Check if a process is still running by sending signal 0."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            return True
        except OSError:
            return False

    def _pause_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        user_id = params.get("user_id", "system")
        try:
            self._lifecycle.pause_app(target)
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("pause_app", target, "success", user_id, {})
            return {"status": "success", "message": f"App {target} 已暂停"}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("pause_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _resume_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        user_id = params.get("user_id", "system")
        try:
            self._lifecycle.resume_app(target)
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("resume_app", target, "success", user_id, {})
            return {"status": "success", "message": f"App {target} 已恢复"}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("resume_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _list_apps(self, target: str, params: dict) -> dict:
        if not self._app_registry:
            return {"status": "error", "message": "AppRegistry 未加载"}
        entries = self._app_registry.list_entries()
        status_filter = params.get("status")
        result = []
        for entry in entries:
            if status_filter and status_filter != "all":
                if getattr(entry, "status", None) != status_filter:
                    continue
            result.append({
                "id": getattr(entry, "app_instance_id", str(entry)),
                "blueprint_id": getattr(entry, "blueprint_id", ""),
                "status": getattr(entry, "status", "unknown"),
                "owner": getattr(entry, "owner_user_id", "system"),
            })
        return {"status": "success", "data": {"apps": result, "total": len(result)}}

    def _query_app(self, target: str, params: dict) -> dict:
        if not self._app_registry:
            return {"status": "error", "message": "AppRegistry 未加载"}
        lookup_target = target or params.get("target_app") or params.get("app_id") or ""
        entries = self._app_registry.list_entries()
        for entry in entries:
            bid = getattr(entry, "blueprint_id", "")
            iid = getattr(entry, "app_instance_id", "")
            if lookup_target in (bid, iid):
                return {
                    "status": "success",
                    "data": {
                        "blueprint_id": bid,
                        "instance_id": iid,
                        "status": getattr(entry, "status", "unknown"),
                        "owner": getattr(entry, "owner_user_id", "system"),
                        "context_hints": params.get("context_hints", []),
                        "related_session_ids": params.get("related_session_ids", []),
                    },
                }
        return {"status": "not_found", "message": f"未找到 App: {lookup_target or target}"}

    def _modify_app(self, target: str, params: dict) -> dict:
        # Delegate to refinement worker via MasterControl
        lookup_target = target or params.get("target_app") or params.get("app_id") or ""
        return {
            "status": "delegated",
            "message": "修改 App 应通过 refinement_worker 执行",
            "data": {
                "target_app": lookup_target,
                "context_hints": params.get("context_hints", []),
                "related_session_ids": params.get("related_session_ids", []),
            },
        }

    def _delete_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        user_id = params.get("user_id", "system")
        try:
            self._lifecycle.delete_app(target)
            # Governance: Audit log
            if self._audit_logger:
                self._audit_logger.log("delete_app", target, "success", user_id, {})
            return {"status": "success", "message": f"App {target} 已删除"}
        except Exception as e:
            if self._audit_logger:
                self._audit_logger.log("delete_app", target, "failed", user_id, {"error": str(e)})
            return {"status": "error", "message": str(e)}

    def _install_app(self, target: str, params: dict) -> dict:
        return self._create_app(target, params)

    def _uninstall_app(self, target: str, params: dict) -> dict:
        user_id = params.get("user_id", "system")
        # Governance: Check quota before operation
        if self._cost_quota_manager:
            try:
                self._cost_quota_manager.check_and_consume("app_uninstall", user_id)
            except QuotaExceededError as e:
                if self._audit_logger:
                    self._audit_logger.log("uninstall_app", target, "failed", user_id, {"reason": "quota_exceeded", "error": str(e)})
                return {"status": "error", "message": f"配额不足：{str(e)}"}
        
        # 1. Stop in RuntimeCenter first
        if self._runtime_center:
            entry = self._runtime_center.get(target)
            if entry:
                self._runtime_center.mark_stopped(target)
                self._runtime_center.unregister(target)
        # 2. Uninstall from AssetCenter if available
        try:
            from app.api.main import asset_center
            asset_center.uninstall(target)
        except Exception:
            pass  # Non-blocking: asset may not be in AssetCenter
        # 3. Delete lifecycle and registry entries
        result = self._delete_app(target, params)
        # Governance: Audit log for uninstall
        if self._audit_logger and result.get("status") == "success":
            self._audit_logger.log("uninstall_app", target, "success", user_id, {})
        elif self._audit_logger and result.get("status") == "error":
            self._audit_logger.log("uninstall_app", target, "failed", user_id, {"error": result.get("message")})
        return result
