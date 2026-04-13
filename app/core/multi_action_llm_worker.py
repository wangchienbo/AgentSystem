"""Multi-Action LLM Worker — generated from MD docs or config center.

A Worker that wraps a skill defined by configuration (model, prompts,
actions). Each action has its own system_prompt + user_prompt_template.
This is the target type for remotely installed skills.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.skill_worker import SkillWorker, WorkerHealth
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.model_router import ModelRouter

logger = logging.getLogger(__name__)


class MultiActionLlmWorker(SkillWorker):
    """Skill Worker with multiple actions, each with its own prompts.

    Configuration-driven: all behaviour comes from config (model,
    prompts, input/output schemas). No Python code needed beyond this
    template.
    """

    def __init__(
        self,
        worker_id: str,
        model_router: ModelRouter,
        model_config: dict[str, Any],
        actions: dict[str, dict[str, Any]],
        description: str = "",
    ) -> None:
        self.worker_id = worker_id
        self._model_router = model_router
        self._model_config = model_config
        self._actions = actions
        self._description = description
        self._client: Any = None
        self._initialized = False

    # -- Lifecycle ------------------------------------------------------------

    async def init(self, config: dict[str, Any] | None = None) -> None:
        model_name = self._model_config.get("model", "gpt-4o")
        try:
            self._client = self._model_router.get_client_by_name(model_name)
            self._initialized = True
            logger.info("MultiActionLlmWorker initialized: %s (model=%s)", self.worker_id, model_name)
        except Exception:
            logger.warning(
                "MultiActionLlmWorker init failed (model offline?): %s",
                self.worker_id,
            )
            # Don't raise — allow offline fallback

    async def shutdown(self) -> None:
        self._initialized = False

    # -- Main processing ------------------------------------------------------

    async def process(self, request: Any) -> Any:
        """Unified entry: route by action."""
        if not isinstance(request, SkillExecutionRequest):
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error="Expected SkillExecutionRequest",
            )

        action = request.action or "execute"

        # Built-in status action
        if action == "status":
            return await self.action_status(request)

        if action not in self._actions:
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error=f"Unsupported action: {action}. Available: {list(self._actions.keys())}",
            )

        action_config = self._actions[action]

        try:
            prompt = self._build_prompt(action_config, request.inputs)
            response = await self._call_llm(action_config, prompt)
            output = self._parse_output(action_config, response, request.inputs)

            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="completed",
                output=output,
            )
        except Exception as e:
            logger.exception("MultiActionLlmWorker %s action=%s failed", self.worker_id, action)
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error=str(e),
                error_detail={"action": action},
            )

    # -- Built-in actions -----------------------------------------------------

    async def action_status(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id=self.worker_id,
            status="completed",
            output={
                "worker_id": self.worker_id,
                "description": self._description,
                "initialized": self._initialized,
                "model": self._model_config.get("model"),
                "available_actions": list(self._actions.keys()),
            },
        )

    async def action_offline(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Offline fallback — return structured info for Orchestrator."""
        return SkillExecutionResult(
            skill_id=self.worker_id,
            status="failed",
            output={
                "mode": "offline",
                "worker_id": self.worker_id,
                "available_actions": list(self._actions.keys()),
            },
            error="Model unavailable, skill cannot run offline",
        )

    # -- Internal helpers -----------------------------------------------------

    def _build_prompt(self, action_config: dict, inputs: dict) -> str:
        template = action_config.get("user_prompt", "")
        for key, value in inputs.items():
            placeholder = "{{" + key + "}}"
            template = template.replace(placeholder, str(value))
        return template

    async def _call_llm(self, action_config: dict, prompt: str) -> str:
        messages = []
        sys_prompt = action_config.get("system_prompt", "")
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat(
            messages=messages,
            model=self._model_config.get("model"),
            temperature=self._model_config.get("temperature", 0.7),
            max_tokens=self._model_config.get("max_tokens", 4096),
        )
        return response.content

    def _parse_output(self, action_config: dict, response: str, inputs: dict) -> dict:
        output_format = action_config.get("output_format")
        if not output_format:
            return {"response": response}

        try:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            pass

        return {"response": response, "_raw": True}

    # -- Health ---------------------------------------------------------------

    async def healthcheck(self) -> WorkerHealth:
        if not self._initialized:
            return WorkerHealth(
                status="unhealthy",
                details={"reason": "not initialized (model may be offline)"},
            )
        return WorkerHealth(
            status="healthy",
            details={"model": self._model_config.get("model")},
        )
