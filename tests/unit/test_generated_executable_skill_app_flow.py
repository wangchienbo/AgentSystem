import json
from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.generated_skill import GeneratedSkillRequest
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.generated_skill_asset_store import GeneratedSkillAssetStore
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.schema_registry import SchemaRegistryService
from app.services.script_skill_generator import ScriptSkillGenerator
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService
from app.services.workflow_executor import WorkflowExecutorService


def test_generated_executable_skill_can_be_used_by_app_workflow(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "generated-app-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "generated-app-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)

    skill_control = SkillControlService()
    for skill_id in ["system.app_config", "system.context", "system.state", "system.audit"]:
        skill_control.register(
            SkillRegistryEntry(
                skill_id=skill_id,
                name=skill_id,
                active_version="1.0.0",
                versions=[SkillVersion(version="1.0.0", content=skill_id)],
                capability_profile=SkillCapabilityProfile(),
                runtime_adapter="callable",
            )
        )
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "generated_skills"))
    generator = ScriptSkillGenerator(asset_store=asset_store, skill_control=skill_control)
    generated_entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.generated.slugify",
            name="Generated Slugify",
            description="slugify text",
            template_type="slugify",
        )
    )
    manifest = generated_entry.manifest
    assert manifest is not None
    schema_registry = SchemaRegistryService()
    schema_registry.register(manifest.contract.input_schema_ref, json.loads(Path(manifest.contract.input_schema_ref).read_text()))
    schema_registry.register(manifest.contract.output_schema_ref, json.loads(Path(manifest.contract.output_schema_ref).read_text()))
    schema_registry.register(manifest.contract.error_schema_ref, json.loads(Path(manifest.contract.error_schema_ref).read_text()))

    skill_runtime = SkillRuntimeService(schema_registry=schema_registry)
    for entry in skill_control.list_skills():
        if entry.runtime_adapter == "executable":
            skill_runtime.register_handler(entry.skill_id, lambda request: None, entry=entry)

    resolver = AppProfileResolverService(skill_control=skill_control)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
        app_profile_resolver=resolver,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
        skill_runtime=skill_runtime,
        store=store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.generated.skill.app",
            name="Generated Skill App",
            goal="use generated skill",
            required_skills=[generated_entry.skill_id],
            required_modules=[],
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.generated.skill",
                    "name": "generated skill flow",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "step.slugify",
                            "kind": "skill",
                            "ref": generated_entry.skill_id,
                            "config": {"inputs": {"text": {"$from_inputs": "title"}}},
                        }
                    ],
                }
            ],
        )
    )

    install_result = installer.install_app("bp.generated.skill.app", user_id="generated-skill-user")
    result = executor.execute_primary_workflow(install_result.app_instance_id, inputs={"title": "Hello World"})

    assert result.status == "completed"
    assert result.steps[0].status == "completed"
    assert result.steps[0].output["slug"] == "hello-world"
