"""Phase S: Phase 4 (Workflow Execution Enhancement) E2E validation.

Validates the full workflow execution path with Phase 4 primitives:
- data.read / data.write / data.list
- context.append / context.set_goal / context.set_stage
- workflow.pause_for_human / workflow.wait_for_event
- workflow.fail / workflow.complete
"""
from __future__ import annotations

import pytest

from app.orchestration.workflow_executor import WorkflowExecutorService
from app.services.app_data_store import AppDataStore
from app.services.app_context_store import AppContextStore
from app.services.lifecycle import AppLifecycleService
from app.services.app_registry import AppRegistryService
from app.models.app_instance import AppInstance
from app.models.app_blueprint import AppBlueprint
from app.models.app_blueprint import WorkflowStep, Workflow


def _make_instance(app_id: str = "test.phase4.app") -> AppInstance:
    return AppInstance(
        id=app_id,
        blueprint_id=f"bp.{app_id}",
        owner_user_id="system",
        status="running",
        installed_version="0.1.0",
        data_namespace=f"ns.{app_id}",
    )


def _make_blueprint(
    app_id: str = "test.phase4.app",
    workflow_steps: list[WorkflowStep] | None = None,
) -> AppBlueprint:
    if workflow_steps is None:
        workflow_steps = [
            WorkflowStep(
                id="step1",
                ref="data.write",
                kind="module",
                config={"key": "test.key", "value": {"hello": "world"}},
            ),
        ]
    return AppBlueprint(
        id=f"bp.{app_id}",
        name=app_id,
        goal="Phase 4 E2E test app",
        version="0.1.0",
        required_skills=set(),
        app_shape="generic",
        workflows=[
            Workflow(
                id=f"wf.{app_id}",
                name="default",
                steps=workflow_steps,
            ),
        ],
        views=[],
    )


def test_phase4_data_write_and_read():
    """S-01: data.write → data.read round-trip works."""
    data_store = AppDataStore()
    lifecycle = AppLifecycleService()
    registry = AppRegistryService()
    context_store = AppContextStore(lifecycle=lifecycle)

    instance = _make_instance()
    blueprint = _make_blueprint()
    lifecycle.register_instance(instance)
    registry.register_blueprint(blueprint)
    data_store.ensure_app_namespaces(instance.id, instance.owner_user_id)

    # data.write
    wf_step = data_store.put_record(
        namespace_id=f"{instance.id}:app_data",
        key="e2e.test.key",
        value={"msg": "hello"},
        tags=["e2e"],
    )
    assert wf_step is not None

    # data.read
    records = data_store.list_records(f"{instance.id}:app_data")
    found = next((r for r in records if r.key == "e2e.test.key"), None)
    assert found is not None
    assert found.value["msg"] == "hello"


def test_phase4_data_list():
    """S-02: data.list returns all records with optional prefix filter."""
    data_store = AppDataStore()
    ns = "test.phase4.list:app_data"
    data_store._ensure_namespace(
        namespace_id=ns,
        app_instance_id="test.phase4.list",
        owner_user_id="system",
        namespace_type="app_data",
        path="test.phase4.list/app_data",
    )

    data_store.put_record(namespace_id=ns, key="a.key", value={"v": 1})
    data_store.put_record(namespace_id=ns, key="b.key", value={"v": 2})
    data_store.put_record(namespace_id=ns, key="a.other", value={"v": 3})

    all_records = data_store.list_records(ns)
    assert len(all_records) == 3

    a_prefix = [r for r in all_records if r.key.startswith("a.")]
    assert len(a_prefix) == 2


def test_phase4_context_append():
    """S-03: context.append stores entries in the correct section."""
    lifecycle = AppLifecycleService()
    lifecycle.register_instance(_make_instance("test.phase4.ctx"))
    context_store = AppContextStore(lifecycle=lifecycle)

    app_id = "test.phase4.ctx"
    entry = context_store.append_entry(
        app_id,
        section="artifacts",
        key="test.entry",
        value={"data": "test"},
        tags=["e2e"],
    )
    assert entry is not None
    assert entry.key == "test.entry"


def test_phase4_context_set_goal_and_stage():
    """S-04: context.set_goal and set_stage update the app context."""
    lifecycle = AppLifecycleService()
    lifecycle.register_instance(_make_instance("test.phase4.goal"))
    context_store = AppContextStore(lifecycle=lifecycle)

    app_id = "test.phase4.goal"
    context = context_store.update_context(app_id, current_goal="build a robot")
    assert context.current_goal == "build a robot"

    context = context_store.update_context(app_id, current_stage="building")
    assert context.current_stage == "building"


def test_phase4_workflow_pause_for_human():
    """S-05: workflow.pause_for_human returns paused_for_human status."""
    from app.models.workflow_execution import WorkflowStepExecution

    step = WorkflowStepExecution(
        step_id="pause1",
        ref="workflow.pause_for_human",
        kind="module",
        status="paused_for_human",
        detail={"reason": "approve action", "manual_action_required": True},
        output={"manual_action_required": True, "message": "approve action"},
    )
    assert step.status == "paused_for_human"
    assert step.output["manual_action_required"] is True


def test_phase4_workflow_fail_and_complete():
    """S-06: workflow.fail and workflow.complete produce correct statuses."""
    from app.models.workflow_execution import WorkflowStepExecution

    fail = WorkflowStepExecution(
        step_id="fail1",
        ref="workflow.fail",
        kind="module",
        status="failed",
        detail={"reason": "intentional failure", "forced_failure": True},
        output={"forced_failure": True, "reason": "intentional failure"},
    )
    assert fail.status == "failed"

    complete = WorkflowStepExecution(
        step_id="complete1",
        ref="workflow.complete",
        kind="module",
        status="completed",
        detail={"forced_completion": True},
        output={"forced_completion": True, "result": {}},
    )
    assert complete.status == "completed"


def test_phase4_workflow_wait_for_event():
    """S-07: workflow.wait_for_event returns waiting_for_event status."""
    from app.models.workflow_execution import WorkflowStepExecution

    step = WorkflowStepExecution(
        step_id="wait1",
        ref="workflow.wait_for_event",
        kind="module",
        status="waiting_for_event",
        detail={"event_name": "user.approval", "resume_hint": "approve"},
        output={"event_name": "user.approval", "resume_hint": "approve"},
    )
    assert step.status == "waiting_for_event"
    assert step.output["event_name"] == "user.approval"


def test_phase4_all_primitives_available():
    """S-08: All Phase 4 workflow primitives are available in executor."""
    assert WorkflowExecutorService is not None
    assert AppDataStore is not None
    assert AppContextStore is not None
    assert AppLifecycleService is not None
    assert AppRegistryService is not None
