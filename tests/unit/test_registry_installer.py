from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def build_blueprint(execution_mode: str = "service") -> AppBlueprint:
    return AppBlueprint(
        id="bp.test.registry",
        name="Registry Test App",
        goal="verify registry and installer",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.test", "name": "test", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=[],
        runtime_policy={
            "execution_mode": execution_mode,
            "activation": "on_demand",
            "restart_policy": "on_failure",
            "persistence_level": "standard",
            "idle_strategy": "suspend",
        },
    )


def test_registry_registers_blueprint() -> None:
    store = RuntimeStateStore(base_dir="data/test-registry")
    registry = AppRegistryService(store=store)

    entry = registry.register_blueprint(build_blueprint(), description="registry test")

    assert entry.blueprint_id == "bp.test.registry"
    assert registry.get_blueprint("bp.test.registry").runtime_policy.execution_mode == "service"


def test_installer_creates_instance_with_runtime_policy() -> None:
    store = RuntimeStateStore(base_dir="data/test-installer")
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime)
    registry.register_blueprint(build_blueprint(execution_mode="pipeline"))

    result = installer.install_app("bp.test.registry", user_id="user.install")
    instance = lifecycle.get_instance(result.app_instance_id)

    assert result.status == "installed"
    assert instance.execution_mode == "pipeline"
    assert instance.runtime_policy.execution_mode == "pipeline"


def test_registry_and_install_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.api.registry",
            "name": "API Registry App",
            "goal": "registry api flow",
            "roles": [],
            "tasks": [],
            "workflows": [{"id": "wf.api", "name": "api flow", "triggers": ["manual"], "steps": []}],
            "views": [],
            "required_modules": ["state.get"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive"
            }
        },
    )
    assert register_response.status_code == 200

    list_response = client.get("/registry/apps")
    assert list_response.status_code == 200
    assert any(item["blueprint_id"] == "bp.api.registry" for item in list_response.json())

    install_response = client.post(
        "/registry/apps/bp.api.registry/install",
        json={"user_id": "api-user"},
    )
    assert install_response.status_code == 200
    assert install_response.json()["execution_mode"] == "service"
