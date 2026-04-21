from __future__ import annotations

from app.services.app_presenter import AppPresenter


def test_app_presenter_confirmation_content_includes_phase_h_summary() -> None:
    presenter = AppPresenter()

    content = presenter.build_confirmation_content(
        intent="modify_app",
        related_app="novel",
        parameters={
            "modification": "改成深色主题",
            "target_app": "novel",
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
    )

    assert "上下文摘要:" in content
    assert "target_app=novel" in content
    assert "context_hints=recent:App: novel" in content
    assert "related_session_ids=sess-1,sess-2" in content


def test_app_presenter_degraded_response_includes_phase_h_summary() -> None:
    presenter = AppPresenter()

    response = presenter.build_degraded_response(
        intent="modify_app",
        session_id="sess-1",
        related_app="novel",
        reason="install failed",
        parameters={
            "target_app": "novel",
            "context_hints": ["recent:App: novel"],
        },
    )

    assert "上下文摘要:" in response.content
    assert "target_app=novel" in response.content
