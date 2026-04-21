from __future__ import annotations

from app.system.workers.refinement import RefinementWorker


class _FakeRefinementOrchestrator:
    def __init__(self):
        self.calls = []

    def refine(self, *, app_instance_id: str, modification: str):
        self.calls.append({
            "app_instance_id": app_instance_id,
            "modification": modification,
        })
        return {"refined": True, "app_instance_id": app_instance_id, "modification": modification}


def test_refinement_worker_refine_app_uses_target_app_param_and_carries_phase_h_context() -> None:
    orch = _FakeRefinementOrchestrator()
    worker = RefinementWorker(refinement_orchestrator=orch)

    result = worker.execute("refine_app", "", {
        "target_app": "novel",
        "modification": "改成深色主题",
        "context_hints": ["recent:App: novel"],
        "related_session_ids": ["sess-1", "sess-2"],
    })

    assert result["status"] == "success"
    assert orch.calls[-1]["app_instance_id"] == "novel"
    assert result["data"]["target_app"] == "novel"
    assert result["data"]["context_hints"] == ["recent:App: novel"]
    assert result["data"]["related_session_ids"] == ["sess-1", "sess-2"]
