from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.prompt_invocation_service import PromptInvocationService
from app.services.prompt_selection_service import PromptSelectionService
from app.services.log_evidence_service import LogEvidenceService
from app.services.context_compaction import ContextCompactionService


client = TestClient(app)


class _FakeLoader:
    def load(self):
        class _Config:
            provider = "OpenAI"
            model = "gpt-5.4"
        return _Config()

    def resolve_api_key(self, config):
        return "sk-test"


class _FakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {"id": "resp_wf_123", "input_echo": input_payload, "extra_payload": extra_payload}


def test_workflow_executor_runs_state_and_event_steps(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-executor-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-executor-ns"), store=store)
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
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.exec",
            name="Workflow Exec App",
            goal="execute deterministic workflow",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.exec",
                    "name": "exec",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.set", "kind": "module", "ref": "state.set", "config": {"key": "draft", "value": {"status": "ok"}}},
                        {"id": "step.get", "kind": "module", "ref": "state.get", "config": {"key": "draft"}},
                        {"id": "step.event", "kind": "event", "ref": "workflow.completed", "config": {"event_name": "workflow.completed"}},
                    ],
                }
            ],
            required_modules=["state.get", "state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.exec", user_id="workflow-user")

    result = executor.execute_primary_workflow(install_result.app_instance_id, inputs={"source": "test"})

    assert result.workflow_id == "wf.exec"
    assert len(result.steps) == 3
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    assert any(item.key == "draft" for item in records)
    events = event_bus.list_events("workflow.completed")
    assert len(events) == 1
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key.startswith("workflow-result:") for item in context.entries)


def test_workflow_executor_supports_workflow_selection_and_placeholders(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-selection-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-selection-ns"), store=store)
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
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.select",
            name="Workflow Select App",
            goal="run selected workflow",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.primary",
                    "name": "primary",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.primary", "kind": "module", "ref": "state.set", "config": {"key": "primary", "value": {"ok": True}}},
                    ],
                },
                {
                    "id": "wf.secondary",
                    "name": "secondary",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "ask.human", "kind": "human_task", "ref": "human.review", "config": {"prompt": "please review"}},
                        {"id": "call.skill", "kind": "skill", "ref": "skill.review", "config": {"mode": "draft"}},
                    ],
                },
            ],
            required_modules=["state.set"],
            required_skills=["skill.review"],
        )
    )
    install_result = installer.install_app("bp.workflow.select", user_id="workflow-select-user")

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.secondary",
        inputs={"topic": "selection"},
    )

    assert result.workflow_id == "wf.secondary"
    assert result.status == "partial"
    assert len(result.steps) == 2
    assert all(step.status == "skipped" for step in result.steps)
    assert result.failed_step_ids == []
    runtime_records = data_store.list_records(f"{install_result.app_instance_id}:runtime_state")
    assert any(item.key == "workflow_execution:wf.secondary" for item in runtime_records)
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key == "human-task:ask.human" for item in context.entries)
    assert any(item.key == "skill-step:call.skill" for item in context.entries)


def test_workflow_executor_passes_step_outputs_between_steps(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-step-outputs-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-step-outputs-ns"), store=store)
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
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.outputs",
            name="Workflow Outputs App",
            goal="pass outputs between steps",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.outputs",
                    "name": "outputs",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.seed", "kind": "module", "ref": "state.set", "config": {"key": "seed", "value": {"message": "hello"}}},
                        {"id": "step.read", "kind": "module", "ref": "state.get", "config": {"key": "seed"}},
                        {"id": "step.copy", "kind": "module", "ref": "state.set", "config": {"key": "copied", "value": {"$from_step": "step.read", "field": "value"}}},
                        {"id": "step.emit", "kind": "event", "ref": "workflow.outputs.done", "config": {"event_name": "workflow.outputs.done", "payload": {"$from_step": "step.copy", "field": "value"}}},
                    ],
                }
            ],
            required_modules=["state.get", "state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.outputs", user_id="workflow-output-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.outputs")

    assert result.status == "completed"
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    copied = next(item for item in records if item.key == "copied")
    assert copied.value["message"] == "hello"
    event = event_bus.list_events("workflow.outputs.done")[0]
    assert event.payload["message"] == "hello"
    assert result.steps[-1].output["event_name"] == "workflow.outputs.done"


