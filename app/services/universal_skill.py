"""Universal Skill — LLM-powered catch-all for unmatched requests.

When no path or skill matches the user's request, the Universal Skill
analyzes the need, decides what to do, and responds. It is the final
fallback before returning "I don't understand."
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.skill_worker import SkillWorker, WorkerHealth
from app.core.model_health import ModelHealthMonitor
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.model_router import ModelRouter

logger = logging.getLogger(__name__)

UNIVERSAL_SYSTEM_PROMPT = """你是 AgentSystem 的万能助手。
当用户请求没有匹配的路径或 Skill 时，由你来处理。

你的职责：
1. 分析用户的真实需求
2. 如果问题可以通过现有能力解决，建议用户调用相应的 Skill
3. 如果无法自动化，给出清晰的手动操作建议
4. 保持回答简洁、有条理

如果用户的问题明显超出系统能力范围，诚实地告知，并提供替代方案。"""


class UniversalSkill(SkillWorker):
    """Catch-all skill powered by LLM."""

    worker_id = "system.universal"

    def __init__(
        self,
        model_router: ModelRouter,
        model_health: ModelHealthMonitor | None = None,
    ) -> None:
        self._model_router = model_router
        self._model_health = model_health
        self._client: Any = None
        self._initialized = False

    async def init(self, config: dict[str, Any] | None = None) -> None:
        try:
            self._client = self._model_router.get_client("universal_skill")
            self._initialized = True
            logger.info("UniversalSkill initialized")
        except Exception:
            logger.warning("UniversalSkill init failed (model offline)")

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error="Expected SkillExecutionRequest",
            )

        if not self._initialized:
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error="模型不可用，万能 Skill 无法运行",
            )

        user_message = request.inputs.get("message", request.inputs.get("query", ""))
        available_paths = request.inputs.get("available_paths", [])
        available_skills = request.inputs.get("available_skills", [])

        try:
            prompt = self._build_prompt(user_message, available_paths, available_skills)
            response = await self._client.chat(
                messages=[
                    {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.7,
            )

            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="completed",
                output={
                    "response": response.content,
                    "mode": "universal_fallback",
                },
            )
        except Exception as e:
            logger.exception("UniversalSkill failed")
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error=f"万能 Skill 执行失败: {e}",
            )

    async def shutdown(self) -> None:
        self._initialized = False

    def _build_prompt(
        self,
        message: str,
        available_paths: list[str],
        available_skills: list[str],
    ) -> str:
        parts = [f"用户请求：{message}\n"]

        if available_paths:
            parts.append(f"\n当前可用的路径：{', '.join(available_paths)}")
        if available_skills:
            parts.append(f"\n当前可用的 Skill：{', '.join(available_skills)}")

        parts.append(
            "\n请分析用户的请求，判断如何处理。"
            "如果能解决，告诉用户该怎么做；如果不能，请解释原因并提供替代方案。"
        )
        return "\n".join(parts)

    async def healthcheck(self) -> WorkerHealth:
        if not self._initialized:
            return WorkerHealth(status="unhealthy", details={"reason": "model offline"})
        return WorkerHealth(status="healthy")
