"""Dynamic Path Composer — LLM-driven skill chain composition.

When no pre-defined YAML path matches a user request, this service:
1. Discovers available skills from SkillMetaService + MessageBus
2. Asks LLM to compose an execution plan (ordered skill chain)
3. Validates I/O compatibility between consecutive steps
4. Executes the plan step-by-step via MessageBus RPC

Fallback: on any failure, gracefully degrades to UniversalSkill.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.models.dynamic_path import DynamicPathPlan, DynamicPathStep
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)

# Max LLM retries for malformed JSON
_MAX_LLM_RETRIES = 2


class DynamicPathComposerError(Exception):
    """Dynamic path composition failed."""
    pass


class DynamicPathComposer:
    """Composes and executes skill chains from natural language requests."""

    def __init__(
        self,
        skill_meta_service: Any,
        message_bus: Any,
        model_router: Any,
        universal_skill: Any = None,
    ) -> None:
        self._meta = skill_meta_service
        self._bus = message_bus
        self._router = model_router
        self._universal = universal_skill

    # -- Public API -----------------------------------------------------------

    async def compose_and_execute(
        self,
        user_input: str,
        *,
        session_id: str = "default",
        user_id: str = "",
        config: dict | None = None,
    ) -> SkillExecutionResult:
        """Try to compose a skill chain from the user request and execute it.

        Returns:
            - SkillExecutionResult on success or graceful fallback
            - None if no suitable skills are available (caller should try other paths)
        """
        # 1. Discover available skills
        skills = self._discover_skills()
        if not skills:
            logger.debug("No skills available for dynamic composition")
            return None

        # 2. Plan with LLM
        plan = await self._plan_chain(user_input, skills)
        if plan is None:
            logger.debug("LLM failed to produce a valid plan")
            return await self._fallback(user_input, session_id)

        # 3. Validate plan
        valid, error = self._validate_plan(plan, skills)
        if not valid:
            logger.warning("Plan validation failed: %s", error)
            return await self._fallback(user_input, session_id)

        # 4. Execute plan
        try:
            result = await self._execute_plan(
                plan, user_input, session_id, user_id, config or {},
            )
            return result
        except Exception as exc:
            logger.error("Plan execution failed: %s", exc, exc_info=True)
            return await self._fallback(user_input, session_id)

    # -- Skill Discovery ------------------------------------------------------

    def _discover_skills(self) -> list[dict[str, Any]]:
        """Build a compact skill catalog for the LLM prompt."""
        meta_list = self._meta.list_all() if self._meta else []
        bus_workers = self._bus.list_workers() if self._bus else []

        # Merge metadata with bus workers
        known_ids = {m.skill_id for m in meta_list}
        skills = []

        for meta in meta_list:
            # Build action dict safely — handle both dict and object styles
            action_dict = {}
            if meta.actions:
                for name, a in meta.actions.items():
                    if isinstance(a, dict):
                        action_dict[name] = {
                            "description": a.get("description", ""),
                            "input_schema": a.get("input_schema", {}),
                            "output_schema": a.get("output_schema", {}),
                        }
                    else:
                        # Object with attributes (ActionMeta or mock)
                        action_dict[name] = {
                            "description": str(getattr(a, "description", "")),
                            "input_schema": getattr(a, "input_schema", {}) or {},
                            "output_schema": getattr(a, "output_schema", {}) or {},
                        }

            # Safely extract fields — handle MagicMock and real objects
            skill_info = {
                "skill_id": str(getattr(meta, "skill_id", "")),
                "name": str(getattr(meta, "name", "")),
                "description": str(getattr(meta, "description", "")),
                "input_schema": self._safe_schema(meta.input_schema),
                "output_schema": self._safe_schema(meta.output_schema),
                "actions": action_dict,
                "offline_capable": bool(getattr(meta, "offline_capable", False)),
            }
            skills.append(skill_info)

        # Add bus workers that don't have metadata
        for worker_id in bus_workers:
            if worker_id not in known_ids:
                skills.append({
                    "skill_id": worker_id,
                    "name": worker_id,
                    "description": f"Worker: {worker_id}",
                    "input_schema": {},
                    "output_schema": {},
                    "actions": {},
                    "offline_capable": False,
                })

        return skills

    @staticmethod
    def _safe_schema(value: Any) -> dict:
        """Safely convert a schema value to a JSON-serializable dict."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        # MagicMock or other objects — try to convert
        try:
            result = dict(value) if hasattr(value, "keys") else {}
            return result
        except (TypeError, ValueError):
            return {}

    # -- LLM Planning ---------------------------------------------------------

    async def _plan_chain(
        self,
        user_input: str,
        skills: list[dict[str, Any]],
    ) -> DynamicPathPlan | None:
        """Ask LLM to compose an execution plan from available skills."""
        prompt = self._build_planning_prompt(user_input, skills)

        for attempt in range(1 + _MAX_LLM_RETRIES):
            try:
                response_text = await self._call_llm(prompt)
                plan = self._parse_plan_response(response_text)
                if plan:
                    logger.info(
                        "Dynamic plan created: goal=%s, steps=%d",
                        plan.goal, len(plan.steps),
                    )
                    return plan
            except Exception as exc:
                logger.warning(
                    "LLM planning attempt %d failed: %s",
                    attempt + 1, exc,
                )

        return None

    def _build_planning_prompt(
        self,
        user_input: str,
        skills: list[dict[str, Any]],
    ) -> str:
        """Build the LLM prompt for skill chain planning."""
        skill_catalog = json.dumps(skills, ensure_ascii=False, indent=2)

        return (
            "You are a skill chain planner. Your job is to compose an ordered "
            "sequence of skill calls to fulfill the user's request.\n\n"
            f"## User Request\n{user_input}\n\n"
            f"## Available Skills\n{skill_catalog}\n\n"
            "## Rules\n"
            "1. Only use skills listed in Available Skills.\n"
            "2. Keep the chain short — max 5 steps.\n"
            "3. Each step must logically follow from the previous one.\n"
            "4. Use input_mapping to connect data between steps:\n"
            '   - "$user.X" means the user\'s input field X\n'
            '   - "$step_N.Y" means output field Y from step N (1-indexed)\n'
            '   - Plain text means a literal value\n'
            "5. If the request can be handled by a single skill, use one step.\n"
            "6. If no available skill can handle the request, return an empty steps list.\n\n"
            "## Output Format\n"
            "Respond with ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "goal": "what the user wants to achieve",\n'
            '  "reasoning": "why you chose this plan",\n'
            '  "steps": [\n'
            "    {\n"
            '      "skill_id": "skill id from catalog",\n'
            '      "action": "execute",\n'
            '      "input_mapping": {"field_name": "$user.field_name"},\n'
            '      "description": "why this step"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM via ModelRouter."""
        if not self._router:
            raise DynamicPathComposerError("ModelRouter not available")

        client = self._router.get_client("dynamic_path_composer", "balanced")
        # OpenAIResponsesClient.chat is sync, wrap in executor
        import asyncio
        loop = asyncio.get_event_loop()
        text, _ = await loop.run_in_executor(
            None,
            lambda: client.chat(
                messages=[
                    {"role": "system", "content": "You are a skill chain planner. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
                stream=False,
            ),
        )
        return text

    def _parse_plan_response(self, text: str) -> DynamicPathPlan | None:
        """Extract and parse JSON plan from LLM response."""
        # Try to find JSON block
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

        # Validate required fields
        if not isinstance(data, dict):
            return None
        if "steps" not in data or not isinstance(data["steps"], list):
            return None
        if not data["steps"]:
            return None

        try:
            return DynamicPathPlan(**data)
        except Exception:
            return None

    # -- Validation -----------------------------------------------------------

    def _validate_plan(
        self,
        plan: DynamicPathPlan,
        skills: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Validate that all referenced skills exist and chain is coherent."""
        skill_ids = {s["skill_id"] for s in skills}

        for i, step in enumerate(plan.steps):
            if step.skill_id not in skill_ids:
                return False, f"Step {i+1}: skill '{step.skill_id}' not in registry"

        # Check input_mapping references are valid
        for i, step in enumerate(plan.steps):
            for field_name, source in step.input_mapping.items():
                if source.startswith("$step_"):
                    ref = source.split(".")[0]
                    try:
                        ref_num = int(ref.replace("$step_", ""))
                        if ref_num < 1 or ref_num > i:
                            return (
                                False,
                                f"Step {i+1}: invalid reference {source} "
                                f"(step {ref_num} doesn't exist yet)",
                            )
                    except ValueError:
                        return False, f"Step {i+1}: malformed reference {source}"

        return True, ""

    # -- Execution ------------------------------------------------------------

    async def _execute_plan(
        self,
        plan: DynamicPathPlan,
        user_input: str,
        session_id: str,
        user_id: str,
        config: dict,
    ) -> SkillExecutionResult:
        """Execute the plan step by step, resolving input mappings."""
        step_outputs: dict[int, dict[str, Any]] = {}
        # Parse user input as potential structured data
        user_data = self._parse_user_input(user_input)

        for i, step in enumerate(plan.steps, start=1):
            # Resolve inputs
            resolved_inputs = {}
            for field_name, source in step.input_mapping.items():
                resolved_inputs[field_name] = self._resolve_source(
                    source, user_data, step_outputs,
                )

            # If no input_mapping, pass the raw user input as "message"
            if not resolved_inputs:
                resolved_inputs["message"] = user_input
                # Also pass accumulated context
                if step_outputs:
                    resolved_inputs["context"] = step_outputs

            request = SkillExecutionRequest(
                skill_id=step.skill_id,
                action=step.action,
                inputs=resolved_inputs,
                config={**config, "session_id": session_id},
                user_id=user_id,
                workflow_id=f"dynamic_compose/{plan.goal[:30]}",
                step_id=f"step_{i}",
                app_instance_id="dynamic_path",
            )

            # Execute via MessageBus RPC
            try:
                result = await self._bus.rpc(
                    target_id=step.skill_id,
                    payload=request.model_dump(mode="json"),
                    timeout=30.0,
                )
            except Exception as exc:
                logger.error("Step %d RPC failed (%s): %s", i, step.skill_id, exc)
                return SkillExecutionResult(
                    skill_id="dynamic_path_composer",
                    status="failed",
                    output={"error": f"Step {i} ({step.skill_id}) failed: {exc}"},
                    error=str(exc),
                )

            # Parse result
            step_output = self._extract_output(result)
            step_outputs[i] = step_output

            # Check for failure
            if isinstance(result, dict) and result.get("status") == "failed":
                return SkillExecutionResult(
                    skill_id="dynamic_path_composer",
                    status="failed",
                    output={
                        "error": f"Step {i} ({step.skill_id}) returned failure",
                        "detail": result.get("error", ""),
                        "completed_steps": i - 1,
                    },
                    error=result.get("error", "Unknown error"),
                )

        # All steps completed successfully
        final_output = step_outputs.get(len(plan.steps), {})
        return SkillExecutionResult(
            skill_id="dynamic_path_composer",
            status="completed",
            output={
                "result": final_output,
                "plan": plan.model_dump(mode="json"),
                "all_step_outputs": {str(k): v for k, v in step_outputs.items()},
            },
        )

    def _resolve_source(
        self,
        source: str,
        user_data: dict,
        step_outputs: dict[int, dict],
    ) -> Any:
        """Resolve a source reference to an actual value."""
        if source.startswith("$user."):
            key = source[len("$user."):]
            return user_data.get(key, source)
        elif source.startswith("$step_"):
            parts = source.split(".", 1)
            try:
                step_num = int(parts[0].replace("$step_", ""))
                field = parts[1] if len(parts) > 1 else None
                output = step_outputs.get(step_num, {})
                if field:
                    return output.get(field, source)
                return output
            except (ValueError, IndexError):
                return source
        else:
            # Literal value
            return source

    def _parse_user_input(self, text: str) -> dict:
        """Try to extract structured fields from user input text."""
        # Simple heuristic: look for key: value patterns
        result = {"text": text}
        for match in re.finditer(r'(\w+)\s*[:：]\s*(.+?)(?:\n|$)', text):
            key, value = match.group(1).strip(), match.group(2).strip()
            result[key.lower()] = value
        return result

    def _extract_output(self, result: Any) -> dict:
        """Extract output dict from RPC result."""
        if isinstance(result, dict):
            if "output" in result:
                output = result["output"]
                if isinstance(output, dict):
                    return output
                return {"value": str(output)}
            return result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return {"text": result}
        return {"value": str(result)}

    # -- Fallback -------------------------------------------------------------

    async def _fallback(
        self,
        user_input: str,
        session_id: str,
    ) -> SkillExecutionResult:
        """Fallback to UniversalSkill when dynamic composition fails."""
        if not self._universal:
            return SkillExecutionResult(
                skill_id="dynamic_path_composer",
                status="failed",
                output={"error": "动态组合失败，且无兜底技能可用"},
                error="No universal skill available for fallback",
            )

        available_skills = [s["skill_id"] for s in self._discover_skills()]
        request = SkillExecutionRequest(
            skill_id="system.universal",
            action="analyze",
            inputs={
                "message": user_input,
                "available_skills": available_skills,
            },
            config={"session_id": session_id},
            user_id="anonymous",
            app_instance_id="dynamic_fallback",
            workflow_id="dynamic_fallback",
            step_id="fallback",
        )
        try:
            return await self._universal.process(request)
        except Exception as exc:
            return SkillExecutionResult(
                skill_id="dynamic_path_composer",
                status="failed",
                output={"error": f"兜底也失败了: {exc}"},
                error=str(exc),
            )
