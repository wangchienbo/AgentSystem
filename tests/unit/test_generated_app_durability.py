from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.skill_creation import AppFromSkillsRequest, SkillCreationRequest, SkillSchemaDefinition
from app.models.skill_runtime import SkillExecutionRequest
from app.services.app_data_store import AppDataStore
from app.services.app_registry import AppRegistryService
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.event_bus import EventBusService
from app.services.scheduler import SchedulerService
from app.services.app_context_store import AppContextStore


FIXTURE_PATH = Path("/root/project/AgentSystem/tests/fixtures/script_slugify_skill.py")


def test_generated_app_can_run_after_runtime_rebuild(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "app-data"), store=store)
    schema_registry = SchemaRegistryService()
    skill_control = SkillControlService()
    skill_runtime = SkillRuntimeService(store=store, schema_registry=schema_registry)
    generated_assets = GeneratedSkillAssetStore(data_store)
    factory = SkillFactoryService(
        skill_control=skill_control,
        skill_runtime=skill_runtime,
        schema_registry=schema_registry,
        generated_assets=generated_assets,
    )
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime_host)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime_host, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
        skill_runtime=skill_runtime,
        store=store,
    )

    request = SkillCreationRequest(
        skill_id="skill.text.slugify.generated.app",
        name="Generated App Slugify Skill",
        description="used by a generated durable app",
        adapter_kind="script",
        command=["python3", str(FIXTURE_PATH)],
        schemas=SkillSchemaDefinition(
            input={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            output={
                "type": "object",
                "properties": {
                    "source_text": {"type": "string"},
                    "slug": {"type": "string"},
                    "length": {"type": "integer"},
                    "adapter": {"type": "string"},
                },
                "required": ["source_text", "slug", "length", "adapter"],
                "additionalProperties": True,
            },
            error={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        ),
        smoke_test_inputs={"text": "Generated App Seed"},
    )
    created = factory.create_skill(request)
    assert created.smoke_test.status == "completed"

    blueprint, result = factory.build_blueprint_from_skills(
        AppFromSkillsRequest(
            blueprint_id="bp.generated.app.durable",
            name="Generated Durable App",
            goal="run after runtime rebuild",
            skill_ids=["skill.text.slugify.generated.app"],
            workflow_id="wf.generated.app.durable",
            step_inputs={"skill.1": {"text": "A Durable Generated App"}},
        )
    )
    assert result.created_steps == ["skill.1"]
    registry.register_blueprint(blueprint if isinstance(blueprint, AppBlueprint) else AppBlueprint.model_validate(blueprint))

    rebuilt_schema_registry = SchemaRegistryService()
    rebuilt_skill_control = SkillControlService()
    rebuilt_skill_runtime = SkillRuntimeService(store=store, schema_registry=rebuilt_schema_registry)
    rebuilt_factory = SkillFactoryService(
        skill_control=rebuilt_skill_control,
        skill_runtime=rebuilt_skill_runtime,
        schema_registry=rebuilt_schema_registry,
        generated_assets=GeneratedSkillAssetStore(data_store),
    )
    restored = rebuilt_factory.reload_generated_skills()
    assert restored >= 1

    rebuilt_lifecycle = AppLifecycleService(store=store)
    rebuilt_runtime_host = AppRuntimeHostService(lifecycle=rebuilt_lifecycle, store=store)
    rebuilt_context_store = AppContextStore(lifecycle=rebuilt_lifecycle, store=store, runtime_host=rebuilt_runtime_host)
    rebuilt_scheduler = SchedulerService(lifecycle=rebuilt_lifecycle, runtime_host=rebuilt_runtime_host, store=store)
    rebuilt_event_bus = EventBusService(scheduler=rebuilt_scheduler, store=store)
    rebuilt_registry = AppRegistryService(store=store)
    rebuilt_executor = WorkflowExecutorService(
        registry=rebuilt_registry,
        lifecycle=rebuilt_lifecycle,
        data_store=data_store,
        event_bus=rebuilt_event_bus,
        context_store=rebuilt_context_store,
        skill_runtime=rebuilt_skill_runtime,
        store=store,
    )
    rebuilt_registry.register_blueprint(blueprint if isinstance(blueprint, AppBlueprint) else AppBlueprint.model_validate(blueprint))

    rebuilt_runtime_host.register_instance(
        AppInstance(
            id="bp.generated.app.durable:user-1",
            blueprint_id="bp.generated.app.durable",
            owner_user_id="user-1",
            status="installed",
            data_namespace="users/user-1/apps/bp.generated.app.durable:user-1",
            execution_mode="service",
        )
    )
    data_store.ensure_app_namespaces("bp.generated.app.durable:user-1", "user-1")

    execution = rebuilt_executor.execute_workflow(
        app_instance_id="bp.generated.app.durable:user-1",
        workflow_id="wf.generated.app.durable",
        trigger="manual",
        inputs={},
    )
    assert execution.status == "completed"
    assert execution.steps[0].output["slug"] == "a-durable-generated-app"
    assert execution.steps[0].output["adapter"] == "script"