def test_workflow_executor_runs_prompt_invoke_module_step(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-prompt-invoke-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-prompt-invoke-ns"), store=store)
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
    log_evidence = LogEvidenceService(store=store)
    context_compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=type("_StubWorkflowExecutor", (), {"list_history": lambda self, app_instance_id: [], "_skill_runtime": None})(),
        store=store,
        log_evidence_service=log_evidence,
    )
    prompt_selection = PromptSelectionService(context_compaction=context_compaction, log_evidence=log_evidence)
    prompt_invocation = PromptInvocationService(
        prompt_selection=prompt_selection,
        model_loader=_FakeLoader(),
        client_factory=_FakeClient,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
        prompt_invocation_service=prompt_invocation,
    )
    executor._skill_risk_policy = SkillRiskPolicyService(store=store, log_evidence_service=log_evidence)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.prompt",
            name="Workflow Prompt App",
            goal="run prompt invocation in workflow",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.prompt.invoke",
                    "name": "prompt invoke",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "prompt.run", "kind": "module", "ref": "prompt.invoke", "config": {"query": {"$from_inputs": "query"}, "limit": 3, "strategy": "query_first", "extra_payload": {"metadata": {"source": "workflow"}}}},
                    ],
                }
            ],
            required_modules=["prompt.invoke"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.prompt", user_id="workflow-prompt-user")
    context_store.update_context(
        install_result.app_instance_id,
        current_stage="reasoning",
        current_goal="answer user",
        status="active",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.prompt.invoke",
        failed_step_ids=["step.a"],
        execution_id="exec.prompt.1",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.prompt.invoke",
        failed_step_ids=["step.a"],
        execution_id="exec.prompt.2",
        status="partial",
    )

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.prompt.invoke",
        inputs={"query": "workflow"},
    )

    assert result.status == "completed"
    assert result.steps[0].ref == "prompt.invoke"
    assert "model_invocation" in result.steps[0].output
    assert result.steps[0].output["model_invocation"]["result"]["id"] == "resp_wf_123"
    assert "normalized_response" in result.steps[0].output
    assert result.steps[0].output["normalized_response"]["finish_status"] == "completed"
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key == "prompt-invocation:prompt.run" for item in context.entries)


def test_workflow_executor_blocks_prompt_invoke_without_user_approval(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-prompt-approval-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-prompt-approval-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    log_evidence = LogEvidenceService(store=store)
    context_compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=type("_StubWorkflowExecutor", (), {"list_history": lambda self, app_instance_id: [], "_skill_runtime": None})(),
        store=store,
        log_evidence_service=log_evidence,
    )
    prompt_selection = PromptSelectionService(context_compaction=context_compaction, log_evidence=log_evidence)
    prompt_invocation = PromptInvocationService(
        prompt_selection=prompt_selection,
        model_loader=_FakeLoader(),
        client_factory=_FakeClient,
    )
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
        prompt_invocation_service=prompt_invocation,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.prompt.approval",
            name="Workflow Prompt Approval App",
            goal="require approval for prompt invoke",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.prompt.approval",
                    "name": "prompt approval",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "prompt.run", "kind": "module", "ref": "prompt.invoke", "config": {"query": "workflow", "approved_by_user": False}},
                    ],
                }
            ],
            required_modules=["prompt.invoke"],
            required_skills=[],
            runtime_policy={"prompt_invoke_requires_ask_user": True},
        )
    )
    install_result = installer.install_app("bp.workflow.prompt.approval", user_id="workflow-prompt-approval-user")

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.prompt.approval",
    )

    assert result.status == "partial"
    assert result.steps[0].status == "failed"
    assert result.steps[0].detail["policy_blocked"] is True
    events = executor._skill_risk_policy.list_events(skill_id="prompt.invoke")
    assert any(item.event_type == "approval_required" for item in events)


