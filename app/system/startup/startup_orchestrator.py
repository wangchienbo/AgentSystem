from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class StartupOrchestratorError(RuntimeError):
    pass


@dataclass(frozen=True)
class StartupStage:
    name: str
    action: Callable[[], Any]
    required: bool = True
    depends_on: tuple[str, ...] = ()
    ready_check: Callable[[dict[str, Any]], tuple[bool, dict[str, Any]]] | None = None


@dataclass
class StartupStageResult:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)


class StartupOrchestrator:
    def __init__(self) -> None:
        self._stages: list[StartupStage] = []
        self._stage_index: dict[str, StartupStage] = {}
        self._results: list[StartupStageResult] = []
        self._ready: set[str] = set()

    def add_stage(self, stage: StartupStage) -> None:
        self._stages.append(stage)
        self._stage_index[stage.name] = stage

    def _run_stage(self, stage: StartupStage, *, recovered: bool = False) -> StartupStageResult:
        missing = [dep for dep in stage.depends_on if dep not in self._ready]
        if missing:
            raise StartupOrchestratorError(
                f"Stage {stage.name} blocked, missing dependencies: {', '.join(missing)}"
            )
        try:
            value = stage.action()
            detail = value if isinstance(value, dict) else {"value": value}
            if stage.ready_check is not None:
                ok, ready_detail = stage.ready_check(detail)
                detail = {**detail, **ready_detail}
                if not ok:
                    raise StartupOrchestratorError(
                        f"Stage {stage.name} not ready: {ready_detail.get('reason', 'ready_check_failed')}"
                    )
            if recovered:
                detail = {**detail, "recovered": True}
            result = StartupStageResult(name=stage.name, status="ready", detail=detail)
            self._ready.add(stage.name)
            return result
        except Exception as exc:
            return StartupStageResult(
                name=stage.name,
                status="failed",
                detail={"error": str(exc), "error_type": type(exc).__name__, "recovered": recovered},
            )

    def execute(self) -> list[StartupStageResult]:
        self._results = []
        self._ready = set()
        for stage in self._stages:
            result = self._run_stage(stage)
            self._results.append(result)
            if result.status != "ready" and stage.required:
                raise StartupOrchestratorError(
                    f"Stage {stage.name} failed: {result.detail.get('error', 'unknown error')}"
                )
        return list(self._results)

    def rerun_stage(self, stage_name: str) -> StartupStageResult:
        stage = self._stage_index.get(stage_name)
        if stage is None:
            raise StartupOrchestratorError(f"Unknown stage: {stage_name}")
        result = self._run_stage(stage, recovered=True)
        replaced = False
        for idx, existing in enumerate(self._results):
            if existing.name == stage_name:
                self._results[idx] = result
                replaced = True
                break
        if not replaced:
            self._results.append(result)
        if result.status != "ready" and stage.required:
            raise StartupOrchestratorError(
                f"Stage {stage.name} failed during recovery: {result.detail.get('error', 'unknown error')}"
            )
        return result

    def results(self) -> list[StartupStageResult]:
        return list(self._results)

    def ready_stages(self) -> set[str]:
        return set(self._ready)
