from __future__ import annotations

from app.bootstrap.runtime import build_runtime


def test_bootstrap_runtime_deeper_assets_are_registered() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    refinement_worker = runtime_center.query_asset_info("asset:refinement_worker:v1")
    package_manager = runtime_center.query_asset_info("asset:package_manager:v1")

    assert refinement_worker is not None
    assert package_manager is not None
    assert refinement_worker["name"] == "refinement_worker"
    assert package_manager["name"] == "package_manager"


def test_bootstrap_runtime_deeper_method_mappings_work() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    package_result = runtime_center.call_asset_method(
        "asset:package_manager:v1",
        "package_list_installed",
        {},
    )
    assert package_result["ok"] is True
    assert "packages" in package_result["result"]

    search_result = runtime_center.call_asset_method(
        "asset:package_manager:v1",
        "package_search",
        {"query": "app"},
    )
    assert search_result["ok"] is True
    assert "packages" in search_result["result"]