def test_workflow_executor_supports_conditional_steps_and_outputs_summary(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-conditions-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-conditions-ns"), store=store)
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
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.conditions",
            name="Workflow Condition App",
            goal="support conditional execution",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.conditional",
                    "name": "conditional",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.flag", "kind": "module", "ref": "state.set", "config": {"key": "flag", "value": {"enabled": True}}},
                        {"id": "copy.enabled", "kind": "module", "ref": "state.set", "config": {"key": "copy-enabled", "value": {"$from_inputs": "payload"}, "when": {"source": {"$from_inputs": "run_copy"}, "equals": True}}},
                        {"id": "copy.disabled", "kind": "module", "ref": "state.set", "config": {"key": "copy-disabled", "value": {"$from_inputs": "payload"}, "when": {"source": {"$from_inputs": "run_copy"}, "equals": False}}},
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.conditions", user_id="workflow-conditions-user")

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.conditional",
        inputs={"run_copy": True, "payload": {"name": "demo"}},
    )

    assert result.status == "partial"
    assert "copy.enabled" in result.outputs["completed_steps"]
    assert "copy.disabled" in result.outputs["skipped_steps"]
    assert "copy.enabled" in result.outputs["step_outputs"]
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    assert any(item.key == "copy-enabled" for item in records)
    assert all(item.key != "copy-disabled" for item in records)


def test_workflow_latest_api_returns_newest_execution() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.latest",
            "name": "Workflow Latest App",
            "goal": "inspect latest workflow execution",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.latest.exec",
                    "name": "latest exec",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.latest", "kind": "module", "ref": "state.set", "config": {"key": "latest", "value": {"$from_inputs": "payload"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.latest/install",
        json={"user_id": "workflow-latest-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    first_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"payload": {"version": 1}}},
    )
    assert first_execute.status_code == 200

    second_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"payload": {"version": 2}}},
    )
    assert second_execute.status_code == 200

    latest_response = client.get("/workflows/latest", params={"app_instance_id": app_instance_id})
    assert latest_response.status_code == 200
    latest = latest_response.json()["execution"]
    assert latest is not None
    assert latest["workflow_id"] == "wf.latest.exec"
    assert latest["outputs"]["inputs"]["payload"]["version"] == 2
    assert latest["failed_step_ids"] == []



def test_workflow_failures_api_supports_workflow_and_failed_step_filters() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.failure.filters",
            "name": "Workflow Failure Filters App",
            "goal": "filter workflow failures",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.failure.filtered",
                    "name": "failure filtered",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
                },
                {
                    "id": "wf.success.other",
                    "name": "success other",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.ok", "kind": "module", "ref": "state.set", "config": {"key": "ok", "value": {"done": True}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.failure.filters/install",
        json={"user_id": "workflow-failure-filter-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    failure_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.failure.filtered", "trigger": "api", "inputs": {}},
    )
    assert failure_execute.status_code == 200
    assert failure_execute.json()["failed_step_ids"] == ["blocked.skill"]

    success_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.success.other", "trigger": "api", "inputs": {}},
    )
    assert success_execute.status_code == 200

    filtered_response = client.get(
        "/workflows/failures",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.failure.filtered",
            "failed_step_id": "blocked.skill",
        },
    )
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert len(filtered) == 1
    assert filtered[0]["workflow_id"] == "wf.failure.filtered"
    assert filtered[0]["failed_step_ids"] == ["blocked.skill"]

    empty_response = client.get(
        "/workflows/failures",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.success.other",
            "failed_step_id": "blocked.skill",
        },
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == []



