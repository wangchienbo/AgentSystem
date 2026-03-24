from app.models.skill_blueprint import SkillBlueprint
from app.services.app_data_store import AppDataStore
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService


def test_skill_factory_builds_creation_defaults_from_blueprint_safety_profile(tmp_path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "blueprint-safety-defaults"))
    factory = SkillFactoryService(
        skill_control=SkillControlService(),
        skill_runtime=SkillRuntimeService(store=store),
        schema_registry=SchemaRegistryService(),
        generated_assets=GeneratedSkillAssetStore(AppDataStore(base_dir=str(tmp_path / "ns"), store=store)),
    )

    blueprint = SkillBlueprint(
        skill_id="skill.safe.blueprint",
        name="Safe Blueprint",
        goal="produce a low-risk generated skill",
        inputs=["context"],
        outputs=["result"],
        steps=["do safe local deterministic work"],
        safety_profile={
            "preferred_risk_level": "R0_safe_read",
            "prefer_local_only": True,
            "prefer_deterministic": True,
            "allow_network": False,
            "allow_shell": False,
            "allow_filesystem_write": False,
        },
    )

    defaults = factory.build_creation_defaults_from_blueprint(blueprint)

    assert defaults["capability_profile"].risk_level == "R0_safe_read"
    assert defaults["capability_profile"].network_requirement == "N0_none"
    assert defaults["capability_profile"].execution_locality == "local"
    assert defaults["manifest_risk"]["allow_network"] is False
    assert defaults["manifest_risk"]["allow_shell"] is False
    assert defaults["manifest_risk"]["allow_filesystem_write"] is False
