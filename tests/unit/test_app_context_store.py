import uuid

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def test_app_context_store_create_update_and_append() -> None:
    suffix = uuid.uuid4().hex
    store = RuntimeStateStore(base_dir=f"data/test-app-context-{suffix}")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=f"data/test-app-context-ns-{suffix}", store=store)
    registry = AppRegistryService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.context.test",
            name="Context Test App",
            goal="test shared context",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.context", "name": "context", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.context.test", user_id="context-user")
    app_instance_id = install_result.app_instance_id

    context = context_store.ensure_context(app_instance_id)
    assert context.app_instance_id == app_instance_id
    assert context.owner_user_id == "context-user"
    assert context.current_goal == "test shared context"

    updated = context_store.update_context(app_instance_id, current_goal="finish analysis", current_stage="planning")
    assert updated.current_goal == "finish analysis"
    assert updated.current_stage == "planning"

    entry = context_store.append_entry(
        app_instance_id=app_instance_id,
        section="facts",
        key="task-brief",
        value={"summary": "Need a structured result"},
        tags=["brief"],
    )
    assert entry.section == "facts"
    assert context_store.get_context(app_instance_id).entries[0].key == "task-brief"



def test_app_context_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "context-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    update_response = client.post(
        f"/app-contexts/{app_instance_id}",
        json={"current_goal": "Help user solve a task", "current_stage": "planning"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_stage"] == "planning"

    append_response = client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "questions", "key": "missing-input", "value": {"question": "Need target audience"}},
    )
    assert append_response.status_code == 200
    assert append_response.json()["section"] == "questions"

    get_response = client.get(f"/app-contexts/{app_instance_id}")
    assert get_response.status_code == 200
    assert get_response.json()["app_instance_id"] == app_instance_id
    assert len(get_response.json()["entries"]) >= 1

    runtime_view_response = client.get(f"/app-contexts/{app_instance_id}?include_runtime=true")
    assert runtime_view_response.status_code == 200
    assert runtime_view_response.json()["context"]["app_instance_id"] == app_instance_id
    assert runtime_view_response.json()["runtime"]["app_instance"]["id"] == app_instance_id
    assert runtime_view_response.json()["runtime"]["lease"] is None
