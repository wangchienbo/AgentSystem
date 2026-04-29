from __future__ import annotations

import re

from app.models.app_blueprint import AppBlueprint, Role, Task, View, Workflow, WorkflowStep
from app.models.app_design import AppDesignResult
from app.models.app_profile import AppRuntimeProfile
from app.models.runtime_policy import RuntimePolicy


class DesignBlueprintBuilderError(ValueError):
    pass


class DesignBlueprintBuilderService:
    """Materialize an AppBlueprint from an AppDesignResult.

    This is a deterministic bridge from the app-design stage into the
    blueprint/install stage, so the confirm step can close the loop without
    depending on requirement-draft builders.
    """

    def build_blueprint_from_design(
        self,
        design: AppDesignResult,
        *,
        created_skill_ids: list[str] | None = None,
    ) -> AppBlueprint:
        if not design.app_name or not design.app_slug:
            raise DesignBlueprintBuilderError("design must include app_name and app_slug")

        created_skill_ids = list(created_skill_ids or [])
        required_skills = list(dict.fromkeys([*design.reused_skills, *created_skill_ids]))
        blueprint_id = f"bp.designed.{self._slugify(design.app_slug)}"
        app_shape = "pipeline_chain" if len(design.subordinate_skills) > 1 else "service"
        normalized_shape = "pipeline_chain" if app_shape == "pipeline_chain" else "generic"

        roles = [
            Role(
                id="r.system",
                name=design.control_skill_name or f"{design.app_name} Control",
                type="agent",
                responsibilities=[
                    design.control_skill_description or "Control app lifecycle and coordination",
                    *design.governance_notes,
                ],
                permissions=["workflow.execute", "workflow.inspect"],
                visible_views=["app.overview", "app.run", "app.activity"],
                allowed_actions=["workflow.execute", "workflow.inspect"],
            )
        ]

        workflow_steps = [
            WorkflowStep(
                id="step.control",
                kind="skill",
                ref=design.control_skill_name or "app.control",
                config={
                    "design_notes": design.design_notes,
                    "decomposition_plan": design.decomposition_plan,
                },
            )
        ]
        for index, skill in enumerate(design.subordinate_skills, start=1):
            workflow_steps.append(
                WorkflowStep(
                    id=f"step.skill.{index}",
                    kind="skill",
                    ref=skill.reuse_existing or skill.suggested_name,
                    config={
                        "scope": skill.scope,
                        "responsibility": skill.responsibility,
                        "priority": skill.priority,
                    },
                )
            )

        workflow = Workflow(
            id="wf.main",
            name=f"{design.app_name} main workflow",
            triggers=["manual"],
            steps=workflow_steps,
        )

        task = Task(
            id="task.main",
            owner_role="r.system",
            trigger="manual",
            inputs={"user_input": {"type": "string"}},
            outputs={"result": {"type": "object"}},
            success_condition=design.design_notes or f"{design.app_name} workflow completes",
            failure_policy="retry_then_escalate",
        )

        views = [
            View(
                id="app.overview",
                name=f"{design.app_name} Overview",
                type="page",
                visible_roles=["r.system"],
                components=[
                    {"kind": "summary", "title": design.app_name, "notes": design.design_notes},
                    {"kind": "decomposition_plan", "items": design.decomposition_plan},
                ],
            ),
            View(
                id="app.run",
                name=f"Run {design.app_name}",
                type="form",
                visible_roles=["r.system"],
                actions=[{"id": "run-app", "kind": "workflow.execute", "workflow_id": "wf.main"}],
            ),
            View(
                id="app.activity",
                name=f"{design.app_name} Activity",
                type="dashboard",
                visible_roles=["r.system"],
                components=[{"kind": "workflow_status", "workflow_id": "wf.main"}],
            ),
        ]

        runtime_policy = RuntimePolicy(
            execution_mode="pipeline" if normalized_shape == "pipeline_chain" else "service",
            activation="on_demand",
            restart_policy="on_failure",
            persistence_level="standard",
            idle_strategy="keep_alive",
        )
        runtime_profile = AppRuntimeProfile(
            runtime_intelligence_level="L1_llm",
            runtime_network_requirement="N0_none",
            offline_capable=True,
            direct_start_supported=True,
            invocation_posture="ask_user",
            runtime_skills=required_skills,
        )

        return AppBlueprint(
            id=blueprint_id,
            name=design.app_name,
            goal=design.design_notes or design.app_name,
            app_shape=normalized_shape,
            roles=roles,
            tasks=[task],
            workflows=[workflow],
            views=views,
            required_modules=[],
            required_skills=required_skills,
            runtime_policy=runtime_policy,
            runtime_profile=runtime_profile,
        )

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
        return normalized[:48] or "app"
