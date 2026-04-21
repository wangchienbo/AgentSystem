from __future__ import annotations

import pytest

from app.models.chat import InterpretedCommand
from app.services.app_command_service import AppCommandService
from app.services.app_lifecycle_query_executor import AppLifecycleQueryExecutor, AppOperationResolution
from app.services.app_presenter import AppPresenter


def _make_executor(*, bus=None):
    return AppLifecycleQueryExecutor(
        command_service=AppCommandService(),
        presenter=AppPresenter(),
        bus=bus,
        resolve_instance_id=lambda x: x,
        resolve_display_name=lambda target, _: target,
    )


async def _fake_resolve_app_operation(target: str, display_name: str) -> AppOperationResolution:
    return AppOperationResolution(
        target=target,
        display_name=display_name,
        static_found=True,
        static_status="installed",
        runtime_found=True,
        runtime_status="running",
    )


@pytest.mark.asyncio
async def test_app_lifecycle_query_executor_query_detail_shows_phase_h_context_summary() -> None:
    executor = _make_executor(bus=object())
    executor._resolve_app_operation = _fake_resolve_app_operation  # type: ignore[attr-defined]
    command = InterpretedCommand(
        intent="query_app",
        target_app="novel",
        parameters={
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
        user_id="u1",
    )

    response = await executor.handle_query_app(command, "sess-1", [])

    assert response.type == "card"
    assert "上下文摘要:" in response.content
    assert "target_app=novel" in response.content
    assert "context_hints=recent:App: novel" in response.content


@pytest.mark.asyncio
async def test_app_lifecycle_query_executor_query_degraded_shows_phase_h_context_summary() -> None:
    executor = _make_executor(bus=None)
    command = InterpretedCommand(
        intent="query_app",
        target_app="novel",
        parameters={
            "context_hints": ["recent:App: novel"],
            "related_session_ids": ["sess-1", "sess-2"],
        },
        user_id="u1",
    )

    response = await executor.handle_query_app(command, "sess-1", [])

    assert response.type == "text"
    assert "上下文摘要:" in response.content
    assert "target_app=novel" in response.content
    assert "related_session_ids=sess-1,sess-2" in response.content
