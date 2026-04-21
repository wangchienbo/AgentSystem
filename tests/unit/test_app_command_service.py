from __future__ import annotations

from app.services.app_command_service import AppCommandService


def test_app_command_service_normalize_modify_app_preserves_phase_h_context() -> None:
    service = AppCommandService()

    normalized = service.normalize_confirmed_params("modify_app", {
        "target_app": "novel",
        "modification": "改成深色主题",
        "context_hints": ["recent:App: novel"],
        "related_session_ids": ["sess-1", "sess-2"],
    })

    assert normalized["target_app"] == "novel"
    assert normalized["parameters"]["context_hints"] == ["recent:App: novel"]
    assert normalized["parameters"]["related_session_ids"] == ["sess-1", "sess-2"]


def test_app_command_service_summarize_phase_h_context() -> None:
    summary = AppCommandService.summarize_phase_h_context({
        "target_app": "novel",
        "context_hints": ["recent:App: novel", "modify theme"],
        "related_session_ids": ["sess-1", "sess-2", "sess-3", "sess-4"],
    })

    assert summary is not None
    assert "target_app=novel" in summary
    assert "context_hints=recent:App: novel | modify theme" in summary
    assert "related_session_ids=sess-1,sess-2,sess-3" in summary
