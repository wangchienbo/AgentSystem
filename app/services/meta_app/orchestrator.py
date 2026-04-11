"""Orchestrator that bridges the LLM-powered meta-app design layer with deterministic assembly/execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.app_meta_app import AppCreationFromMetaAppRequest
from app.models.meta_app import AppControlSkillResult
from app.models.meta_app_skill import MetaAppSkillRequest
from app.models.skill_creation import (
    AppFromSkillsRequest,
    SkillCreationRequest,
    SkillSchemaDefinition,
)
from app.services.meta_app.bootstrap import MetaAppBootstrapService
from app.services.skill_factory import SkillFactoryService, SkillFactoryError


class MetaAppOrchestratorError(ValueError):
    pass


@dataclass
class AppCreationOrchestrationResult:
    """End-to-end result from meta-app design through blueprint generation."""
    app_name: str
    control_plan: AppControlSkillResult
    blueprint: AppBlueprint | None = None
    created_skill_ids: list[str] = field(default_factory=list)
    installed_app: AppInstance | None = None
    error: str = ""


class MetaAppCreationOrchestrator:
    """Orchestrates app creation through the meta-app LLM design layer.

    Flow:
    1. Call meta_app_bootstrap (LLM) to design app control structure
    2. Create the suggested subordinate skills via skill_factory
    3. Build blueprint from the created skills
    4. Optionally install the app
    """

    def __init__(
        self,
        *,
        meta_app_bootstrap: MetaAppBootstrapService,
        skill_factory: SkillFactoryService,
    ) -> None:
        self._meta_app = meta_app_bootstrap
        self._skill_factory = skill_factory

    def create_app_through_meta_app(
        self,
        request: AppCreationFromMetaAppRequest,
    ) -> AppCreationOrchestrationResult:
        """Full flow: LLM design → skill creation → blueprint assembly."""

        # Step 1: LLM design layer — produce app control plan
        meta_request = MetaAppSkillRequest(
            app_name=request.app_name,
            goal=request.goal,
            app_kind=request.app_kind,
            complexity=request.complexity,
            scope=request.scope,
            context={"user_description": request.context} if request.context else {},
        )
        control_plan = self._meta_app.bootstrap(meta_request)

        # Step 2: Create subordinate skills from the LLM plan
        created_skill_ids = self._create_subordinate_skills(
            control_plan, request.app_name, request.goal,
        )

        # Step 3: Build blueprint from created skills
        blueprint: AppBlueprint | None = None
        try:
            if created_skill_ids:
                blueprint_id = f"bp-{control_plan.app_slug}"
                bp_request = AppFromSkillsRequest(
                    blueprint_id=blueprint_id,
                    name=request.app_name,
                    goal=request.goal,
                    skill_ids=created_skill_ids,
                    step_inputs=request.workflow_inputs,
                )
                blueprint, _app_result = self._skill_factory.build_blueprint_from_skills(bp_request)
        except (SkillFactoryError, ValueError) as exc:
            return AppCreationOrchestrationResult(
                app_name=request.app_name,
                control_plan=control_plan,
                created_skill_ids=created_skill_ids,
                error=f"Blueprint assembly failed: {exc}",
            )

        return AppCreationOrchestrationResult(
            app_name=request.app_name,
            control_plan=control_plan,
            blueprint=blueprint,
            created_skill_ids=created_skill_ids,
        )

    def _create_subordinate_skills(
        self,
        control_plan: AppControlSkillResult,
        app_name: str,
        app_goal: str,
    ) -> list[str]:
        """Create skill stubs for each suggested subordinate in the control plan."""
        created: list[str] = []
        for suggestion in control_plan.subordinate_suggestions:
            skill_id = suggestion.suggested_name
            # Skip if already exists
            try:
                self._skill_factory._skill_control.get_skill(skill_id)
                created.append(skill_id)
                continue
            except Exception:
                pass

            # Generate stub handler code
            handler_code = self._generate_skill_stub_code(
                skill_id=skill_id,
                name=suggestion.responsibility,
                scope=suggestion.scope,
                app_name=app_name,
                app_goal=app_goal,
            )

            # Write handler to disk
            import os
            skills_dir = f"skills/generated/{skill_id}"
            os.makedirs(skills_dir, exist_ok=True)
            handler_path = f"{skills_dir}/handler.py"
            with open(handler_path, "w") as f:
                f.write(handler_code)

            # Create the skill in the registry
            creation_request = SkillCreationRequest(
                skill_id=skill_id,
                name=suggestion.responsibility,
                description=f"Subordinate skill for {app_name}: {suggestion.responsibility}",
                adapter_kind="script",
                handler_entry=handler_path,
                tags=[control_plan.app_slug, suggestion.priority, "generated-by-meta-app"],
                schemas=SkillSchemaDefinition(
                    input={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                    output={"type": "object", "properties": {"result": {"type": "string"}, "skill_id": {"type": "string"}}},
                    error={"type": "object", "properties": {"message": {"type": "string"}}},
                ),
            )
            self._skill_factory.create_skill(creation_request)
            created.append(skill_id)

        return created

    @staticmethod
    def _generate_skill_stub_code(
        skill_id: str,
        name: str,
        scope: str,
        app_name: str,
        app_goal: str,
    ) -> str:
        """Generate a minimal Python handler for a subordinate skill stub."""
        return (
            f'"""Auto-generated skill stub: {skill_id}\n'
            f"App: {app_name} | Goal: {app_goal}\n"
            f"Purpose: {name}\n"
            f"Scope: {scope}\n"
            'This is a placeholder — refine the handler for production use.\n'
            '"""\n\n'
            f"def handle(request: dict) -> dict:\n"
            f'    text = request.get("text", "")\n'
            f'    return {{"skill_id": "{skill_id}", "result": f"Processed: {{text}}", "status": "stub"}}\n'
        )
