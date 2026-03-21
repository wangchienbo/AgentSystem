import pytest

from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.model_client import ModelClientError
from app.services.skill_runtime import SkillRuntimeError, SkillRuntimeService


def test_skill_runtime_executes_callable_adapter_entry() -> None:
    runtime = SkillRuntimeService()
    entry = SkillRegistryEntry(
        skill_id="skill.callable",
        name="Callable Skill",
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="callable")],
        dependencies=[],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="callable",
        manifest=SkillManifest(
            skill_id="skill.callable",
            name="Callable Skill",
            version="1.0.0",
            description="callable adapter",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.handlers:callable"),
            contract=SkillContractRef(),
            tags=["test"],
        ),
    )

    runtime.register_handler(
        "skill.callable",
        lambda request: SkillExecutionResult(skill_id=request.skill_id, output={"ok": True}),
        entry=entry,
    )

    result = runtime.execute(
        SkillExecutionRequest(skill_id="skill.callable", app_instance_id="app", workflow_id="wf", step_id="step")
    )

    assert result.status == "completed"
    assert result.output["ok"] is True


def test_skill_runtime_executes_script_adapter_entry() -> None:
    runtime = SkillRuntimeService()
    entry = SkillRegistryEntry(
        skill_id="skill.script",
        name="Script Skill",
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="script")],
        dependencies=[],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="script",
        manifest=SkillManifest(
            skill_id="skill.script",
            name="Script Skill",
            version="1.0.0",
            description="script adapter",
            runtime_adapter="script",
            adapter=SkillAdapterSpec(kind="script", command=["python3", "tests/fixtures/script_echo_skill.py"]),
            contract=SkillContractRef(),
            tags=["test"],
        ),
    )

    runtime.register_handler(
        "skill.script",
        lambda request: SkillExecutionResult(skill_id=request.skill_id, output={"ok": True}),
        entry=entry,
    )

    result = runtime.execute(
        SkillExecutionRequest(skill_id="skill.script", app_instance_id="app", workflow_id="wf", step_id="step", inputs={"text": "hello-script"})
    )

    assert result.status == "completed"
    assert result.output["echo"] == "hello-script"
    assert result.output["adapter"] == "script"


def test_skill_runtime_returns_structured_model_client_error() -> None:
    runtime = SkillRuntimeService()
    entry = SkillRegistryEntry(
        skill_id="skill.model",
        name="Model Skill",
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="model")],
        dependencies=[],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="callable",
        manifest=SkillManifest(
            skill_id="skill.model",
            name="Model Skill",
            version="1.0.0",
            description="model adapter",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.handlers:model"),
            contract=SkillContractRef(),
            tags=["test"],
        ),
    )

    def failing_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        raise ModelClientError("upstream 502", status_code=502, retryable=True)

    runtime.register_handler("skill.model", failing_handler, entry=entry)

    result = runtime.execute(
        SkillExecutionRequest(skill_id="skill.model", app_instance_id="app", workflow_id="wf", step_id="step")
    )

    assert result.status == "failed"
    assert result.error_detail["kind"] == "model_client_error"
    assert result.error_detail["status_code"] == 502
    assert result.error_detail["retryable"] is True
