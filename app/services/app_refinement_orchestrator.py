from __future__ import annotations

from app.models.app_refinement import (
    SuggestedSkillRefinementClosureRequest,
    SuggestedSkillRefinementClosureResult,
)
from app.services.app_installer import AppInstallerService
from app.services.app_refinement import AppRefinementService
from app.services.app_registry import AppRegistryService
from app.models.skill_diagnostics import SkillDiagnostic
from app.services.workflow_executor import WorkflowExecutorService


class AppRefinementOrchestratorError(ValueError):
    pass


class AppRefinementOrchestratorService:
    def __init__(
        self,
        *,
        app_refinement: AppRefinementService,
        app_registry: AppRegistryService,
        app_installer: AppInstallerService,
        workflow_executor: WorkflowExecutorService,
    ) -> None:
        self._app_refinement = app_refinement
        self._app_registry = app_registry
        self._app_installer = app_installer
        self._workflow_executor = workflow_executor

    def refine_closure(self, request: SuggestedSkillRefinementClosureRequest) -> SuggestedSkillRefinementClosureResult:
        refinement = self._app_refinement.build_app_from_suggested_skills(request)
        entry = self._app_registry.register_blueprint(refinement.blueprint)

        release = self._app_registry.add_release(
            refinement.blueprint.id,
            version=request.version,
            note=request.note,
            reviewer=request.reviewer,
            activate_immediately=False,
        )
        release_entry = release.model_dump(mode="json")
        release_entry["candidate_version"] = request.version
        compare_summary = self._build_compare_summary(refinement.blueprint)

        install_result = None
        execution_result = None
        diagnostics: list[dict] = []
        if request.install or request.run:
            if not request.user_id:
                raise AppRefinementOrchestratorError("user_id is required when install or run is requested")
            install = self._app_installer.install_app(refinement.blueprint.id, user_id=request.user_id)
            install_result = install.model_dump(mode="json")
            if request.run:
                execution = self._workflow_executor.execute_workflow(
                    app_instance_id=install.app_instance_id,
                    workflow_id=refinement.app_result.workflow_id,
                    trigger=request.trigger,
                    inputs=request.workflow_inputs,
                )
                execution_result = execution.model_dump(mode="json")
                if execution.status != "completed":
                    diagnostics.append(
                        SkillDiagnostic(
                            stage="execute",
                            kind="execution_error",
                            message="Refined app candidate execution did not complete successfully",
                            retryable=execution.status in {"partial", "paused_for_human", "waiting_for_event"},
                            hint="Inspect unresolved/failed step ids and retry or resume with corrected inputs.",
                            details={
                                "workflow_id": refinement.app_result.workflow_id,
                                "status": execution.status,
                                "failed_step_ids": list(execution.failed_step_ids),
                                "unresolved_step_ids": list(execution.unresolved_step_ids),
                            },
                            suggested_retry_request={
                                "blueprint_id": refinement.blueprint.id,
                                "workflow_id": refinement.app_result.workflow_id,
                                "workflow_inputs": request.workflow_inputs,
                            },
                        ).model_dump(mode="json")
                    )

        return SuggestedSkillRefinementClosureResult(
            blueprint=refinement.blueprint,
            app_result=refinement.app_result,
            created_skills=refinement.created_skills,
            reused_skill_ids=refinement.reused_skill_ids,
            selected_blueprints=refinement.selected_blueprints,
            materialized_skill_ids=[item.skill_id for item in refinement.created_skills],
            release_entry=release_entry,
            install_result=install_result,
            execution_result=execution_result,
            compare_summary=compare_summary,
            diagnostics=diagnostics,
        )

    def _build_compare_summary(self, blueprint) -> dict:
        active = self._app_registry.get_blueprint(blueprint.id)
        runtime_profile = active.runtime_profile if isinstance(active.runtime_profile, dict) else {}
        runtime_policy = active.runtime_policy if isinstance(active.runtime_policy, dict) else {}
        return {
            "blueprint_id": blueprint.id,
            "app_shape": blueprint.app_shape,
            "required_skills": list(blueprint.required_skills),
            "workflow_count": len(blueprint.workflows),
            "view_count": len(blueprint.views),
            "runtime_profile": runtime_profile,
            "runtime_policy": runtime_policy,
        }
