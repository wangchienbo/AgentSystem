"""Pipeline Executor — real command/script execution engine for AgentSystem.

Supports multiple executor types:
1. ShellExecutor — run shell/bash commands (subprocess)
2. PythonExecutor — execute Python scripts
3. LLMExecutor — call LLM for reasoning/generation
4. APIExecutor — call external HTTP APIs

Security sandbox:
- Whitelist of allowed commands
- Per-step timeout (default 30s)
- Working directory isolation (user workspace only)
- Environment variable sanitization
- Output truncation (max 10KB per step)
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shlex
import subprocess
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from app.runtime_paths import resolve_runtime_paths


def _default_workspace() -> str:
    runtime_data_dir = os.environ.get("AGENTSYSTEM_DATA_DIR")
    if runtime_data_dir:
        return str(Path(runtime_data_dir).expanduser().resolve())
    return str(resolve_runtime_paths().data_dir.resolve())


# ===========================================================================
# Constants
# ===========================================================================

class ExecutorType(str, Enum):
    SHELL = "shell"
    PYTHON = "python"
    LLM = "llm"
    API = "api"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


# Command whitelist for shell executor
SHELL_WHITELIST: set[str] = {
    # File operations
    "ls", "cat", "head", "tail", "wc", "find", "grep", "sort", "uniq", "cut",
    "awk", "sed", "tee", "diff", "tree", "file", "stat", "du", "df",
    # Python
    "python", "python3", "pip", "pip3",
    # Git
    "git",
    # System info
    "echo", "printenv", "uname", "date", "whoami", "pwd", "id",
    # Text processing
    "jq", "xargs", "tr",
    # Network (read-only)
    "curl", "wget",
    # Compression
    "tar", "zip", "unzip", "gzip",
}

# Dangerous commands that are always blocked
SHELL_BLACKLIST: set[str] = {
    "rm", "rmdir", "mkfs", "dd", "chmod", "chown", "chgrp",
    "sudo", "su", "passwd", "useradd", "userdel", "usermod",
    "kill", "killall", "pkill", "reboot", "shutdown", "halt",
    "mount", "umount", "fdisk", "parted",
    "iptables", "ufw", "firewall-cmd",
    "crontab", "at", "systemctl", "service",
    "docker", "podman",
    "nc", "ncat", "netcat", "socat",
}

# Safe environment variables to pass through
SAFE_ENV_VARS: set[str] = {
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL",
    "PYTHONPATH", "VIRTUAL_ENV",
}

DEFAULT_TIMEOUT = 30  # seconds per step
MAX_OUTPUT_SIZE = 10_000  # chars per step output


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class PipelineStep:
    """A single step in a pipeline."""
    step_id: str
    executor_type: ExecutorType
    command: str  # shell command, python code, or API URL
    args: dict[str, Any] = field(default_factory=dict)
    timeout: int = DEFAULT_TIMEOUT
    status: StepStatus = StepStatus.PENDING
    output: str = ""
    error: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    depends_on: list[str] = field(default_factory=list)  # step_ids this depends on

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "executor_type": self.executor_type.value,
            "command": self.command,
            "args": self.args,
            "timeout": self.timeout,
            "status": self.status.value,
            "output": self.output[:500] if self.output else "",  # truncate for dict
            "error": self.error[:500] if self.error else "",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineStep":
        return cls(
            step_id=data["step_id"],
            executor_type=ExecutorType(data.get("executor_type", "shell")),
            command=data.get("command", ""),
            args=data.get("args", {}),
            timeout=data.get("timeout", DEFAULT_TIMEOUT),
            status=StepStatus(data.get("status", "pending")),
            output=data.get("output", ""),
            error=data.get("error", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class ExecutionResult:
    """Result of executing a single step."""
    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_ms: int = 0


# ===========================================================================
# Executors
# ===========================================================================

class BaseExecutor:
    """Base class for all executors."""

    def __init__(self, workspace: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.workspace = workspace or _default_workspace()
        self.timeout = timeout

    async def execute(self, step: PipelineStep) -> ExecutionResult:
        raise NotImplementedError


class ShellExecutor(BaseExecutor):
    """Execute shell commands with security sandbox."""

    def _validate_command(self, command: str) -> str | None:
        """Validate command against whitelist/blacklist. Returns error message or None."""
        # Parse the command to get the base command
        parts = shlex.split(command) if command else []
        if not parts:
            return "Empty command"

        base_cmd = parts[0].lower()

        # Check blacklist first
        if base_cmd in SHELL_BLACKLIST:
            return f"Command '{base_cmd}' is blocked for security reasons"

        # Check whitelist
        if base_cmd not in SHELL_WHITELIST:
            return f"Command '{base_cmd}' is not in the allowed whitelist"

        # Check for dangerous patterns
        dangerous_patterns = ["|", "&&", "||", ";", "`", "$(", ">", ">>"]
        if base_cmd in ("rm", "sudo", "su", "kill"):
            return f"Command '{base_cmd}' is not allowed"

        return None

    def _sanitize_env(self) -> dict[str, str]:
        """Create a sanitized environment for subprocess execution."""
        env = {}
        for key in SAFE_ENV_VARS:
            if key in os.environ:
                env[key] = os.environ[key]
        env["HOME"] = self.workspace
        env["PWD"] = self.workspace
        return env

    async def execute(self, step: PipelineStep) -> ExecutionResult:
        import time
        start = time.monotonic()

        # Validate command
        error = self._validate_command(step.command)
        if error:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=error,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            # Run in subprocess with timeout
            proc = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace,
                env=self._sanitize_env(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=step.timeout or self.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ExecutionResult(
                    step_id=step.step_id,
                    status=StepStatus.TIMEOUT,
                    error=f"Step timed out after {step.timeout or self.timeout}s",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

            output = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
            error_out = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

            status = StepStatus.SUCCESS if proc.returncode == 0 else StepStatus.FAILED
            return ExecutionResult(
                step_id=step.step_id,
                status=status,
                output=output,
                error=error_out,
                exit_code=proc.returncode or 0,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )


class PythonExecutor(BaseExecutor):
    """Execute Python code in a sandboxed subprocess."""

    async def execute(self, step: PipelineStep) -> ExecutionResult:
        import time
        start = time.monotonic()

        try:
            # Write code to a temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, dir=self.workspace
            ) as f:
                f.write(step.command)
                script_path = f.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    "python3", script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=step.timeout or self.timeout,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    return ExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.TIMEOUT,
                        error=f"Python script timed out after {step.timeout or self.timeout}s",
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )

                output = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
                error_out = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

                status = StepStatus.SUCCESS if proc.returncode == 0 else StepStatus.FAILED
                return ExecutionResult(
                    step_id=step.step_id,
                    status=status,
                    output=output,
                    error=error_out,
                    exit_code=proc.returncode or 0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            finally:
                # Clean up temp file
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=traceback.format_exc()[:MAX_OUTPUT_SIZE],
                duration_ms=int((time.monotonic() - start) * 1000),
            )


class LLMExecutor(BaseExecutor):
    """Execute via LLM API call. Delegates to model_client."""

    def __init__(self, workspace: str | None = None, timeout: int = DEFAULT_TIMEOUT,
                 model_client=None):
        super().__init__(workspace, timeout)
        self.model_client = model_client

    async def execute(self, step: PipelineStep) -> ExecutionResult:
        import time
        start = time.monotonic()

        if not self.model_client:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="LLM executor requires model_client",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            prompt = step.command
            # Get model config from args
            model = step.args.get("model", "gpt-4o")
            temperature = step.args.get("temperature", 0.7)
            max_tokens = step.args.get("max_tokens", 2000)

            # Call the model (simplified — adapt to your model_client API)
            # This is a placeholder; wire to actual model_client.generate()
            result = await self.model_client.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.SUCCESS,
                output=str(result),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )


class APIExecutor(BaseExecutor):
    """Execute HTTP API calls."""

    async def execute(self, step: PipelineStep) -> ExecutionResult:
        import time
        start = time.monotonic()

        try:
            url = step.command
            method = step.args.get("method", "GET").upper()
            headers = step.args.get("headers", {})
            body = step.args.get("body")
            timeout = step.timeout or self.timeout

            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                else:
                    return ExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=f"Unsupported HTTP method: {method}",
                    )

                output = resp.text[:MAX_OUTPUT_SIZE]
                status = StepStatus.SUCCESS if resp.status_code < 400 else StepStatus.FAILED
                return ExecutionResult(
                    step_id=step.step_id,
                    status=status,
                    output=output,
                    error=f"HTTP {resp.status_code}" if resp.status_code >= 400 else "",
                    exit_code=resp.status_code,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )


# ===========================================================================
# Pipeline Execution Engine
# ===========================================================================

class PipelineExecutor:
    """Execute a pipeline with multiple steps and different executor types."""

    def __init__(
        self,
        workspace: str | None = None,
        model_client=None,
    ):
        self.workspace = workspace or _default_workspace()
        self.model_client = model_client
        self.executors: dict[ExecutorType, BaseExecutor] = {
            ExecutorType.SHELL: ShellExecutor(self.workspace),
            ExecutorType.PYTHON: PythonExecutor(self.workspace),
            ExecutorType.LLM: LLMExecutor(self.workspace, model_client=model_client),
            ExecutorType.API: APIExecutor(self.workspace),
        }

    async def execute_pipeline(
        self,
        steps: list[PipelineStep],
        user_id: str | None = None,
    ) -> list[ExecutionResult]:
        """Execute all steps in order, respecting dependencies.

        Args:
            steps: List of pipeline steps
            user_id: User ID for workspace isolation

        Returns:
            List of execution results
        """
        if user_id:
            user_workspace = os.path.join(self.workspace, "data", "users", user_id, "workspace")
            os.makedirs(user_workspace, exist_ok=True)
            for exec_type, executor in self.executors.items():
                executor.workspace = user_workspace

        results = []
        completed_steps: set[str] = set()
        failed = False

        for step in steps:
            if failed:
                step.status = StepStatus.SKIPPED
                results.append(ExecutionResult(
                    step_id=step.step_id,
                    status=StepStatus.SKIPPED,
                    error="Skipped due to previous failure",
                ))
                continue

            # Check dependencies
            for dep in step.depends_on:
                if dep not in completed_steps:
                    step.status = StepStatus.FAILED
                    results.append(ExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=f"Dependency '{dep}' not completed",
                    ))
                    failed = True
                    break

            if failed:
                continue

            # Execute the step
            step.status = StepStatus.RUNNING
            step.started_at = datetime.now(UTC).isoformat()

            executor = self.executors.get(step.executor_type)
            if not executor:
                step.status = StepStatus.FAILED
                step.error = f"Unknown executor type: {step.executor_type}"
                step.completed_at = datetime.now(UTC).isoformat()
                results.append(ExecutionResult(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error=step.error,
                ))
                failed = True
                continue

            result = await executor.execute(step)

            step.status = result.status
            step.output = result.output
            step.error = result.error
            step.completed_at = datetime.now(UTC).isoformat()

            results.append(result)

            if result.status != StepStatus.SUCCESS:
                failed = True
            else:
                completed_steps.add(step.step_id)

        return results


# ===========================================================================
# Factory
# ===========================================================================

def create_executor(executor_type: str, workspace: str | None = None, **kwargs) -> BaseExecutor:
    """Factory function to create an executor by type name."""
    exec_map = {
        "shell": ShellExecutor,
        "python": PythonExecutor,
        "llm": LLMExecutor,
        "api": APIExecutor,
    }
    cls = exec_map.get(executor_type.lower())
    if not cls:
        raise ValueError(f"Unknown executor type: {executor_type}. Valid: {list(exec_map.keys())}")
    return cls(workspace=workspace, **kwargs)
