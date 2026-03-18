from app.models.app_config import AppConfigRequest
from app.services.app_config_service import AppConfigService
from app.services.app_data_store import AppDataStore
from app.services.runtime_state_store import RuntimeStateStore


def test_app_config_service_initializes_and_mutates_values() -> None:
    store = RuntimeStateStore(base_dir="data/test-app-config")
    data_store = AppDataStore(base_dir="data/test-app-config-ns", store=store)
    data_store.ensure_app_namespaces("app.config.test", "user.config")
    service = AppConfigService(data_store=data_store, store=store)

    snapshot = service.ensure_initialized("app.config.test", defaults={"runtime": {"mode": "service"}})

    assert snapshot.values["runtime"]["mode"] == "service"

    set_result = service.execute("app.config.test", AppConfigRequest(operation="set", key="ui", value={"theme": "dark"}))
    assert set_result.values["ui"]["theme"] == "dark"

    patch_result = service.execute("app.config.test", AppConfigRequest(operation="patch", key="ui", value={"density": "compact"}))
    assert patch_result.values["ui"]["theme"] == "dark"
    assert patch_result.values["ui"]["density"] == "compact"

    get_result = service.execute("app.config.test", AppConfigRequest(operation="get", key="ui"))
    assert get_result.value["theme"] == "dark"

    delete_result = service.execute("app.config.test", AppConfigRequest(operation="delete", key="ui"))
    assert delete_result.key == "ui"
    assert "ui" not in delete_result.values
    assert len(service.list_history("app.config.test")) == 4
