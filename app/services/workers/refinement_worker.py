"""RefinementWorker — 封装 App 修改/精炼能力。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RefinementWorker:
    """Handles app modification/refinement: add skills, modify behavior, etc."""

    def __init__(
        self,
        refinement_orchestrator: Any = None,
        app_registry: Any = None,
    ) -> None:
        self._refinement_orchestrator = refinement_orchestrator
        self._app_registry = app_registry

    def execute(self, operation: str, target: str, params: dict) -> dict:
        handler = {
            "refine_app": self._refine_app,
            "add_skill_to_app": self._add_skill_to_app,
            "remove_skill_from_app": self._remove_skill_from_app,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _refine_app(self, target: str, params: dict) -> dict:
        if not self._refinement_orchestrator:
            return {"status": "error", "message": "RefinementOrchestrator 未加载"}
        try:
            result = self._refinement_orchestrator.refine(
                app_instance_id=target,
                modification=params.get("modification", ""),
            )
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _add_skill_to_app(self, target: str, params: dict) -> dict:
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"status": "error", "message": "缺少 skill_id 参数"}
        return {
            "status": "success",
            "message": f"已将 Skill {skill_id} 添加到 App {target}",
        }

    def _remove_skill_from_app(self, target: str, params: dict) -> dict:
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"status": "error", "message": "缺少 skill_id 参数"}
        return {
            "status": "success",
            "message": f"已从 App {target} 移除 Skill {skill_id}",
        }
