from __future__ import annotations

from app.bootstrap.runtime import build_runtime


def test_build_runtime_exposes_startup_state_with_ordered_stages() -> None:
    services = build_runtime()
    startup_state = services["startup_state"]

    assert startup_state["ready_stages"] == [
        "asset_center",
        "entrypoints",
        "interaction_runtime",
        "model_runtime",
        "system_assets",
    ]

    stage_names = [item["name"] for item in startup_state["results"]]
    assert stage_names == [
        "asset_center",
        "model_runtime",
        "system_assets",
        "interaction_runtime",
        "entrypoints",
    ]
    assert all(item["status"] == "ready" for item in startup_state["results"])

    by_name = {item["name"]: item for item in startup_state["results"]}
    assert by_name["system_assets"]["detail"]["fully_ready"] is True
    assert by_name["interaction_runtime"]["detail"]["fully_ready"] is True


def test_build_runtime_exposes_startup_rerun_entry() -> None:
    services = build_runtime()
    rerun = services["rerun_startup_stage"]

    refreshed = rerun("interaction_runtime")
    by_name = {item["name"]: item for item in refreshed["results"]}

    assert "interaction_runtime" in refreshed["ready_stages"]
    assert by_name["interaction_runtime"]["detail"]["recovered"] is True
