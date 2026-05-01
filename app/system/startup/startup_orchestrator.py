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
        self._results: list[StartupStageResult] = []
        self._ready: set[str] = set()

    def add_stage(self, stage: StartupStage) -> None:
        self._stages.append(stage)

    def execute(self) -> list[StartupStageResult]:
        self._results = []
        self._ready = set()
        for stage in self._stages:
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
                self._results.append(
                    StartupStageResult(name=stage.name, status="ready", detail=detail)
                )
                self._ready.add(stage.name)
            except Exception as exc:
                self._results.append(
                    StartupStageResult(
                        name=stage.name,
                        status="failed",
                        detail={"error": str(exc), "error_type": type(exc).__name__},
                    )
                )
                if stage.required:
                    raise StartupOrchestratorError(
                        f"Stage {stage.name} failed: {exc}"
                    ) from exc
        return list(self._results)

    def results(self) -> list[StartupStageResult]:
        return list(self._results)

    def ready_stages(self) -> set[str]:
        return set(self._ready)
