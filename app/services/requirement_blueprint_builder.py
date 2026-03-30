from __future__ import annotations

import re

from app.models.app_blueprint import AppBlueprint, Role, Task, View, Workflow, WorkflowStep
from app.models.runtime_policy import RuntimePolicy
from app.models.requirement_spec import RequirementSpec


class RequirementBlueprintBuilderError(ValueError):
    pass


class RequirementBlueprintBuilderService:
    def build_blueprint_draft(self, spec: RequirementSpec) -> AppBlueprint:
        if spec.readiness != "ready":
            raise RequirementBlueprintBuilderError(
                f"Requirement is not ready for blueprint generation: {spec.readiness}"
            )
        if spec.requirement_type not in {"app", "hybrid"}:
            raise RequirementBlueprintBuilderError(
                f"Blueprint draft currently supports app/hybrid requirements only: {spec.requirement_type}"
            )

        slug = self._slugify(spec.goal or spec.raw_text)
        app_id = f"bp.requirement.{slug}"
        role_names = spec.roles or ["requester", "agent"]
        roles = [
            Role(
                id=f"r{i+1}",
                name=name,
                type="agent" if name in {"agent", "处理人", "审批人", "客服", "管理员"} else "human",
                responsibilities=[f"support {spec.goal[:60]}"],
                permissions=spec.permissions,
            )
            for i, name in enumerate(role_names)
        ]
        owner_role = roles[0].id if roles else "r1"
        task = Task(
            id="task.main",
            owner_role=owner_role,
            trigger="manual",
            inputs={item: {"type": "string"} for item in (spec.inputs or ["user_input"])},
            outputs={item: {"type": "string"} for item in (spec.outputs or ["result"])},
            success_condition="request handled successfully",
            failure_policy=spec.failure_strategy or "retry_then_escalate",
        )
        workflow = Workflow(
            id="wf.main",
            name="requirement-derived workflow",
            triggers=["manual"],
            steps=[
                WorkflowStep(
                    id="step.capture",
                    kind="human_task",
                    ref="capture.requirement",
                    config={"goal": spec.goal, "constraints": spec.constraints},
                ),
                WorkflowStep(
                    id="step.execute",
                    kind="human_task",
                    ref="execute.requirement",
                    config={"outputs": spec.outputs, "failure_strategy": spec.failure_strategy},
                ),
            ],
        )
        view = View(
            id="view.main",
            name="Requirement Overview",
            type="detail",
            visible_roles=[role.id for role in roles],
            components=[
                {"type": "summary", "goal": spec.goal, "constraints": spec.constraints},
                {"type": "list", "items": spec.outputs or ["result"]},
            ],
        )
        runtime_policy = RuntimePolicy(execution_mode="service" if spec.requirement_type == "app" else "pipeline")
        return AppBlueprint(
            id=app_id,
            name=self._titleize(spec.goal or spec.raw_text),
            goal=spec.goal or spec.raw_text,
            app_shape="generic",
            roles=roles,
            tasks=[task],
            workflows=[workflow],
            views=[view],
            required_modules=[],
            required_skills=[],
            runtime_policy=runtime_policy,
        )

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
        if not normalized:
            return "draft"
        return normalized[:48]

    def _titleize(self, value: str) -> str:
        compact = re.sub(r"\s+", " ", value.strip())
        return compact[:80] or "Requirement Draft"
