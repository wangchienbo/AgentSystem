from pathlib import Path

import json

from app.models.app_instance import AppInstance
from app.models.context_skill import ContextSkillRequest
from app.services.app_context_store import AppContextStore
from app.services.context_skill_service import ContextSkillService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


def test_runtime_state_store_returns_default_for_empty_or_invalid_json(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    empty_path = Path(store.base_path) / "app_contexts.json"
    empty_path.write_text("", encoding="utf-8")

    assert store.load_json("app_contexts", {}) == {}
    assert not empty_path.exists()
    assert any(path.name.startswith("app_contexts.empty") for path in (Path(store.base_path) / "corrupted").iterdir())

    invalid_path = Path(store.base_path) / "registry_entries.json"
    invalid_path.write_text("{not-json", encoding="utf-8")

    assert store.load_json("registry_entries", {}) == {}
    assert not invalid_path.exists()
    assert any(path.name.startswith("registry_entries.invalid") for path in (Path(store.base_path) / "corrupted").iterdir())


def test_context_runtime_view_is_json_serializable(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "context-runtime-view-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    skill = ContextSkillService(context_store=context_store)

    instance = AppInstance(
        id="app.context.runtime.view",
        blueprint_id="bp.context.runtime.view",
        owner_user_id="user-1",
        data_namespace="users/user-1/apps/app.context.runtime.view",
    )
    runtime.register_instance(instance)
    lifecycle.transition(instance.id, "validate", reason="test")
    lifecycle.transition(instance.id, "compile", reason="test")
    lifecycle.transition(instance.id, "install", reason="test")
    runtime.start(instance.id, reason="test")
    runtime.enqueue_task(instance.id, "task-1")
    context_store.ensure_context(instance.id)
    context_store.append_entry(
        instance.id,
        section="facts",
        key="fact-1",
        value={"summary": "hello"},
        tags=["demo"],
    )

    payload = skill.execute(instance.id, ContextSkillRequest(operation="list_runtime_view"))
    encoded = json.dumps(payload)

    assert "app.context.runtime.view" in encoded
    assert '"runtime"' in encoded
    assert payload["context"]["app_instance_id"] == instance.id
    assert payload["context"]["entries"][0]["key"] == "fact-1"
    assert payload["runtime"] is not None
    assert payload["runtime"]["pending_tasks"] == ["task-1"]
    assert payload["runtime"]["lease"]["app_instance_id"] == instance.id
    assert payload["runtime"]["latest_checkpoint"]["app_instance_id"] == instance.id


def test_context_runtime_view_falls_back_to_context_only_when_runtime_unavailable(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "context-runtime-view-no-runtime-store"))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=None)
    skill = ContextSkillService(context_store=context_store)

    instance = AppInstance(
        id="app.context.no.runtime",
        blueprint_id="bp.context.no.runtime",
        owner_user_id="user-2",
        data_namespace="users/user-2/apps/app.context.no.runtime",
    )
    lifecycle.register_instance(instance)
    context_store.ensure_context(instance.id)

    payload = skill.execute(instance.id, ContextSkillRequest(operation="list_runtime_view"))

    assert payload["context"]["app_instance_id"] == instance.id
    assert payload["runtime"] is None
    assert json.loads(json.dumps(payload))["runtime"] is None
