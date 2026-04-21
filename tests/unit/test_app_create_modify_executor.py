from __future__ import annotations

import pytest

from app.models.chat import InterpretedCommand
from app.services.app_command_service import AppCommandService
from app.services.app_create_modify_executor import AppCreateModifyExecutor
from app.services.app_presenter import AppPresenter


def _make_executor(*, bus=None):
    return AppCreateModifyExecutor(
        command_service=AppCommandService(),
        presenter=AppPresenter(),
        bus=bus,
        config_center=None,
        persistence=None,
        lifecycle=None,
        runtime_host=None,
        app_registry=None,
        catalog=None,
        app_refinement_orchestrator=object(),
        resolve_instance_id=lambda x: x,
        resolve_display_name=lambda target, _: target,
        check_app_modify_permission=lambda user_id, target: {"allowed": True, "can_create_skills": True, "message": "ok"},
    )


@pytest.mark.asyncio
async def test_app_create_modify_executor_modify_confirm_shows_phase_h_context_summary() -> None:
    executor = _make_executor()
    command = InterpretedCommand(
        intent="modify_app",
        target_app="novel",
        parameters={
            "modification": "改成深色主题",
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
        user_id="u1",
    )

    response = await executor.handle_modify_app(command, "sess-1", [])

    assert response.type == "confirm"
    assert "上下文摘要:" in response.content
    assert "target_app=novel" in response.content
    assert "context_hints=recent:App: novel" in response.content


@pytest.mark.asyncio
async def test_app_create_modify_executor_modify_degraded_shows_phase_h_context_summary() -> None:
    executor = _make_executor(bus=None)
    command = InterpretedCommand(
        intent="modify_app",
        target_app="novel",
        parameters={
            "confirmed": True,
            "modification": "改成深色主题",
            "target_app": "novel",
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
        user_id="u1",
    )

    response = await executor.handle_modify_app(command, "sess-1", [])

    assert response.type == "text"
    assert "上下文摘要:" in response.content
    assert "target_app=novel" in response.content
    assert "related_session_ids=sess-1,sess-2" in response.content
