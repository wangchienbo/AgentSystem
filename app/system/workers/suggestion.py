"""SuggestionWorker — 系统建议/可行性评估。

从属 Worker，通过 MasterControl 统一调度。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SuggestionWorker:
    """Handles system-level suggestions and feasibility analysis."""

    def __init__(self) -> None:
        self._suggestions: dict[str, dict] = {}

    def execute(self, operation: str, target: str, params: dict) -> dict:
        handler = {
            "suggest": self._suggest,
            "suggest_revise": self._suggest_revise,
            "suggest_approve": self._suggest_approve,
        }.get(operation)

        if handler is None:
            return {"status": "error", "message": f"不支持的操作: {operation}"}
        return handler(target, params)

    def _suggest(self, target: str, params: dict) -> dict:
        """Submit a system-level suggestion with feasibility analysis."""
        suggestion_id = f"sgt_{int(datetime.now().timestamp())}"
        category = params.get("category", "")
        problem = params.get("problem", "")
        expectation = params.get("expectation", "")

        # Simple feasibility analysis
        affected_module = self._analyze_category(category)
        plan = self._generate_plan(affected_module, problem, expectation)

        self._suggestions[suggestion_id] = {
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
            "plan": plan,
            "required_role": "admin",
        }

    def _suggest_revise(self, target: str, params: dict) -> dict:
        """Revise an existing suggestion."""
        suggestion_id = params.get("suggestion_id", target)
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            return {"status": "error", "message": f"未找到建议: {suggestion_id}"}

        # Update plan based on revision
        new_actions = params.get("actions", [])
        if new_actions:
            suggestion["plan"]["suggested_actions"] = new_actions
            suggestion["plan"]["revised_at"] = datetime.now().isoformat()

        return {"status": "success", "plan": suggestion["plan"]}

    def _suggest_approve(self, target: str, params: dict) -> dict:
        """Approve and execute a suggestion."""
        suggestion_id = params.get("suggestion_id", target)
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            return {"status": "error", "message": f"未找到建议: {suggestion_id}"}

        suggestion["status"] = "approved"
        suggestion["approved_at"] = datetime.now().isoformat()

        return {
            "status": "approved",
            "message": f"建议 {suggestion_id} 已批准，待执行",
            "plan": suggestion["plan"],
        }

    def _analyze_category(self, category: str) -> str:
        mapping = {
            "intent_understanding": "intent_analyzer",
            "app_creation": "app_assembler",
            "skill_management": "skill_manager",
            "permission": "user_manager",
            "system_upgrade": "file_worker",
        }
        return mapping.get(category, "unknown")

    def _generate_plan(self, module: str, problem: str, expectation: str) -> dict:
        return {
            "module": module,
            "problem": problem,
            "expectation": expectation,
            "suggested_actions": [f"检查 {module} 的当前配置", f"评估修改影响"],
            "risk_level": "low",
            "estimated_impact": "待评估",
        }
