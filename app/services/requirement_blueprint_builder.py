from __future__ import annotations

import re

from app.models.app_blueprint import AppBlueprint, Role, Task, View, Workflow, WorkflowStep
from app.models.app_profile import AppRuntimeProfile
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
        app_shape = self._classify_app_shape(spec)
        runtime_profile = self._infer_runtime_profile(spec, app_shape=app_shape)
        execution_mode = "pipeline" if app_shape == "pipeline_chain" else "service"
        visible_views = ["requirement.overview", "requirement.run", "requirement.activity"]

        role_name = {
            "text_transform": "Requirement Text Agent",
            "structured_transform": "Requirement Data Agent",
            "pipeline_chain": "Requirement Pipeline Agent",
        }.get(app_shape, "Requirement Agent")
        task_name = {
            "text_transform": "Transform incoming text into normalized output",
            "structured_transform": "Transform structured payload into normalized output",
            "pipeline_chain": "Run the requirement-derived multi-step process",
        }.get(app_shape, "Handle requirement workflow")
        overview_title = {
            "text_transform": "Text Requirement Overview",
            "structured_transform": "Structured Requirement Overview",
            "pipeline_chain": "Pipeline Requirement Overview",
        }.get(app_shape, "Requirement Overview")
        run_title = {
            "text_transform": "Run Text Transformation",
            "structured_transform": "Run Structured Transformation",
            "pipeline_chain": "Run Pipeline Flow",
        }.get(app_shape, "Run Requirement Flow")
        activity_title = {
            "text_transform": "Text Transformation Activity",
            "structured_transform": "Structured Transformation Activity",
            "pipeline_chain": "Pipeline Activity",
        }.get(app_shape, "Requirement Activity")

        role_names = spec.roles or ["agent", "user"]
        roles = [
            Role(
                id=f"r{i+1}",
                name=role_name if i == 0 else name,
                type="agent" if i == 0 or name in {"处理人", "审批人", "客服", "管理员", "agent"} else "human",
                responsibilities=[task_name],
                permissions=spec.permissions,
                visible_views=visible_views,
                allowed_actions=["workflow.execute", "workflow.inspect"],
            )
            for i, name in enumerate(role_names)
        ]
        owner_role = roles[0].id if roles else "r1"
        inputs = spec.inputs or ["user_input"]
        outputs = spec.outputs or ["result"]
        task_outputs = {item: {"type": "string"} for item in outputs}
        if app_shape in {"text_transform", "structured_transform", "generic"}:
            task_outputs["normalized_response"] = {"type": "object"}
            task_outputs["model_invocation"] = {"type": "object"}
        task = Task(
            id="task.main",
            owner_role=owner_role,
            trigger="manual",
            inputs={item: {"type": "string"} for item in inputs} | {"app_shape": app_shape},
            outputs=task_outputs,
            success_condition=task_name,
            failure_policy=spec.failure_strategy or "retry_then_escalate",
        )
        steps = self._build_steps(spec, app_shape=app_shape)
        workflow = Workflow(
            id="wf.main",
            name=task_name,
            triggers=["manual"],
            steps=steps,
        )
        view = View(
            id="requirement.overview",
            name=overview_title,
            type="page",
            visible_roles=[role.id for role in roles],
            components=[
                {"kind": "summary", "title": spec.goal, "constraints": spec.constraints},
                {"kind": "runtime_profile", "profile": runtime_profile.model_dump(mode="json")},
            ],
        )
        run_view = View(
            id="requirement.run",
            name=run_title,
            type="form",
            visible_roles=[role.id for role in roles],
            actions=[{"id": "run-requirement", "kind": "workflow.execute", "workflow_id": "wf.main"}],
        )
        activity_view = View(
            id="requirement.activity",
            name=activity_title,
            type="dashboard",
            visible_roles=[role.id for role in roles],
            components=[
                {"kind": "workflow_status", "workflow_id": "wf.main"},
                {"kind": "outputs", "items": outputs},
            ],
        )
        runtime_policy = RuntimePolicy(
            execution_mode=execution_mode,
            activation="on_demand",
            restart_policy="on_failure",
            persistence_level="full" if execution_mode == "pipeline" else "standard",
            idle_strategy="suspend" if execution_mode == "pipeline" else "keep_alive",
        )
        return AppBlueprint(
            id=app_id,
            name=self._titleize(spec.goal or spec.raw_text),
            goal=spec.goal or spec.raw_text,
            app_shape=app_shape,
            roles=roles,
            tasks=[task],
            workflows=[workflow],
            views=[view, run_view, activity_view],
            required_modules=[],
            required_skills=[],
            runtime_policy=runtime_policy,
            runtime_profile=runtime_profile,
        )

    def _build_steps(self, spec: RequirementSpec, *, app_shape: str) -> list[WorkflowStep]:
        if app_shape == "pipeline_chain":
            return [
                WorkflowStep(
                    id="step.capture",
                    kind="human_task",
                    ref="capture.requirement",
                    config={"inputs": spec.inputs, "goal": spec.goal},
                ),
                WorkflowStep(
                    id="step.process",
                    kind="human_task",
                    ref="process.requirement",
                    config={"constraints": spec.constraints, "outputs": spec.outputs},
                ),
                WorkflowStep(
                    id="step.record",
                    kind="human_task",
                    ref="record.requirement",
                    config={"failure_strategy": spec.failure_strategy, "permissions": spec.permissions},
                ),
            ]
        if app_shape in {"text_transform", "structured_transform", "generic"}:
            return [
                WorkflowStep(
                    id="step.prompt.invoke",
                    kind="module",
                    ref="prompt.invoke",
                    config={
                        "query": spec.goal or spec.raw_text,
                        "limit": 3,
                        "strategy": "query_first",
                        "include_prompt_assembly": True,
                        "extra_payload": {
                            "metadata": {
                                "source": "requirement_blueprint_builder",
                                "app_shape": app_shape,
                            }
                        },
                    },
                )
            ]
        return [
            WorkflowStep(
                id="step.handle",
                kind="human_task",
                ref="handle.requirement",
                config={
                    "goal": spec.goal,
                    "inputs": spec.inputs,
                    "outputs": spec.outputs,
                    "constraints": spec.constraints,
                    "failure_strategy": spec.failure_strategy,
                },
            )
        ]

    def _classify_app_shape(self, spec: RequirementSpec) -> str:
        text = " ".join([
            spec.goal,
            " ".join(spec.inputs),
            " ".join(spec.outputs),
            " ".join(spec.constraints),
            " ".join(spec.extracted_keywords),
        ]).lower()
        if any(token in text for token in ["json", "结构化", "schema", "payload", "字段"]):
            return "structured_transform"
        if any(token in text for token in ["text", "文本", "slug", "标题", "规范化"]):
            return "text_transform"
        if len(spec.inputs) > 1 or len(spec.outputs) > 1 or any(token in text for token in ["workflow", "流程", "审批", "分配"]):
            return "pipeline_chain"
        return "generic"

    def _infer_runtime_profile(self, spec: RequirementSpec, *, app_shape: str) -> AppRuntimeProfile:
        network_required = any(item in {"联网"} for item in spec.constraints)
        ask_user = any(item in {"approval_flow"} for item in spec.permissions)
        return AppRuntimeProfile(
            runtime_intelligence_level="L0_deterministic",
            runtime_network_requirement="N2_required" if network_required else "N0_none",
            offline_capable=not network_required,
            direct_start_supported=app_shape != "pipeline_chain",
            invocation_posture="ask_user" if ask_user else "automatic",
            runtime_skills=[],
        )

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
        if not normalized:
            return "draft"
        return normalized[:48]

    def _titleize(self, value: str) -> str:
        compact = re.sub(r"\s+", " ", value.strip())
        return compact[:80] or "Requirement Draft"
