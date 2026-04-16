"""FileWorker — 封装持久化/升级/回滚能力。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FileWorker:
    """Handles persistence, upgrade, and rollback operations."""

    def __init__(
        self,
        persistence: Any = None,
    ) -> None:
        self._persistence = persistence

    def execute(self, operation: str, target: str, params: dict) -> dict:
        handler = {
            "save_state": self._save_state,
            "load_state": self._load_state,
            "upgrade": self._upgrade,
            "rollback": self._rollback,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _save_state(self, target: str, params: dict) -> dict:
        if not self._persistence:
            return {"status": "error", "message": "PersistenceService 未加载"}
        try:
            self._persistence.save_state()
            return {"status": "success", "message": "系统状态已保存"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _load_state(self, target: str, params: dict) -> dict:
        if not self._persistence:
            return {"status": "error", "message": "PersistenceService 未加载"}
        try:
            self._persistence.load_state()
            return {"status": "success", "message": "系统状态已加载"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _upgrade(self, target: str, params: dict) -> dict:
        version = params.get("version", "latest")
        return {
            "status": "success",
            "message": f"系统升级到 {version}（模拟）",
            "data": {"version": version},
        }

    def _rollback(self, target: str, params: dict) -> dict:
        version = params.get("version", "previous")
        return {
            "status": "success",
            "message": f"系统回滚到 {version}（模拟）",
            "data": {"version": version},
        }
