from __future__ import annotations

import pytest

from app.models.skill_runtime import SkillExecutionRequest
from app.models.app_refinement import SuggestedSkillRefinementClosureResult
from app.system.workers.system_app_refinement_worker import SystemAppRefinementWorker


class _FakeRefinementService:
    def __init__(self):
        self.requests = []

    def refine_closure(self, request):
        self.requests.append(request)
        return SuggestedSkillRefinementClosureResult(
            blueprint=None,
            app_result=None,
            created_skills=[],
            reused_skill_ids=[],
            diagnostics=[],
        )


@pytest.mark.asyncio
async def test_system_app_refinement_worker_refine_carries_phase_h_context() -> None:
    service = _FakeRefinementService()
    worker = SystemAppRefinementWorker(bus=None, refinement_service=service)

    request = SkillExecutionRequest(
        skill_id="system.app_refinement",
        app_instance_id="bp.novel",
        workflow_id="wf.refine",
        step_id="refine",
        action="refine",
        inputs={
            "app_id": "bp.novel",
            "target_app": "novel",
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
        config={},
        user_id="u1",
    )

    result = await worker.process(request)

    assert result.status == "completed"
    assert service.requests[-1].target_app == "novel"
    assert service.requests[-1].context_hints == ["recent:App: novel"]
    assert service.requests[-1].related_session_ids == ["sess-1", "sess-2"]
    assert result.output["target_app"] == "novel"
    assert result.output["context_hints"] == ["recent:App: novel"]
    assert result.output["related_session_ids"] == ["sess-1", "sess-2"]
