from pathlib import Path

from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.models.skill_runtime import SkillExecutionRequest
from app.services.executable_skill_adapter import ExecutableSkillAdapter, ExecutableSkillAdapterError
from app.services.skill_runtime import SkillRuntimeService


def _write_script(path: Path, content: str) -> str:
    path.write_text(content)
    return str(path)


def _entry(skill_id: str, entrypoint: str) -> SkillRegistryEntry:
    return SkillRegistryEntry(
        skill_id=skill_id,
        name=skill_id,
        active_version="0.1.0",
        versions=[SkillVersion(version="0.1.0", content="generated")],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="executable",
        manifest=SkillManifest(
            skill_id=skill_id,
            name=skill_id,
            version="0.1.0",
            description="executable test",
            runtime_adapter="executable",
            adapter=SkillAdapterSpec(kind="executable", command=["python3"], entry=entrypoint, invocation_protocol="json_stdio"),
            contract=SkillContractRef(),
            tags=["test"],
        ),
    )


def test_executable_skill_adapter_executes_json_stdio_script(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path / "echo_skill.py",
        "import json,sys\nreq=json.loads(sys.stdin.read())\njson.dump({'skill_id': req['skill_id'], 'status': 'completed', 'output': {'echo': req['inputs']['text']}}, sys.stdout)\n",
    )
    entry = _entry("skill.exec.echo", script_path)
    adapter = ExecutableSkillAdapter()

    result = adapter.execute(
        entry,
        SkillExecutionRequest(
            skill_id="skill.exec.echo",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec",
            inputs={"text": "hello"},
            config={},
        ),
    )

    assert result.status == "completed"
    assert result.output["echo"] == "hello"


def test_skill_runtime_supports_executable_adapter_entry(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path / "slug_skill.py",
        "import json,sys\nreq=json.loads(sys.stdin.read())\ntext=req['inputs'].get('text','')\njson.dump({'skill_id': req['skill_id'], 'status': 'completed', 'output': {'slug': text.lower().replace(' ','-')}}, sys.stdout)\n",
    )
    entry = _entry("skill.exec.slug", script_path)
    runtime = SkillRuntimeService()
    runtime.register_handler("skill.exec.slug", lambda request: None, entry=entry)

    result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.exec.slug",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec",
            inputs={"text": "Hello World"},
            config={},
        )
    )

    assert result.status == "completed"
    assert result.output["slug"] == "hello-world"


def test_skill_runtime_maps_invalid_executable_output_to_failure(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path / "bad_skill.py",
        "import sys\nsys.stdout.write('not-json')\n",
    )
    entry = _entry("skill.exec.bad", script_path)
    runtime = SkillRuntimeService()
    runtime.register_handler("skill.exec.bad", lambda request: None, entry=entry)

    result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.exec.bad",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec",
            inputs={},
            config={},
        )
    )

    assert result.status == "failed"
    assert result.error_detail["kind"] == "executable_adapter_error"
    assert result.error_detail["subkind"] == "invalid_json"


def test_executable_skill_adapter_reports_missing_entrypoint(tmp_path: Path) -> None:
    missing_path = str(tmp_path / "missing.py")
    entry = _entry("skill.exec.missing", missing_path)
    adapter = ExecutableSkillAdapter()

    try:
        adapter.execute(
            entry,
            SkillExecutionRequest(
                skill_id="skill.exec.missing",
                app_instance_id="app.exec",
                workflow_id="wf.exec",
                step_id="step.exec",
                inputs={},
                config={},
            ),
        )
    except ExecutableSkillAdapterError as error:
        assert error.kind == "entrypoint_missing"
        assert error.detail["entrypoint"] == missing_path
    else:
        raise AssertionError("expected missing entrypoint error")


def test_skill_runtime_maps_timeout_and_non_zero_exit_details(tmp_path: Path) -> None:
    slow_script_path = _write_script(
        tmp_path / "slow_skill.py",
        "import time\ntime.sleep(2)\n",
    )
    timeout_entry = _entry("skill.exec.timeout", slow_script_path)
    timeout_entry.manifest.adapter.timeout_seconds = 1
    runtime = SkillRuntimeService()
    runtime.register_handler("skill.exec.timeout", lambda request: None, entry=timeout_entry)

    timeout_result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.exec.timeout",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec.timeout",
            inputs={},
            config={},
        )
    )

    assert timeout_result.status == "failed"
    assert timeout_result.error_detail["subkind"] == "timeout"
    assert timeout_result.error_detail["timeout_seconds"] == 1

    failing_script_path = _write_script(
        tmp_path / "failing_skill.py",
        "import sys\nsys.stderr.write('boom stderr')\nsys.exit(3)\n",
    )
    failing_entry = _entry("skill.exec.fail", failing_script_path)
    runtime.register_handler("skill.exec.fail", lambda request: None, entry=failing_entry)

    failing_result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.exec.fail",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec.fail",
            inputs={},
            config={},
        )
    )

    assert failing_result.status == "failed"
    assert failing_result.error_detail["subkind"] == "non_zero_exit"
    assert failing_result.error_detail["returncode"] == 3
    assert "boom stderr" in failing_result.error_detail["stderr_preview"]


def test_skill_runtime_maps_skill_id_mismatch(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path / "mismatch_skill.py",
        "import json,sys\nreq=json.loads(sys.stdin.read())\njson.dump({'skill_id': 'other.skill', 'status': 'completed', 'output': {}}, sys.stdout)\n",
    )
    entry = _entry("skill.exec.mismatch", script_path)
    runtime = SkillRuntimeService()
    runtime.register_handler("skill.exec.mismatch", lambda request: None, entry=entry)

    result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.exec.mismatch",
            app_instance_id="app.exec",
            workflow_id="wf.exec",
            step_id="step.exec.mismatch",
            inputs={},
            config={},
        )
    )

    assert result.status == "failed"
    assert result.error_detail["subkind"] == "skill_id_mismatch"
    assert result.error_detail["expected_skill_id"] == "skill.exec.mismatch"
    assert result.error_detail["returned_skill_id"] == "other.skill"
