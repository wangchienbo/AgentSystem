"""Orchestrator that bridges the LLM-powered meta-app design layer with deterministic assembly/execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.app_meta_app import AppCreationFromMetaAppRequest
from app.models.meta_app import AppControlSkillResult
from app.models.meta_app_skill import MetaAppSkillRequest
from app.models.skill_blueprint import SkillBlueprint
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
    error: str = ""


class MetaAppCreationOrchestrator:
    """Orchestrates app creation through the meta-app LLM design layer.

    Flow:
    1. Call meta_app_bootstrap (LLM) to design app control structure
    2. Use the plan to guide skill assembly via skill_factory
    3. Return both the control plan and the generated blueprint

    This is the bridge between:
    - LLM layer (understanding, design, planning) ← system.meta_app
    - Deterministic layer (assembly, registration, execution) ← skill_factory
    """

    def __init__(
        self,
        *,
        meta_app_bootstrap: MetaAppBootstrapService,
        skill_factory: SkillFactoryService,
    ) -> None:
        self._meta_app = meta_app_bootstrap
        self._skill_factory = skill_factory

    def create_app_through_meta_app(self, request: AppCreationFromMetaAppRequest) -> AppCreationOrchestrationResult:
        """Step 1: Call LLM to design app control structure.
        Step 2: Use existing skill infrastructure to build the blueprint."""

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

        # Step 2: Deterministic assembly — build blueprint from existing skills
        # For now, route through the existing skill-based creation path.
        # The control plan provides structural guidance; skill_factory does the wiring.
        try:
            blueprint, app_result = self._skill_factory.build_blueprint_from_skills(
                self._build_app_from_skills_request(request, control_plan),
            )
            return AppCreationOrchestrationResult(
                app_name=request.app_name,
                control_plan=control_plan,
                blueprint=blueprint,
                created_skill_ids=app_result.skill_ids if hasattr(app_result, "skill_ids") else [],
            )
        except (SkillFactoryError, ValueError) as exc:
            # Return partial result: we still have the control plan even if assembly failed
            return AppCreationOrchestrationResult(
                app_name=request.app_name,
                control_plan=control_plan,
                error=str(exc),
            )

    def _build_app_from_skills_request(self, request: AppCreationFromMetaAppRequest, control_plan: AppControlSkillResult) -> Any:
        """Translate meta-app output into skill_factory input.

        This is where the LLM design meets deterministic assembly.
        For the first integration, we pass through to the existing path
        while recording the meta-app control plan alongside it.
        """
        from app.models.app_blueprint import AppFromSkillsRequest

        # Use the user's skill selection or fall back to all available skills
        # In a full implementation, the LLM would select specific skills
        return AppFromSkillsRequest(
            app_name=request.app_name,
            goal=request.goal,
            trigger=request.trigger,
            workflow_inputs=request.workflow_inputs,
        )
