"""AppManagementWorker — 封装 App 注册/生命周期/安装能力。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._app_registry = app_registry
        self._lifecycle = lifecycle
        self._app_installer = app_installer
        self._app_catalog = app_catalog
        self._tool_registry = tool_registry
        self._runtime_center = runtime_center

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
        blueprint_id = params.get("blueprint_id", target)
        user_id = params.get("user_id", "system")
        try:
            result = self._app_installer.install_app(
                blueprint_id=blueprint_id,
                user_id=user_id,
                app_instance_id=params.get("app_instance_id"),
            )
            return {"status": "success", "data": {"app_id": result.app_instance_id}}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _start_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        try:
            self._lifecycle.transition(target, "start", reason=params.get("reason", "master_control.start_app"))
            return {"status": "success", "message": f"App {target} 已启动"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stop_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        try:
            self._lifecycle.transition(target, "stop", reason=params.get("reason", "master_control.stop_app"))
            return {"status": "success", "message": f"App {target} 已停止"}
        except Exception as e:
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
                    entry = self._runtime_center.register(
                        asset_id=target,
                        version=getattr(instance, "installed_version", "0.0.0") or "0.0.0",
                        pid=params.get("pid", 0),
                        endpoint=params.get("endpoint", ""),
                        owner=getattr(instance, "owner_user_id", "system"),
                    )
                result["data"] = {
                    "asset_id": entry.asset_id,
                    "status": entry.status,
                    "pid": entry.pid,
                    "endpoint": entry.endpoint,
                    "version": entry.version,
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return result

    def _stop_asset(self, target: str, params: dict) -> dict:
        result = self._stop_app(target, params)
        if result.get("status") != "success":
            return result
        if self._runtime_center:
            self._runtime_center.mark_stopped(target)
            self._runtime_center.unregister(target, pid=params.get("pid"))
        return {"status": "success", "message": f"Asset {target} 已停止"}

    def _health_check_asset(self, target: str, params: dict) -> dict:
        if not self._runtime_center:
            return {"status": "error", "message": "RuntimeCenter 未加载"}
        entry = self._runtime_center.get(target)
        if entry is None:
            return {"status": "not_found", "message": f"未找到运行中的资产: {target}"}
        return {
            "status": "success",
            "data": {
                "asset_id": entry.asset_id,
                "status": entry.status,
                "pid": entry.pid,
                "endpoint": entry.endpoint,
                "version": entry.version,
                "uptime": self._runtime_center.get_uptime(target),
            },
        }

    def _pause_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        try:
            self._lifecycle.pause_app(target)
            return {"status": "success", "message": f"App {target} 已暂停"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _resume_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        try:
            self._lifecycle.resume_app(target)
            return {"status": "success", "message": f"App {target} 已恢复"}
        except Exception as e:
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
        entries = self._app_registry.list_entries()
        for entry in entries:
            bid = getattr(entry, "blueprint_id", "")
            iid = getattr(entry, "app_instance_id", "")
            if target in (bid, iid):
                return {
                    "status": "success",
                    "data": {
                        "blueprint_id": bid,
                        "instance_id": iid,
                        "status": getattr(entry, "status", "unknown"),
                        "owner": getattr(entry, "owner_user_id", "system"),
                    },
                }
        return {"status": "not_found", "message": f"未找到 App: {target}"}

    def _modify_app(self, target: str, params: dict) -> dict:
        # Delegate to refinement worker via MasterControl
        return {"status": "delegated", "message": "修改 App 应通过 refinement_worker 执行"}

    def _delete_app(self, target: str, params: dict) -> dict:
        if not self._lifecycle:
            return {"status": "error", "message": "Lifecycle 未加载"}
        try:
            self._lifecycle.delete_app(target)
            return {"status": "success", "message": f"App {target} 已删除"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _install_app(self, target: str, params: dict) -> dict:
        return self._create_app(target, params)

    def _uninstall_app(self, target: str, params: dict) -> dict:
        return self._delete_app(target, params)
