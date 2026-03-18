import json

from app.models.context_skill import ContextSkillRequest
from app.services.app_context_store import AppContextStore
from app.services.context_skill_service import ContextSkillService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.models.app_instance import AppInstance


def test_context_runtime_view_is_json_serializable() -> None:
    store = RuntimeStateStore(base_dir="data/test-context-runtime-view")
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
    context_store.ensure_context(instance.id)

    payload = skill.execute(instance.id, ContextSkillRequest(operation="list_runtime_view"))
    encoded = json.dumps(payload)

    assert "app.context.runtime.view" in encoded
    assert '"runtime"' in encoded
