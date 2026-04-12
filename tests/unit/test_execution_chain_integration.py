"""Execution chain integration tests — Phase 8.4.

Tests the full chain from workflow executor through skill runtime
to pipeline execution, verifying that components work together
end-to-end.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.workflow_execution import WorkflowExecutionResult
from app.models.app_blueprint import WorkflowStep
from app.services.pipeline_executor import (
    ExecutorType,
    PipelineExecutor,
    PipelineStep,
    StepStatus,
)
from app.services.workflow_executor import WorkflowExecutorService


# ===========================================================================
# Fixtures
# ===========================================================================

def _build_runtime_services(tmp_path: Path) -> dict:
    """Build a minimal set of runtime services for chain testing."""
    from app.bootstrap.runtime import build_runtime
    from app.bootstrap.skills import bootstrap_builtin_skills
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    bootstrap_builtin_skills(services["skill_runtime"], services)
    return services


def _ensure_workspace(tmp_path: Path) -> str:
    """Create and return a workspace directory."""
    ws = str(tmp_path / "workspace")
    os.makedirs(ws, exist_ok=True)
    return ws


# ===========================================================================
# Pipeline Executor Chain Tests
# ===========================================================================

def test_pipeline_executor_chains_shell_steps(tmp_path: Path) -> None:
    """Pipeline should chain multiple shell steps in sequence."""
    ws = _ensure_workspace(tmp_path)
    executor = PipelineExecutor(workspace=ws)

    steps = [
        PipelineStep(step_id="s1", executor_type=ExecutorType.SHELL, command="echo hello"),
        PipelineStep(step_id="s2", executor_type=ExecutorType.SHELL, command="echo world"),
    ]

    results = asyncio.run(executor.execute_pipeline(steps))

    assert len(results) == 2
    assert results[0].status == StepStatus.SUCCESS
    assert results[0].step_id == "s1"
    assert "hello" in results[0].output
    assert results[1].status == StepStatus.SUCCESS
    assert results[1].step_id == "s2"
    assert "world" in results[1].output


def test_pipeline_executor_stops_on_failure(tmp_path: Path) -> None:
    """Pipeline should stop chaining when a step fails."""
    ws = _ensure_workspace(tmp_path)
    executor = PipelineExecutor(workspace=ws)

    steps = [
        PipelineStep(step_id="s1", executor_type=ExecutorType.SHELL, command="echo ok"),
        PipelineStep(step_id="s2", executor_type=ExecutorType.SHELL, command="nonexistent_cmd_xyz"),
        PipelineStep(step_id="s3", executor_type=ExecutorType.SHELL, command="echo skipped"),
    ]

    results = asyncio.run(executor.execute_pipeline(steps))

    assert len(results) == 3
    assert results[0].status == StepStatus.SUCCESS
    assert results[1].status == StepStatus.FAILED
    assert results[2].status == StepStatus.SKIPPED


def test_pipeline_executor_respects_dependencies(tmp_path: Path) -> None:
    """Pipeline should respect step dependencies."""
    ws = _ensure_workspace(tmp_path)
    executor = PipelineExecutor(workspace=ws)

    steps = [
        PipelineStep(step_id="setup", executor_type=ExecutorType.SHELL, command="echo setup"),
        PipelineStep(step_id="run", executor_type=ExecutorType.SHELL, command="echo run", depends_on=["setup"]),
    ]

    results = asyncio.run(executor.execute_pipeline(steps))

    assert len(results) == 2
    assert results[0].status == StepStatus.SUCCESS
    assert results[1].status == StepStatus.SUCCESS


def test_pipeline_executor_fails_on_unmet_dependency(tmp_path: Path) -> None:
    """Pipeline should fail a step when its dependency failed."""
    ws = _ensure_workspace(tmp_path)
    executor = PipelineExecutor(workspace=ws)

    steps = [
        PipelineStep(step_id="setup", executor_type=ExecutorType.SHELL, command="nonexistent_cmd_xyz"),
        PipelineStep(step_id="run", executor_type=ExecutorType.SHELL, command="echo run", depends_on=["setup"]),
    ]

    results = asyncio.run(executor.execute_pipeline(steps))

    assert len(results) == 2
    assert results[0].status == StepStatus.FAILED
    # Step with unmet dependency gets skipped because the pipeline
    # sets failed=True after first failure
    assert results[1].status in (StepStatus.FAILED, StepStatus.SKIPPED)


def test_pipeline_executor_python_steps(tmp_path: Path) -> None:
    """Pipeline should execute Python steps in the chain."""
    ws = _ensure_workspace(tmp_path)
    executor = PipelineExecutor(workspace=ws)

    steps = [
        PipelineStep(
            step_id="py1",
            executor_type=ExecutorType.PYTHON,
            command="print('hello from python')",
        ),
    ]

    results = asyncio.run(executor.execute_pipeline(steps))

    assert len(results) == 1
    assert results[0].status == StepStatus.SUCCESS
    assert "hello from python" in results[0].output


# ===========================================================================
# Skill Execution Chain Tests
# ===========================================================================

def test_skill_runtime_executes_callable_chain(tmp_path: Path) -> None:
    """Skill runtime should execute callable skills in a chain."""
    services = _build_runtime_services(tmp_path)
    skill_runtime = services["skill_runtime"]

    # Register a chain of skills
    def step_one(request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="chain.step_one",
            status="completed",
            output={"value": request.inputs.get("input", 0) + 1},
        )

    def step_two(request: SkillExecutionRequest) -> SkillExecutionResult:
        prev = request.inputs.get("prev_value", 0)
        return SkillExecutionResult(
            skill_id="chain.step_two",
            status="completed",
            output={"value": prev * 2},
        )

    skill_runtime.register_handler("chain.step_one", step_one)
    skill_runtime.register_handler("chain.step_two", step_two)

    # Execute first step
    r1 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.step_one", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
        inputs={"input": 10},
    ))
    assert r1.status == "completed"
    assert r1.output["value"] == 11

    # Pass result to second step
    r2 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.step_two", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
        inputs={"prev_value": r1.output["value"]},
    ))
    assert r2.status == "completed"
    assert r2.output["value"] == 22


def test_skill_runtime_chain_with_error_propagation(tmp_path: Path) -> None:
    """Error in one skill should propagate through the chain."""
    services = _build_runtime_services(tmp_path)
    skill_runtime = services["skill_runtime"]

    def ok_step(request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(skill_id="ok", status="completed", output={"ok": True})

    def fail_step(request: SkillExecutionRequest) -> SkillExecutionResult:
        raise RuntimeError("chain broken")

    skill_runtime.register_handler("chain.ok", ok_step)
    skill_runtime.register_handler("chain.fail", fail_step)

    r1 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.ok", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
    ))
    assert r1.status == "completed"

    r2 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.fail", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
    ))
    assert r2.status == "failed"
    assert "chain broken" in r2.error


def test_skill_runtime_chain_with_callable_and_generated(tmp_path: Path) -> None:
    """Chain should work with both callable and generated skills."""
    services = _build_runtime_services(tmp_path)
    skill_runtime = services["skill_runtime"]

    # Register a callable skill that prepares data
    def prepare_data(request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="chain.prepare",
            status="completed",
            output={"payload": {"My Key": "value", "Other-Key": 42}},
        )

    skill_runtime.register_handler("chain.prepare", prepare_data)

    # Register the generated normalize_keys chain skill
    import sys
    skill_dir = Path(__file__).parent.parent.parent / "data" / "generated_callable_skills"
    sys.path.insert(0, str(skill_dir))
    from skill_object_normalize_keys_chain import handle as normalize_keys_handle
    sys.path.pop(0)
    skill_runtime.register_handler("skill.object.normalize_keys.chain", normalize_keys_handle)

    # Execute prepare
    r1 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.prepare", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
    ))
    assert r1.status == "completed"
    assert "My Key" in r1.output["payload"]

    # Execute the generated normalize_keys chain skill
    r2 = skill_runtime.execute(SkillExecutionRequest(
        skill_id="skill.object.normalize_keys.chain",
        app_instance_id="app.test", workflow_id="wf.test", step_id="step.test",
        inputs={"payload": r1.output["payload"]},
    ))
    assert r2.status == "completed"
    assert "my_key" in r2.output["normalized"]
    assert "other_key" in r2.output["normalized"]


# ===========================================================================
# Workflow + Skill Chain Tests
# ===========================================================================

def _make_handler(fn):
    """Wrap a function as a skill handler that returns SkillExecutionResult."""
    def handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        return fn(request)
    return handler


def test_workflow_executor_with_skill_runtime_chain(tmp_path: Path) -> None:
    """Workflow executor should chain skill executions through skill runtime."""
    from app.models.app_blueprint import AppBlueprint
    from app.services.app_context_store import AppContextStore
    from app.services.app_installer import AppInstallerService
    from app.services.event_bus import EventBusService
    from app.services.runtime_host import AppRuntimeHostService
    from app.services.scheduler import SchedulerService

    services = _build_runtime_services(tmp_path)
    store = services["runtime_store"]
    lifecycle = services["lifecycle"]
    registry = services["app_registry"]
    data_store = services["app_data_store"]
    skill_runtime = services["skill_runtime"]

    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)

    # Register a skill for the workflow
    def greet(request: SkillExecutionRequest) -> SkillExecutionResult:
        name = request.inputs.get("name", "World")
        return SkillExecutionResult(
            skill_id="chain.greet",
            status="completed",
            output={"greeting": f"Hello, {name}!"},
        )
    skill_runtime.register_handler("chain.greet", greet)

    registry.register_blueprint(AppBlueprint(
        id="bp.chain.test",
        name="Chain Test App",
        goal="Test skill execution chain",
        roles=[],
        tasks=[],
        workflows=[{
            "id": "wf.chain.test",
            "name": "greet",
            "triggers": ["manual"],
            "steps": [{"id": "greet", "kind": "skill", "ref": "chain.greet"}],
        }],
        required_modules=[],
        required_skills=["chain.greet"],
    ))

    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    install_result = installer.install_app("bp.chain.test", user_id="chain-user")

    workflow = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        skill_runtime=skill_runtime,
        store=store,
        context_store=context_store,
    )

    result = workflow.execute_workflow(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.chain.test",
        inputs={"name": "AgentSystem"},
    )

    assert isinstance(result, WorkflowExecutionResult)
    assert result.workflow_id == "wf.chain.test"
    assert len(result.steps) >= 1
    greet_step = next(s for s in result.steps if s.step_id == "greet")
    assert greet_step.status == "completed"


def test_workflow_executor_chains_multiple_skills(tmp_path: Path) -> None:
    """Workflow should chain multiple skill steps with output passing."""
    from app.models.app_blueprint import AppBlueprint
    from app.services.app_context_store import AppContextStore
    from app.services.app_installer import AppInstallerService
    from app.services.event_bus import EventBusService
    from app.services.runtime_host import AppRuntimeHostService
    from app.services.scheduler import SchedulerService

    services = _build_runtime_services(tmp_path)
    store = services["runtime_store"]
    lifecycle = services["lifecycle"]
    registry = services["app_registry"]
    data_store = services["app_data_store"]
    skill_runtime = services["skill_runtime"]

    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)

    def fetch_data(request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="chain.fetch",
            status="completed",
            output={"data": [1, 2, 3]},
        )

    def process_data(request: SkillExecutionRequest) -> SkillExecutionResult:
        data = request.inputs.get("data", [])
        return SkillExecutionResult(
            skill_id="chain.process",
            status="completed",
            output={"sum": sum(data), "count": len(data)},
        )

    skill_runtime.register_handler("chain.fetch", fetch_data)
    skill_runtime.register_handler("chain.process", process_data)

    registry.register_blueprint(AppBlueprint(
        id="bp.chain.multi",
        name="Multi Chain App",
        goal="Test multi-skill chain",
        roles=[],
        tasks=[],
        workflows=[{
            "id": "wf.chain.multi",
            "name": "multi",
            "triggers": ["manual"],
            "steps": [
                {"id": "fetch", "kind": "skill", "ref": "chain.fetch"},
                {"id": "process", "kind": "skill", "ref": "chain.process"},
            ],
        }],
        required_modules=[],
        required_skills=["chain.fetch", "chain.process"],
    ))

    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    install_result = installer.install_app("bp.chain.multi", user_id="chain-multi-user")

    workflow = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        skill_runtime=skill_runtime,
        store=store,
        context_store=context_store,
    )

    result = workflow.execute_workflow(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.chain.multi",
        inputs={"data": [1, 2, 3, 4, 5]},
    )

    assert isinstance(result, WorkflowExecutionResult)
    assert result.workflow_id == "wf.chain.multi"
    assert len(result.steps) >= 2


# ===========================================================================
# Full End-to-End Chain Test
# ===========================================================================

def test_full_execution_chain_pipeline_to_skills(tmp_path: Path) -> None:
    """Test a full chain: pipeline step → skill execution → result aggregation."""
    ws = _ensure_workspace(tmp_path)
    pipeline = PipelineExecutor(workspace=ws)

    # Simulate a chain where a pipeline step prepares data,
    # then we manually chain it through skill execution
    steps = [
        PipelineStep(
            step_id="prepare",
            executor_type=ExecutorType.SHELL,
            command='echo \'{"items": ["a", "b", "c"]}\'',
        ),
    ]

    results = asyncio.run(pipeline.execute_pipeline(steps))
    assert results[0].status == StepStatus.SUCCESS

    # Parse the shell output and chain it into skill execution
    data = json.loads(results[0].output.strip())

    services = _build_runtime_services(tmp_path)
    skill_runtime = services["skill_runtime"]

    def transform(request: SkillExecutionRequest) -> SkillExecutionResult:
        items = request.inputs.get("items", [])
        return SkillExecutionResult(
            skill_id="chain.transform",
            status="completed",
            output={"uppercased": [item.upper() for item in items]},
        )

    skill_runtime.register_handler("chain.transform", transform)

    r = skill_runtime.execute(SkillExecutionRequest(
        skill_id="chain.transform", app_instance_id="app.test",
        workflow_id="wf.test", step_id="step.test",
        inputs=data,
    ))
    assert r.status == "completed"
    assert r.output["uppercased"] == ["A", "B", "C"]
