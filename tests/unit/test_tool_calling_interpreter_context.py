from __future__ import annotations

from app.system.gateway.tool_calling_interpreter import build_session_context


def test_build_session_context_limits_recent_history_window() -> None:
    history = [
        {"role": "user", "content": f"user-{idx}-" + ("x" * 80)} if idx % 2 == 0
        else {"role": "assistant", "content": f"assistant-{idx}-" + ("y" * 80)}
        for idx in range(8)
    ]

    ctx = build_session_context(
        history=history,
        pending_intent=None,
        pending_params={},
        missing_param=None,
        available_apps=[],
        available_assets=None,
    )

    assert "【最近对话】" in ctx
    assert "user-0-" not in ctx
    assert "assistant-1-" not in ctx
    assert "user-6-" in ctx
    assert "assistant-7-" in ctx
    recent_lines = [line for line in ctx.splitlines() if line.startswith("  user:") or line.startswith("  assistant:")]
    assert len(recent_lines) <= 4
    assert len(ctx) < 1000
