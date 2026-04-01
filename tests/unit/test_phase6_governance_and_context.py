from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.context_compaction import ContextCompactionService
from app.services.context_retrieval_service import ContextRetrievalService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.persistence_health_service import PersistenceHealthService
from app.services.policy_authority_service import PolicyAuthorityService, PolicyAuthorityError
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.workflow_executor import WorkflowExecutorService

client = TestClient(app)


def _build_context_stack(tmp_path: Path):
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase6-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "phase6-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
        store=store,
    )
    compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=executor,
        store=store,
    )
    retrieval = ContextRetrievalService(app_context_store=context_store, context_compaction=compaction)
    return store, registry, installer, context_store, executor, compaction, retrieval


def test_phase6_policy_authority_requires_reviewer_and_reason(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase6-authority"))
    authority = PolicyAuthorityService(store=store)
    authority.set_policy(
        authority.get_policy("app_activate").model_copy(update={
            "require_reviewer": True,
            "require_reason": True,
            "allow_automatic": False,
            "allowed_reviewers": ["ops-reviewer"],
        })
    )

    try:
        authority.enforce(scope="app_activate", reviewer="", reason="", automatic=False)
        assert False, "expected PolicyAuthorityError"
    except PolicyAuthorityError:
        pass

    decision = authority.enforce(scope="app_activate", reviewer="ops-reviewer", reason="promote candidate", automatic=False)
    assert decision.allowed is True
    assert decision.reviewer == "ops-reviewer"


def test_phase6_persistence_health_reports_corrupted_files(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase6-health"))
    broken = store.base_path / "bad.json"
    broken.write_text("{not-json", encoding="utf-8")
    assert store.load_json("bad", {}) == {}

    health = PersistenceHealthService(store=store).get_summary()
    assert health.corrupted_file_count == 1
    assert health.healthy is False
    assert any(item.startswith("corrupted/bad.invalid") for item in health.corrupted_files)


def test_phase6_context_retrieval_returns_layered_prompt_ready_view(tmp_path: Path) -> None:
    store, registry, installer, context_store, executor, compaction, retrieval = _build_context_stack(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.phase6.context",
            name="Phase6 Context App",
            goal="exercise layered context",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase6.context",
                    "name": "phase6 context",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "goal", "kind": "module", "ref": "context.set_goal", "config": {"goal": "finish phase 6"}},
                        {"id": "stage", "kind": "module", "ref": "context.set_stage", "config": {"stage": "phase6:active"}},
                        {"id": "note", "kind": "module", "ref": "context.append", "config": {"section": "decisions", "key": "phase6-decision", "value": {"accepted": True}}},
                    ],
                }
            ],
            required_modules=["context.set_goal", "context.set_stage", "context.append"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.phase6.context", user_id="phase6-user")
    executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase6.context")
    compaction.compact(install.app_instance_id, reason="phase6-test")

    prompt_ready = retrieval.get_prompt_ready_context(install.app_instance_id)
    detail_refs = retrieval.retrieve_detail_refs(install.app_instance_id)

    assert prompt_ready["working_set"]["current_goal"] == "finish phase 6"
    assert prompt_ready["summary"]["metadata"]["compact_reason"] == "phase6-test"
    assert prompt_ready["selection_policy"]["avoid_raw_history"] is True
    assert "summary_refs" in detail_refs


def test_phase6_authority_and_persistence_health_api() -> None:
    set_response = client.post(
        "/policy-authority",
        json={
            "scope": "app_activate",
            "require_reviewer": True,
            "require_reason": True,
            "allow_automatic": False,
            "allowed_reviewers": ["ops-reviewer"],
        },
    )
    assert set_response.status_code == 200

    summary_response = client.get("/policy-authority")
    assert summary_response.status_code == 200
    assert summary_response.json()["reviewer_required_scope_count"] >= 1

    health_response = client.get("/persistence/health")
    assert health_response.status_code == 200
    assert "healthy" in health_response.json()