def test_retry_last_failure_returns_comparison_details() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.retry.compare",
            "name": "Workflow Retry Compare App",
            "goal": "compare retry results",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.retry.compare",
                    "name": "retry compare",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "set.maybe",
                            "kind": "module",
                            "ref": "state.set",
                            "config": {
                                "key": "maybe",
                                "value": {"ok": True},
                                "when": {"source": {"$from_inputs": "allow_write", "default": False}, "equals": True}
                            },
                        },
                        {
                            "id": "read.maybe",
                            "kind": "module",
                            "ref": "state.get",
                            "config": {"key": "maybe"},
                        },
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set", "state.get"],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.retry.compare/install",
        json={"user_id": "workflow-retry-compare-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    first_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.retry.compare", "trigger": "api", "inputs": {"allow_write": False}},
    )
    assert first_execute.status_code == 200
    first = first_execute.json()
    assert first["status"] == "partial"
    assert first["failed_step_ids"] == []

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200
    retried = retry_response.json()
    assert retried["trigger"] == "retry:api"
    assert retried["retry_comparison"]["previous_status"] == "partial"
    assert retried["retry_comparison"]["retried_status"] == "partial"
    assert retried["retry_comparison"]["previous_failed_step_ids"] == []
    assert retried["retry_comparison"]["retried_failed_step_ids"] == []
    assert retried["retry_comparison"]["unchanged_failed_step_ids"] == []
    assert retried["retry_comparison"]["resolved_failed_step_ids"] == []
    assert retried["retry_comparison"]["newly_failed_step_ids"] == []
    assert retried["retry_of_completed_at"] is not None



def test_workflow_diagnostics_api_returns_latest_failure_and_retry_summary() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.diagnostics",
            "name": "Workflow Diagnostics App",
            "goal": "summarize workflow recovery state",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.diagnostics",
                    "name": "diagnostics",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.diagnostics/install",
        json={"user_id": "workflow-diagnostics-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.diagnostics", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["failed_step_ids"] == ["blocked.skill"]

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    diagnostics_response = client.get(
        "/workflows/diagnostics",
        params={"app_instance_id": app_instance_id, "workflow_id": "wf.diagnostics"},
    )
    assert diagnostics_response.status_code == 200
    payload = diagnostics_response.json()
    assert payload["latest_execution"] is not None
    assert payload["latest_failure"] is not None
    assert payload["latest_retry"] is not None
    assert payload["latest_failure"]["failed_step_ids"] == ["blocked.skill"]
    assert payload["latest_retry"]["retry_comparison"]["previous_failed_step_ids"] == ["blocked.skill"]
    assert payload["recovery_state"]["recovered"] is False
    assert payload["recovery_state"]["still_failing"] is True
    assert payload["recovery_state"]["unchanged_failed_step_ids"] == ["blocked.skill"]



def test_workflow_diagnostics_supports_failed_step_filter_and_latest_recovery() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.diagnostics.filter",
            "name": "Workflow Diagnostics Filter App",
            "goal": "filter diagnostics and summarize latest recovery",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.diagnostics.filter",
                    "name": "diagnostics filter",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.diagnostics.filter/install",
        json={"user_id": "workflow-diagnostics-filter-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.diagnostics.filter", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    diagnostics_response = client.get(
        "/workflows/diagnostics",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.diagnostics.filter",
            "failed_step_id": "blocked.skill",
        },
    )
    assert diagnostics_response.status_code == 200
    payload = diagnostics_response.json()
    assert payload["latest_failure"] is not None
    assert payload["latest_failure"]["failed_step_ids"] == ["blocked.skill"]
    assert payload["latest_retry"] is not None
    assert payload["latest_retry"]["retry_comparison"]["unchanged_failed_step_ids"] == ["blocked.skill"]

    empty_diagnostics = client.get(
        "/workflows/diagnostics",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.diagnostics.filter",
            "failed_step_id": "other.step",
        },
    )
    assert empty_diagnostics.status_code == 200
    assert empty_diagnostics.json() == {
        "latest_execution": None,
        "latest_failure": None,
        "latest_retry": None,
        "recovery_state": None,
    }

    latest_recovery = client.get(
        "/workflows/latest-recovery",
        params={"app_instance_id": app_instance_id, "workflow_id": "wf.diagnostics.filter"},
    )
    assert latest_recovery.status_code == 200
    recovery = latest_recovery.json()["recovery"]
    assert recovery is not None
    assert recovery["workflow_id"] == "wf.diagnostics.filter"
    assert recovery["still_failing"] is True
    assert recovery["unchanged_failed_step_ids"] == ["blocked.skill"]



