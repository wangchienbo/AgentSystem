from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import PatchProposal, SelfRefinementRequest, SelfRefinementResult
from app.services.app_registry import AppRegistryService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService


class SelfRefinementError(ValueError):
    pass


class SelfRefinementService:
    def __init__(
        self,
        experience_store: ExperienceStore,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
    ) -> None:
        self._experience_store = experience_store
        self._registry = registry
        self._lifecycle = lifecycle

    def propose(self, request: SelfRefinementRequest) -> SelfRefinementResult:
        experience = self._get_experience(request.experience_id)
        instance = self._lifecycle.get_instance(request.app_instance_id)
        blueprint = self._registry.get_blueprint(instance.blueprint_id)

        proposals: list[PatchProposal] = []
        proposals.extend(self._build_runtime_policy_proposals(instance.id, blueprint, experience.summary))
        proposals.extend(self._build_workflow_proposals(instance.id, blueprint, experience.summary))

        if not proposals:
            raise SelfRefinementError(f"No refinement proposal generated for {request.app_instance_id}")

        return SelfRefinementResult(
            app_instance_id=request.app_instance_id,
            experience_id=request.experience_id,
            proposals=proposals,
        )

    def _get_experience(self, experience_id: str):
        for experience in self._experience_store.list_experiences():
            if experience.experience_id == experience_id:
                return experience
        raise SelfRefinementError(f"Experience not found: {experience_id}")

    def _build_runtime_policy_proposals(self, app_instance_id: str, blueprint: AppBlueprint, summary: str) -> list[PatchProposal]:
        proposals: list[PatchProposal] = []
        if blueprint.runtime_policy.execution_mode == "service" and blueprint.runtime_policy.idle_strategy != "keep_alive":
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

    def _build_workflow_proposals(self, app_instance_id: str, blueprint: AppBlueprint, summary: str) -> list[PatchProposal]:
        proposals: list[PatchProposal] = []
        if blueprint.workflows:
            workflow = blueprint.workflows[0]
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
                            "config": {"reason": "review checkpoint"},
                        },
                    },
                )
            )
        return proposals
