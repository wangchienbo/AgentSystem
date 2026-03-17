from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.interaction import AppCatalogEntry, UserCommand
from app.services.app_catalog import AppCatalogService
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.app_context_store import AppContextStore
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.requirement_router import RequirementRouter
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def test_interaction_gateway_opens_service_app() -> None:
    store = RuntimeStateStore(base_dir="data/test-runtime-gateway-service")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-runtime-gateway-service-ns", store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    catalog = AppCatalogService()
    registry.register_blueprint(
        AppBlueprint(
            id="bp.assistant",
            name="Assistant",
            goal="long running assistant",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.assistant", "name": "assistant", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service"},
        )
    )
    catalog.register(
        AppCatalogEntry(
            app_id="app.assistant",
            name="Assistant",
            description="long running assistant",
            execution_mode="service",
            trigger_phrases=["打开助手"],
            blueprint_id="bp.assistant",
        )
    )
    gateway = InteractionGateway(catalog, RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u1", text="请帮我打开助手"))

    assert decision.action == "open_app"
    assert decision.execution_mode == "service"
    assert decision.app_instance_id == "app.assistant:u1"
    assert lifecycle.get_instance("app.assistant:u1").status == "running"
    context = context_store.get_context("app.assistant:u1")
    assert context.current_stage == "running"
    assert context.current_goal == "请帮我打开助手"
    assert context.entries[-1].key == "latest-user-command"


def test_interaction_gateway_runs_pipeline_app() -> None:
    store = RuntimeStateStore(base_dir="data/test-runtime-gateway-pipeline")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-runtime-gateway-pipeline-ns", store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    catalog = AppCatalogService()
    registry.register_blueprint(
        AppBlueprint(
            id="bp.pipeline",
            name="Pipeline",
            goal="one-shot pipeline",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.pipeline", "name": "pipeline", "triggers": ["manual"], "steps": []}],
            required_modules=["state.set"],
            required_skills=[],
            runtime_policy={"execution_mode": "pipeline", "restart_policy": "never", "idle_strategy": "stop"},
        )
    )
    catalog.register(
        AppCatalogEntry(
            app_id="app.pipeline",
            name="Pipeline",
            description="one-shot pipeline",
            execution_mode="pipeline",
            trigger_phrases=["执行流水线"],
            blueprint_id="bp.pipeline",
        )
    )
    gateway = InteractionGateway(catalog, RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u2", text="现在执行流水线"))

    assert decision.action == "run_pipeline"
    assert decision.execution_mode == "pipeline"
    assert decision.app_instance_id == "app.pipeline:u2:run"
    assert lifecycle.get_instance("app.pipeline:u2:run").status == "stopped"
    assert decision.pending_tasks == ["现在执行流水线"]
    context = context_store.get_context("app.pipeline:u2:run")
    assert context.current_stage == "stopped"
    assert context.status == "archived"
    assert context.entries[-1].key == "latest-pipeline-run"


def test_interaction_gateway_clarifies_unknown_command() -> None:
    store = RuntimeStateStore(base_dir="data/test-runtime-gateway-clarify")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-runtime-gateway-clarify-ns", store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    gateway = InteractionGateway(AppCatalogService(), RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u3", text="帮我搞个抽象战略平台"))

    assert decision.action == "clarify"
    assert "未命中已登记 app" in decision.message


def test_runtime_state_store_persists_files() -> None:
    base_dir = "data/test-runtime-persistence"
    store = RuntimeStateStore(base_dir=base_dir)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    runtime.register_instance(
        AppInstance(
            id="app.persist.001",
            blueprint_id="bp.persist.001",
            owner_user_id="user.persist",
            status="installed",
            data_namespace="users/user.persist/apps/app.persist.001",
        )
    )
    runtime.start("app.persist.001")
    runtime.enqueue_task("app.persist.001", "persist task")

    assert Path(base_dir, "app_instances.json").exists()
    assert Path(base_dir, "runtime_leases.json").exists()
    assert Path(base_dir, "runtime_pending_tasks.json").exists()


def test_interaction_api_and_persistence_snapshot() -> None:
    catalog_response = client.get("/catalog/apps")
    assert catalog_response.status_code == 200
    assert len(catalog_response.json()) >= 2

    service_response = client.post(
        "/interaction/command",
        json={"user_id": "qq-user", "text": "打开助手"},
    )
    assert service_response.status_code == 200
    assert service_response.json()["action"] == "open_app"

    pipeline_response = client.post(
        "/interaction/command",
        json={"user_id": "qq-user", "text": "执行流水线"},
    )
    assert pipeline_response.status_code == 200
    assert pipeline_response.json()["action"] == "run_pipeline"

    persistence_response = client.get("/runtime/persistence")
    assert persistence_response.status_code == 200
    assert "app_instances" in persistence_response.json()