def test_workflow_overview_api_aggregates_diagnostics_and_recovery() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.overview",
            "name": "Workflow Overview App",
            "goal": "aggregate diagnostics and latest recovery",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.overview",
                    "name": "overview",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.overview/install",
        json={"user_id": "workflow-overview-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.overview", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    overview_response = client.get(
        "/workflows/overview",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.overview",
            "failed_step_id": "blocked.skill",
        },
    )
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["diagnostics"]["latest_failure"] is not None
    assert overview["diagnostics"]["latest_failure"]["failed_step_ids"] == ["blocked.skill"]
    assert overview["latest_recovery"] is not None
    assert overview["latest_recovery"]["workflow_id"] == "wf.overview"
    assert overview["latest_recovery"]["unchanged_failed_step_ids"] == ["blocked.skill"]
    assert overview["health"]["health_status"] == "failing"
    assert overview["health"]["severity"] == "critical"
    assert overview["health"]["unresolved_failure_count"] == 1
    assert overview["health"]["latest_failed_step_ids"] == ["blocked.skill"]
    assert overview["health"]["has_recent_retry"] is True



def test_workflow_overview_reports_healthy_status_for_completed_workflow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.health.healthy",
            "name": "Workflow Healthy Health App",
            "goal": "report healthy workflow state",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.health.healthy",
                    "name": "health healthy",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.ok", "kind": "module", "ref": "state.set", "config": {"key": "ok", "value": {"done": True}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.health.healthy/install",
        json={"user_id": "workflow-health-healthy-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.health.healthy", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200

    overview_response = client.get(
        "/workflows/overview",
        params={"app_instance_id": app_instance_id, "workflow_id": "wf.health.healthy"},
    )
    assert overview_response.status_code == 200
    health = overview_response.json()["health"]
    assert health["health_status"] == "healthy"
    assert health["severity"] == "info"
    assert health["unresolved_failure_count"] == 0
    assert health["latest_failed_step_ids"] == []
    assert health["has_recent_retry"] is False
    assert health["last_transition"] == "completed"



def test_workflow_overview_reports_unknown_for_partial_without_failed_steps() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.health.unknown",
            "name": "Workflow Unknown Health App",
            "goal": "report unknown workflow state when partial has no failed steps",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.health.unknown",
                    "name": "health unknown",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "read.missing",
                            "kind": "module",
                            "ref": "state.get",
                            "config": {"key": "missing"},
                        },
                    ],
                }
            ],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.health.unknown/install",
        json={"user_id": "workflow-health-unknown-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.health.unknown", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "partial"
    assert execute_response.json()["failed_step_ids"] == []

    overview_response = client.get(
        "/workflows/overview",
        params={"app_instance_id": app_instance_id, "workflow_id": "wf.health.unknown"},
    )
    assert overview_response.status_code == 200
    health = overview_response.json()["health"]
    assert health["health_status"] == "unknown"
    assert health["severity"] == "info"
    assert health["unresolved_failure_count"] == 0
    assert health["latest_failed_step_ids"] == []
    assert health["has_recent_retry"] is False
    assert health["last_transition"] == "partial-without-failed-steps"



def test_workflow_api_contracts_share_observability_filter_semantics() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.api.contracts",
            "name": "Workflow API Contracts App",
            "goal": "verify observability api filter semantics",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.contracts",
                    "name": "api contracts",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.api.contracts/install",
        json={"user_id": "workflow-api-contract-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    first_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.api.contracts", "trigger": "api", "inputs": {}},
    )
    assert first_execute.status_code == 200
    first_completed_at = first_execute.json()["completed_at"]

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    diagnostics = client.get(
        "/workflows/diagnostics",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.contracts",
            "failed_step_id": "blocked.skill",
        },
    )
    assert diagnostics.status_code == 200
    assert diagnostics.json()["latest_failure"]["failed_step_ids"] == ["blocked.skill"]

    history = client.get(
        "/workflows/observability-history",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.contracts",
            "failed_step_id": "blocked.skill",
            "since": first_completed_at,
            "unresolved_only": True,
            "limit": 1,
        },
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert len(history_payload["items"]) == 1
    assert history_payload["items"][0]["workflow_id"] == "wf.api.contracts"
    assert history_payload["meta"]["returned_count"] == 1
    assert history_payload["meta"]["unresolved_count"] >= 1
    assert history_payload["meta"]["has_more"] is True
    assert history_payload["meta"]["next_cursor"] is not None

    timeline = client.get(
        "/workflows/timeline",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.contracts",
            "failed_step_id": "blocked.skill",
            "since": first_completed_at,
            "limit": 1,
        },
    )
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert len(timeline_payload["items"]) == 1
    assert timeline_payload["items"][0]["workflow_id"] == "wf.api.contracts"
    assert timeline_payload["meta"]["returned_count"] == 1
    assert timeline_payload["meta"]["has_more"] is True
    assert timeline_payload["meta"]["next_cursor"] is not None



