from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_context import AppSharedContext
from app.models.context_policy import ContextCompactionPolicy
from app.models.context_summary import ContextSummary
from app.services.app_context_store import AppContextStore
from app.services.context_compaction import ContextCompactionService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def _register_context_app(blueprint_id: str) -> None:
    response = client.post(
        "/registry/apps",
        json={
            "id": blueprint_id,
            "name": "Context Test App",
            "goal": "exercise context compaction",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.context",
                    "name": "context workflow",
                    "triggers": ["manual"],
                    "steps": [],
                }
            ],
            "views": [],
            "required_modules": [],
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
    assert response.status_code == 200


def test_context_compaction_api_flow() -> None:
    _register_context_app("bp.context.compaction.api")
    install_response = client.post(
        "/registry/apps/bp.context.compaction.api/install",
        json={"user_id": "context-compaction-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "decisions", "key": "use-brief-mode", "value": {"enabled": True}, "tags": ["policy"]},
    )
    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "constraints", "key": "avoid-long-prompts", "value": {"enabled": True}, "tags": ["budget"]},
    )
    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "open_loops", "key": "summarize-context", "value": {"pending": True}, "tags": ["followup"]},
    )

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"topic": "compaction"}},
    )
    assert execute_response.status_code == 200

    compact_response = client.post(f"/app-contexts/{app_instance_id}/compact")
    assert compact_response.status_code == 200
    assert compact_response.json()["layer"] == "summary"
    assert "use-brief-mode" in compact_response.json()["decisions"]
    assert compact_response.json()["metadata"]["context_entry_count"] >= 1
    assert compact_response.json()["metadata"]["compact_reason"] == "manual"

    working_set_response = client.get(f"/app-contexts/{app_instance_id}/working-set")
    assert working_set_response.status_code == 200
    assert working_set_response.json()["layer"] == "working_set"
    assert "summarize-context" in working_set_response.json()["open_loops"]
    assert "evidence_summary" in working_set_response.json()["metadata"]

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["summary"]["layer"] == "summary"
    assert layers_response.json()["layers"]["detail"]["workflow_history_count"] >= 1


def test_context_compaction_loads_persisted_summary_and_policy(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "context-compaction-store"))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store)

    class StubWorkflowExecutor:
        def __init__(self) -> None:
            self._skill_runtime = None

        def list_history(self, app_instance_id: str):
            return []

    store.save_mapping(
        "app_contexts",
        {
            "app.persisted": AppSharedContext(
                app_instance_id="app.persisted",
                app_name="bp.persisted",
                owner_user_id="user.persisted",
                description="persisted context",
                status="active",
                current_goal="remember summary",
                current_stage="running",
                entries=[],
            )
        },
    )
    store.save_mapping(
        "context_summaries",
        {
            "app.persisted": ContextSummary(
                app_instance_id="app.persisted",
                layer="summary",
                current_goal="remember summary",
                current_stage="running",
                decisions=["persist-decision"],
                constraints=[],
                open_loops=[],
                artifacts=[],
                detail_refs=["workflow:wf.persisted:manual"],
                metadata={"compact_reason": "manual"},
            )
        },
    )
    store.save_mapping(
        "context_policies",
        {
            "app.persisted": ContextCompactionPolicy(
                app_instance_id="app.persisted",
                max_context_entries=3,
                compact_on_workflow_complete=True,
                compact_on_workflow_failure=False,
                compact_on_stage_change=True,
            )
        },
    )

    reloaded_context_store = AppContextStore(lifecycle=lifecycle, store=store)
    service = ContextCompactionService(
        app_context_store=reloaded_context_store,
        workflow_executor=StubWorkflowExecutor(),
        store=store,
    )

    assert service.get_policy("app.persisted").compact_on_stage_change is True
    assert service.list_layers("app.persisted")["layers"]["summary"]["decisions"] == ["persist-decision"]
