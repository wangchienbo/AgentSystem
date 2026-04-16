from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.app_context import AppSharedContext
from app.models.patch_proposal import PatchProposal, SelfRefinementRequest, SelfRefinementResult
from app.services.app_context_store import AppContextStore, AppContextStoreError
from app.services.app_registry import AppRegistryService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService
from app.services.model_client import ModelClientError
from app.services.model_config_loader import ModelConfigError
from app.services.model_self_refiner import ModelSelfRefiner


class SelfRefinementError(ValueError):
    pass


class SelfRefinementService:
    def __init__(
        self,
        experience_store: ExperienceStore,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
        model_self_refiner: ModelSelfRefiner | None = None,
        context_store: AppContextStore | None = None,
    ) -> None:
        self._experience_store = experience_store
        self._registry = registry
        self._lifecycle = lifecycle
        self._model_self_refiner = model_self_refiner
        self._context_store = context_store

    def propose(self, request: SelfRefinementRequest) -> SelfRefinementResult:
        experience = self._get_experience(request.experience_id)
        instance = self._lifecycle.get_instance(request.app_instance_id)
        blueprint = self._registry.get_blueprint(instance.blueprint_id)
        context = self._get_context(instance.id)
        refinement_evidence = self._build_refinement_evidence(experience.summary, context)

        proposals = self._build_fallback_proposals(instance.id, blueprint, refinement_evidence, context)
        if self._model_self_refiner and self._model_self_refiner.is_available():
            try:
                proposals = self._model_self_refiner.propose(instance.id, blueprint, experience)
            except (ModelConfigError, ModelClientError, KeyError, TypeError, ValueError):
                proposals = self._build_fallback_proposals(instance.id, blueprint, refinement_evidence, context)

        if not proposals:
            raise SelfRefinementError(f"No refinement proposal generated for {request.app_instance_id}")

        return SelfRefinementResult(
            app_instance_id=request.app_instance_id,
            experience_id=request.experience_id,
            context_entry_count=0 if context is None else len(context.entries),
            proposals=proposals,
        )

    def _get_experience(self, experience_id: str):
        for experience in self._experience_store.list_experiences():
            if experience.experience_id == experience_id:
                return experience
        raise SelfRefinementError(f"Experience not found: {experience_id}")

    def _get_context(self, app_instance_id: str) -> AppSharedContext | None:
        if self._context_store is None:
            return None
        try:
            return self._context_store.get_context(app_instance_id)
        except AppContextStoreError:
            return None

    def _build_refinement_evidence(self, summary: str, context: AppSharedContext | None) -> str:
        if context is None:
            return summary
        parts = [summary]
        if context.current_goal:
            parts.append(f"current_goal={context.current_goal}")
        if context.current_stage:
            parts.append(f"current_stage={context.current_stage}")
        for entry in context.entries[-5:]:
            parts.append(f"context:{entry.section}:{entry.key}")
        return " | ".join(parts)

    def _build_fallback_proposals(
        self,
        app_instance_id: str,
        blueprint: AppBlueprint,
        summary: str,
        context: AppSharedContext | None,
    ) -> list[PatchProposal]:
        proposals: list[PatchProposal] = []
        proposals.extend(self._build_runtime_policy_proposals(app_instance_id, blueprint, summary, context))
        proposals.extend(self._build_workflow_proposals(app_instance_id, blueprint, summary, context))
        return proposals

    def _build_runtime_policy_proposals(
        self,
        app_instance_id: str,
        blueprint: AppBlueprint,
        summary: str,
        context: AppSharedContext | None,
    ) -> list[PatchProposal]:
        proposals: list[PatchProposal] = []
        should_promote_keep_alive = (
            blueprint.runtime_policy.execution_mode == "service"
            and blueprint.runtime_policy.idle_strategy != "keep_alive"
        )
        if context is not None and context.status == "paused":
            should_promote_keep_alive = False

        if should_promote_keep_alive:
            proposals.append(
                PatchProposal(
                    proposal_id=f"proposal.runtime.{app_instance_id}.1",
                    app_instance_id=app_instance_id,
                    target_type="runtime_policy",
                    title="Promote service app idle strategy to keep_alive",
                    summary="服务型 app 在运行经验中表现出持续交互需求，建议保持更稳定的驻留策略。",
                    evidence=[summary],
                    expected_benefit="减少频繁唤醒带来的上下文抖动，提升长期运行 app 的连续性。",
                    risk_level="low",
                    auto_apply_allowed=True,
                    validation_checklist=[
                        "validate runtime policy schema",
                        "confirm no resource budget violation",
                        "ensure restart policy remains compatible",
                    ],
                    rollback_target="restore previous runtime_policy.idle_strategy",
                    patch={"idle_strategy": "keep_alive"},
                )
            )
        return proposals

    def _build_workflow_proposals(
        self,
        app_instance_id: str,
        blueprint: AppBlueprint,
        summary: str,
        context: AppSharedContext | None,
    ) -> list[PatchProposal]:
        proposals: list[PatchProposal] = []
        if blueprint.workflows:
            workflow = blueprint.workflows[0]
            patch_config = {"reason": "review checkpoint"}
            if context is not None and context.current_goal:
                patch_config["goal"] = context.current_goal
            proposals.append(
                PatchProposal(
                    proposal_id=f"proposal.workflow.{app_instance_id}.1",
                    app_instance_id=app_instance_id,
                    target_type="workflow",
                    title="Add review checkpoint to primary workflow",
                    summary="基于最近运行经验，建议在主 workflow 增加 review/checkpoint 步骤以降低重复失误。",
                    evidence=[summary, f"workflow:{workflow.id}"],
                    expected_benefit="提升 workflow 可恢复性，并使经验沉淀更容易回流到执行链路。",
                    risk_level="medium",
                    auto_apply_allowed=False,
                    validation_checklist=[
                        "check workflow schema compatibility",
                        "confirm added step does not break trigger semantics",
                        "run regression tests for affected workflow",
                    ],
                    rollback_target=f"restore workflow {workflow.id} to previous step list",
                    patch={
                        "workflow_id": workflow.id,
                        "append_step": {
                            "kind": "module",
                            "ref": "state.set",
                            "config": patch_config,
                        },
                    },
                )
            )
            if context is not None and any(entry.section == "open_loops" for entry in context.entries):
                proposals.append(
                    PatchProposal(
                        proposal_id=f"proposal.workflow.{app_instance_id}.2",
                        app_instance_id=app_instance_id,
                        target_type="workflow",
                        title="Add open-loop triage step to workflow",
                        summary="共享上下文中存在未闭环事项，建议增加专门的 open-loop triage 步骤。",
                        evidence=[summary, "context:open_loops"],
                        expected_benefit="减少长期堆积的未完成事项，提高流程闭环能力。",
                        risk_level="medium",
                        auto_apply_allowed=False,
                        validation_checklist=[
                            "verify open-loop schema mapping",
                            "confirm workflow can consume context entries",
                            "run regression tests for follow-up handling",
                        ],
                        rollback_target=f"restore workflow {workflow.id} to previous step list",
                        patch={
                            "workflow_id": workflow.id,
                            "append_step": {
                                "kind": "module",
                                "ref": "state.get",
                                "config": {"section": "open_loops", "reason": "triage pending context"},
                            },
                        },
                    )
                )
        return proposals