def test_workflow_stats_api_returns_aggregate_observability_totals() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.api.stats",
            "name": "Workflow API Stats App",
            "goal": "verify workflow stats api",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.stats",
                    "name": "api stats",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.api.stats/install",
        json={"user_id": "workflow-api-stats-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.api.stats", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    stats_response = client.get(
        "/workflows/stats",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.stats",
            "failed_step_id": "blocked.skill",
        },
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_executions"] >= 2
    assert stats["total_failures"] >= 1
    assert stats["total_retries"] >= 1
    assert stats["unresolved_executions"] >= 1
    assert stats["latest_event_at"] is not None



def test_workflow_dashboard_api_returns_operator_read_model() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.api.dashboard",
            "name": "Workflow API Dashboard App",
            "goal": "verify workflow dashboard api",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.dashboard",
                    "name": "api dashboard",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
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
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.api.dashboard/install",
        json={"user_id": "workflow-api-dashboard-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.api.dashboard", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200

    dashboard_response = client.get(
        "/workflows/dashboard",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.dashboard",
            "failed_step_id": "blocked.skill",
            "timeline_limit": 2,
        },
    )
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["overview"]["health"]["health_status"] == "failing"
    assert dashboard["stats"]["total_executions"] >= 2
    assert dashboard["recent_timeline"]["meta"]["returned_count"] >= 1
    assert len(dashboard["recent_timeline"]["items"]) >= 1



def test_workflow_execution_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.api",
            "name": "Workflow API App",
            "goal": "run workflow via api",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.exec",
                    "name": "api exec",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.settings", "kind": "module", "ref": "state.set", "config": {"key": "settings", "value": {"theme": "dark"}}},
                        {"id": "emit.done", "kind": "event", "ref": "workflow.api.done", "config": {"event_name": "workflow.api.done"}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
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

    install_response = client.post(
        "/registry/apps/bp.workflow.api/install",
        json={"user_id": "workflow-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"request_id": "r1"}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["workflow_id"] == "wf.api.exec"
    assert len(execute_response.json()["steps"]) == 2

    records_response = client.get(f"/data/namespaces/{app_instance_id}:app_data/records")
    assert records_response.status_code == 200
    assert any(item["key"] == "settings" for item in records_response.json())

    events_response = client.get("/events", params={"event_name": "workflow.api.done"})
    assert events_response.status_code == 200
    assert any(item["app_instance_id"] == app_instance_id for item in events_response.json())
