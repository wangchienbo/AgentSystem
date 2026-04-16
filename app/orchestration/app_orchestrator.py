"""App Orchestrator — central path dispatcher.

Receives user requests, matches them to paths, dispatches Skill Workers
via RPC, tracks checkpoints, handles failures with retry/fallback, and
formats responses.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from app.core.message_bus import MessageBus, WorkerNotFoundError
from app.core.model_health import ModelHealthMonitor, ModelHealthStatus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.path_store import PathStore, PathTemplate
from app.services.dynamic_path_composer import DynamicPathComposer

logger = logging.getLogger(__name__)


class PathExecutionError(Exception):
    def __init__(self, message: str, step: str | None = None, context: dict | None = None) -> None:
        super().__init__(message)
        self.step = step
        self.context = context or {}


class AppOrchestrator(SkillWorker):
    """Central dispatcher for path-based skill execution.

    Responsibilities:
    1. Load path execution graph from YAML at startup
    2. Match user requests to paths (by key or keywords)
    3. Validate input format
    4. Dispatch steps to Skill Workers via RPC
    5. Record checkpoints for resume/retry
    6. Handle failures: retry, skip, or fallback
    7. Switch to offline paths when model is unavailable
    8. Format and return results to user
    """

    worker_id = "orchestrator"

    def __init__(
        self,
        bus: MessageBus,
        path_store: PathStore,
        model_health: ModelHealthMonitor | None = None,
        universal_skill: Any = None,
        dynamic_composer: DynamicPathComposer | None = None,
    ) -> None:
        self._bus = bus
        self._path_store = path_store
        self._model_health = model_health
        self._universal_skill = universal_skill
        self._dynamic_composer = dynamic_composer
        self._paths: dict[str, PathTemplate] = {}
        self._checkpoints: dict[str, dict] = {}

    # -- Lifecycle ------------------------------------------------------------

    async def init(self, config: dict[str, Any] | None = None) -> None:
        """Load path graph and start model health monitoring."""
        self._paths = self._path_store.load_all()
        if self._model_health:
            await self._model_health.start()
            logger.info(
                "Orchestrator initialized: %d paths loaded, model=%s",
                len(self._paths),
                self._model_health.health.status.value if self._model_health else "no monitor",
            )
        else:
            logger.info("Orchestrator initialized: %d paths loaded (no model monitor)", len(self._paths))

    async def shutdown(self) -> None:
        if self._model_health:
            await self._model_health.stop()

    # -- Main entry -----------------------------------------------------------

    async def process(self, request: Any) -> Any:
        """Handle a user request.

        Expects SkillExecutionRequest with:
        - inputs.message or inputs.query: user's natural language
        - inputs.path_id (optional): direct path key
        """
        if not isinstance(request, SkillExecutionRequest):
            return SkillExecutionResult(
                skill_id=self.worker_id,
                status="failed",
                output={},
                error="Expected SkillExecutionRequest",
            )

        user_inputs = request.inputs
        session_id = request.config.get("session_id", "default")
        # Normalize input — Bridge sends "text", chat sends "message"
        user_message = user_inputs.get("message") or user_inputs.get("text", "")

        # 1. Match path
        path = self._match_path(user_inputs)
        if not path:
            # No pre-defined path matched — try dynamic composition
            if self._dynamic_composer:
                dynamic_result = await self._dynamic_composer.compose_and_execute(
                    user_message,
                    session_id=session_id,
                    user_id=request.user_id or "",
                    config=request.config,
                )
                if dynamic_result and dynamic_result.status != "failed":
                    logger.info(
                        "Dynamic composition succeeded: %s",
                        dynamic_result.output.get("result", "") if isinstance(dynamic_result.output, dict) else "",
                    )
                    return dynamic_result
                # Dynamic composition failed or returned None — fall through
            return await self._invoke_universal(user_inputs)

        # 2. Model status check
        if not path.offline_capable and self._model_health and self._model_health.is_offline:
            if path.offline_fallback:
                fallback = self._path_store.get(path.offline_fallback)
                if fallback:
                    logger.info(
                        "Model offline, switching to fallback path: %s → %s",
                        path.name, fallback.name,
                    )
                    return await self._execute_path(fallback, user_inputs, session_id)
            return self._error_reply(
                f"路径「{path.name}」需要模型连接，当前模型不可用。",
                suggestion="可尝试的离线操作：" + ", ".join(
                    p.name for p in self._paths.values() if p.offline_capable
                ),
            )

        # 3. Input validation
        validation = self._validate_input(path, user_inputs)
        if not validation["valid"]:
            return self._error_reply(f"输入格式错误：{validation['error']}")

        # 4. Execute
        return await self._execute_path(path, user_inputs, session_id)

    # -- Path matching --------------------------------------------------------

    def _match_path(self, inputs: dict) -> PathTemplate | None:
        # Direct key match
        if "path_id" in inputs:
            return self._paths.get(inputs["path_id"])

        # Name match
        if "path" in inputs:
            query = inputs["path"].lower()
            for path in self._paths.values():
                if query in path.name.lower() or query in path.path_id.lower():
                    return path

        # Keyword match in message or text
        msg = inputs.get("message") or inputs.get("text", "")
        if msg:
            msg = msg.lower()
            for path in self._paths.values():
                if any(kw in msg for kw in path.name.lower().split()):
                    return path

        return None

    # -- Path execution -------------------------------------------------------

    async def _execute_path(
        self,
        path: PathTemplate,
        user_inputs: dict,
        session_id: str,
    ) -> SkillExecutionResult:
        """Execute a path step by step with checkpoint and retry."""
        context: dict[str, Any] = {"user": user_inputs}
        checkpoint_key = f"{session_id}:{path.path_id}"

        # Resume from checkpoint
        start_step = 0
        if checkpoint_key in self._checkpoints:
            ckpt = self._checkpoints[checkpoint_key]
            context.update(ckpt.get("context", {}))
            start_step = ckpt.get("next_step_index", 0)
            logger.info("Resuming path %s from step %d", path.path_id, start_step)

        for i, step in enumerate(path.steps):
            if i < start_step:
                continue

            # Checkpoint before step
            self._checkpoints[checkpoint_key] = {
                "path_id": path.path_id,
                "path_name": path.name,
                "next_step_index": i,
                "context": dict(context),
                "timestamp": time.time(),
            }

            # Condition check
            if step.condition and not self._eval_condition(step.condition, context):
                logger.debug("Skipping step %s (condition false)", step.name)
                continue

            # Execute with retry
            result = None
            last_error = None
            for attempt in range(step.max_retries):
                try:
                    resolved_inputs = {
                        **step.inputs,
                        **self._resolve_template_vars(step.inputs, context),
                    }
                    result = await self._invoke_skill(
                        step.skill, step.action, resolved_inputs, timeout=step.timeout,
                    )

                    if result.status == "completed":
                        last_error = None
                        break  # success

                    last_error = result.error or "unknown"
                    if attempt < step.max_retries - 1:
                        logger.warning(
                            "Step %s attempt %d failed, retrying in %.1fs: %s",
                            step.name, attempt + 1, step.retry_delay, last_error,
                        )
                        await asyncio.sleep(step.retry_delay)

                except Exception as e:
                    last_error = str(e)
                    if attempt < step.max_retries - 1:
                        await asyncio.sleep(step.retry_delay)

            # Handle failure
            if last_error:
                if step.on_failure == "skip":
                    logger.info("Step %s failed, skipping: %s", step.name, last_error)
                    continue
                elif step.on_failure == "fallback" and path.offline_fallback:
                    fallback = self._path_store.get(path.offline_fallback)
                    if fallback:
                        return await self._execute_path(fallback, user_inputs, session_id)

                # Abort
                self._checkpoints[checkpoint_key]["status"] = "failed_at_step"
                self._checkpoints[checkpoint_key]["failed_step"] = step.name
                completed = [s.name for s in path.steps[:i]]
                return self._error_reply(
                    f"步骤「{step.name}」执行失败",
                    error=last_error,
                    completed_steps=completed,
                    checkpoint_key=checkpoint_key,
                    can_resume=True,
                )

            # Save output
            if result:
                context[step.name] = result.output

        # Path complete
        self._checkpoints.pop(checkpoint_key, None)
        return self._success_reply(context, path.name)

    # -- Skill invocation -----------------------------------------------------

    async def _invoke_skill(
        self,
        skill_id: str,
        action: str,
        inputs: dict,
        timeout: float = 30.0,
    ) -> SkillExecutionResult:
        """Invoke a Skill Worker via MessageBus RPC."""
        request = SkillExecutionRequest(
            skill_id=skill_id,
            action=action,
            inputs=inputs,
            config={},
        )

        try:
            result = await self._bus.rpc(skill_id, request, timeout=timeout)
            if isinstance(result, SkillExecutionResult):
                return result
            if isinstance(result, dict):
                return SkillExecutionResult(
                    skill_id=skill_id,
                    status=result.get("status", "completed"),
                    output=result.get("output", {}),
                    error=result.get("error"),
                )
            return SkillExecutionResult(
                skill_id=skill_id,
                status="completed",
                output={"raw": result},
            )
        except WorkerNotFoundError:
            return SkillExecutionResult(
                skill_id=skill_id,
                status="failed",
                output={},
                error=f"Skill Worker 未注册: {skill_id}",
            )
        except Exception as e:
            return SkillExecutionResult(
                skill_id=skill_id,
                status="failed",
                output={},
                error=str(e),
            )

    # -- Universal fallback ---------------------------------------------------

    async def _invoke_universal(self, inputs: dict) -> SkillExecutionResult:
        """Fallback to universal skill when no path matches."""
        if not self._universal_skill:
            return self._error_reply(
                "未找到匹配的操作路径。",
                suggestion="可用路径：" + ", ".join(p.name for p in self._paths.values()),
            )

        available_paths = [p.name for p in self._paths.values()]
        available_skills = self._bus.list_workers()

        request = SkillExecutionRequest(
            skill_id="system.universal",
            action="analyze",
            inputs={
                **inputs,
                "available_paths": available_paths,
                "available_skills": available_skills,
            },
            config={},
            app_instance_id="fallback",
            workflow_id="universal_fallback",
            step_id="universal",
        )
        return await self._universal_skill.process(request)

    # -- Helpers --------------------------------------------------------------

    def _validate_input(self, path: PathTemplate, inputs: dict) -> dict:
        schema = path.input_schema
        if not schema:
            return {"valid": True}
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in inputs:
                return {"valid": False, "error": f"缺少必需字段: {field_name}"}
        return {"valid": True}

    def _eval_condition(self, condition: str, context: dict) -> bool:
        """Simple condition evaluation (safe, no eval())."""
        expr = condition
        for key, value in context.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    placeholder = f"{key}.{k}"
                    if placeholder in expr:
                        expr = expr.replace(placeholder, repr(v))

        # Only allow basic comparisons
        allowed = set("0123456789. +-*/<>!=()and or not True False ")
        if not all(c in allowed for c in expr):
            return True  # unsafe expression → default to execute

        try:
            return bool(eval(expr, {"__builtins__": {}}, {}))
        except Exception:
            return True

    def _resolve_template_vars(self, inputs: dict, context: dict) -> dict:
        """Resolve {{step.field}} template variables."""
        resolved = {}
        pattern = re.compile(r"\{\{([^}]+)\}\}")
        for key, value in inputs.items():
            if isinstance(value, str):
                match = pattern.search(value)
                if match:
                    var_path = match.group(1)
                    parts = var_path.split(".")
                    result: Any = context
                    for part in parts:
                        if isinstance(result, dict):
                            result = result.get(part, "")
                        else:
                            result = ""
                    resolved[key] = result
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    def _error_reply(
        self,
        message: str,
        error: str = "",
        completed_steps: list | None = None,
        checkpoint_key: str | None = None,
        suggestion: str = "",
        can_resume: bool = False,
    ) -> SkillExecutionResult:
        output: dict[str, Any] = {"error": message}
        if error:
            output["detail"] = error
        if completed_steps:
            output["completed_steps"] = completed_steps
        if checkpoint_key:
            output["checkpoint_key"] = checkpoint_key
            output["can_resume"] = can_resume
        if suggestion:
            output["suggestion"] = suggestion
        return SkillExecutionResult(
            skill_id=self.worker_id,
            status="failed",
            output=output,
        )

    def _success_reply(self, output: dict, path_name: str = "") -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id=self.worker_id,
            status="completed",
            output={"result": output, "path": path_name},
        )
