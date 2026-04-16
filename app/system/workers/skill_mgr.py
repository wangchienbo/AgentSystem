"""SkillManager — 封装 Skill 工厂/注册/验证/修改能力。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillManager:
    """Handles skill lifecycle: create, modify, delete, list, register, validate."""

    def __init__(
        self,
        skill_registry: Any = None,
        skill_meta_service: Any = None,
        skill_control: Any = None,
    ) -> None:
        self._skill_registry = skill_registry
        self._skill_meta_service = skill_meta_service
        self._skill_control = skill_control

    def execute(self, operation: str, target: str, params: dict) -> dict:
        handler = {
            "create_skill": self._create_skill,
            "modify_skill": self._modify_skill,
            "delete_skill": self._delete_skill,
            "list_skills": self._list_skills,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _create_skill(self, target: str, params: dict) -> dict:
        skill_id = params.get("skill_id", target)
        if self._skill_meta_service:
            try:
                meta = self._skill_meta_service.register_skill(
                    skill_id=skill_id,
                    name=params.get("name", skill_id),
                    version=params.get("version", "1.0.0"),
                    description=params.get("description", ""),
                )
                return {"status": "success", "data": {"skill_id": skill_id, "meta": meta}}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "success", "data": {"skill_id": skill_id, "note": "Skill 注册跳过（服务未加载）"}}

    def _modify_skill(self, target: str, params: dict) -> dict:
        # Delegated to refinement via MasterControl for complex modifications
        return {"status": "delegated", "message": "Skill 修改应通过 refinement_worker 处理"}

    def _delete_skill(self, target: str, params: dict) -> dict:
        if self._skill_meta_service:
            try:
                self._skill_meta_service.unregister(target)
                return {"status": "success", "message": f"Skill {target} 已卸载"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "success", "message": f"Skill {target} 卸载跳过（服务未加载）"}

    def _list_skills(self, target: str, params: dict) -> dict:
        if self._skill_meta_service:
            try:
                skills = self._skill_meta_service.list_all()
                return {"status": "success", "data": {"skills": skills, "total": len(skills)}}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "success", "data": {"skills": [], "note": "SkillMetaService 未加载"}}
