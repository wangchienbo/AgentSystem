from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.models.skill_control import SkillRegistryEntry
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


def _preview(text: str, limit: int = 300) -> str:
    value = text.strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


class ExecutableSkillAdapterError(ValueError):
    def __init__(self, message: str, *, kind: str = "executable_adapter_error", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail or {}


class ExecutableSkillAdapter:
    def execute(self, entry: SkillRegistryEntry, request: SkillExecutionRequest) -> SkillExecutionResult:
        manifest = entry.manifest
        if manifest is None:
            raise ExecutableSkillAdapterError(
                f"Executable adapter requires manifest: {entry.skill_id}",
                kind="manifest_missing",
            )
        command = list(manifest.adapter.command)
        if not command:
            raise ExecutableSkillAdapterError(
                f"Executable adapter command missing: {entry.skill_id}",
                kind="command_missing",
            )
        entrypoint = manifest.adapter.entry.strip()
        if entrypoint:
            if not Path(entrypoint).exists():
                raise ExecutableSkillAdapterError(
                    f"Executable skill entrypoint not found: {entrypoint}",
                    kind="entrypoint_missing",
                    detail={"entrypoint": entrypoint},
                )
            command = [*command, entrypoint]
        payload = {
            "skill_id": request.skill_id,
            "version": entry.active_version,
            "inputs": request.inputs,
            "config": request.config,
            "context": {
                "app_instance_id": request.app_instance_id,
                "workflow_id": request.workflow_id,
                "step_id": request.step_id,
            },
        }
        timeout_seconds = manifest.adapter.timeout_seconds
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise ExecutableSkillAdapterError(
                f"Executable skill timed out after {timeout_seconds}s: {entry.skill_id}",
                kind="timeout",
                detail={
                    "timeout_seconds": timeout_seconds,
                    "command": command,
                },
            ) from error
        stdout_preview = _preview(completed.stdout)
        stderr_preview = _preview(completed.stderr)
        if completed.returncode != 0:
            raise ExecutableSkillAdapterError(
                stderr_preview or f"Executable skill failed: {entry.skill_id}",
                kind="non_zero_exit",
                detail={
                    "returncode": completed.returncode,
                    "command": command,
                    "stdout_preview": stdout_preview,
                    "stderr_preview": stderr_preview,
                },
            )
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ExecutableSkillAdapterError(
                f"Executable skill produced invalid JSON: {entry.skill_id}",
                kind="invalid_json",
                detail={
                    "stdout_preview": stdout_preview,
                    "stderr_preview": stderr_preview,
                },
            ) from error
        try:
            result = SkillExecutionResult(**raw)
        except Exception as error:  # noqa: BLE001
            raise ExecutableSkillAdapterError(
                f"Executable skill produced invalid result payload: {entry.skill_id}",
                kind="invalid_result_payload",
                detail={
                    "stdout_preview": stdout_preview,
                    "stderr_preview": stderr_preview,
                },
            ) from error
        if result.skill_id != request.skill_id:
            raise ExecutableSkillAdapterError(
                f"Executable skill returned mismatched skill_id: {entry.skill_id}",
                kind="skill_id_mismatch",
                detail={
                    "expected_skill_id": request.skill_id,
                    "returned_skill_id": result.skill_id,
                },
            )
        return result
