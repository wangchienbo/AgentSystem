from app.models.app_design import AppDesignResult, SubordinateSkillDesign
from app.services.design_blueprint_builder import DesignBlueprintBuilderService


def test_design_blueprint_builder_materializes_blueprint_from_design() -> None:
    builder = DesignBlueprintBuilderService()
    blueprint = builder.build_blueprint_from_design(
        AppDesignResult(
            app_name="Monitor App",
            app_slug="monitor-app",
            control_skill_name="monitor.control",
            control_skill_description="Control monitoring workflows",
            subordinate_skills=[
                SubordinateSkillDesign(
                    suggested_name="monitor.collect",
                    scope="metrics",
                    responsibility="Collect metrics",
                    priority="high",
                    reuse_existing=None,
                )
            ],
            reused_skills=["skill.existing"],
            new_skills=["monitor.collect"],
            decomposition_plan=["collect", "report"],
            governance_notes=["require approval for destructive actions"],
            design_notes="Monitoring app design",
        ),
        created_skill_ids=["monitor.collect"],
    )

    assert blueprint.id == "bp.designed.monitor-app"
    assert blueprint.name == "Monitor App"
    assert blueprint.required_skills == ["skill.existing", "monitor.collect"]
    assert blueprint.workflows[0].steps[0].ref == "monitor.control"
    assert blueprint.workflows[0].steps[1].ref == "monitor.collect"
    assert blueprint.runtime_policy.execution_mode == "service"


def test_design_blueprint_builder_uses_pipeline_shape_for_multi_skill_design() -> None:
    builder = DesignBlueprintBuilderService()
    blueprint = builder.build_blueprint_from_design(
        AppDesignResult(
            app_name="Ops App",
            app_slug="ops-app",
            control_skill_name="ops.control",
            control_skill_description="Control ops workflows",
            subordinate_skills=[
                SubordinateSkillDesign(suggested_name="ops.detect", scope="detect", responsibility="Detect"),
                SubordinateSkillDesign(suggested_name="ops.fix", scope="fix", responsibility="Fix"),
            ],
            design_notes="Ops pipeline",
        )
    )

    assert blueprint.app_shape == "pipeline_chain"
    assert blueprint.runtime_policy.execution_mode == "pipeline"
    assert len(blueprint.workflows[0].steps) == 3
