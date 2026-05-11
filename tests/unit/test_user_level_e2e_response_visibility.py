from __future__ import annotations

import tests.e2e.test_50_scenarios_20_turns_user_level as harness


class _MixedVisibilityClient:
    def __init__(self) -> None:
        self.calls = 0

    def send_message(self, user_id: str, message: str, session_id: str | None = None, payload=None):
        self.calls += 1
        if self.calls == 1:
            return {"ok": True, "session_id": "session_vis", "response": "visible answer", "content": "visible answer"}
        return {"ok": True, "session_id": "session_vis", "response": "", "content": ""}

    def get_history(self, session_id: str):
        return [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "visible answer"},
            {"role": "user", "content": "two"},
        ]


def test_run_scenario_marks_empty_visible_response_as_failure() -> None:
    scenario = {
        "id": "SV1",
        "name": "visibility",
        "user_id": "user_vis",
        "turns": ["one", "two"],
    }

    result = harness.run_scenario(_MixedVisibilityClient(), scenario, delay=0)

    assert len(result.turns) == 2
    assert result.turns[0].ok is True
    assert result.turns[1].ok is False
    assert result.total_ok == 1
    assert result.total_fail >= 1
