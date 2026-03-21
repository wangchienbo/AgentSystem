from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def build_blueprint() -> AppBlueprint:
    return AppBlueprint(
        id="bp.data.store",
        name="Data Store App",
        goal="verify namespace separation",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.data", "name": "data flow", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=[],
    )


def test_app_data_store_creates_namespaces(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "app-data-store-root"))
    data_store = AppDataStore(base_dir=str(tmp_path / "app-data-ns"), store=store)

    namespaces = data_store.ensure_app_namespaces("app.data.001", "user.data")
    skill_assets = data_store.ensure_skill_asset_namespace()

    assert len(namespaces) == 3
    assert {item.namespace_type for item in namespaces} == {"app_data", "runtime_state", "system_metadata"}
    assert skill_assets.namespace_type == "skill_assets"


def test_installer_provisions_namespaces(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "app-data-installer-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "app-data-installer-ns"), store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store)
    registry.register_blueprint(build_blueprint())

    result = installer.install_app("bp.data.store", user_id="user.data")
    namespaces = data_store.list_namespaces(result.app_instance_id)

    assert len(namespaces) == 3
    assert Path(namespaces[0].path).exists()


def test_put_and_list_data_records(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "app-data-records-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "app-data-records-ns"), store=store)
    data_store.ensure_app_namespaces("app.data.002", "user.data")

    record = data_store.put_record(
        namespace_id="app.data.002:app_data",
        key="profile",
        value={"name": "demo", "status": "active"},
        tags=["user", "profile"],
    )
    records = data_store.list_records("app.data.002:app_data")

    assert record.key == "profile"
    assert len(records) == 1
    assert records[0].value["name"] == "demo"


def test_data_namespace_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "data-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    namespaces_response = client.get("/data/namespaces", params={"app_instance_id": app_instance_id})
    assert namespaces_response.status_code == 200
    namespaces = namespaces_response.json()
    assert len(namespaces) == 3

    app_data_namespace = next(item for item in namespaces if item["namespace_type"] == "app_data")
    record_response = client.post(
        f"/data/namespaces/{app_data_namespace['namespace_id']}/records",
        json={"key": "settings", "value": {"theme": "dark"}, "tags": ["prefs"]},
    )
    assert record_response.status_code == 200

    list_response = client.get(f"/data/namespaces/{app_data_namespace['namespace_id']}/records")
    assert list_response.status_code == 200
    assert list_response.json()[0]["value"]["theme"] == "dark"

    persistence_response = client.get("/runtime/persistence")
    assert persistence_response.status_code == 200
    assert "data_namespaces" in persistence_response.json()
