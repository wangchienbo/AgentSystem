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


def test_bootstrap_runtime_write_path_capabilities_are_exposed() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    app_worker = runtime_center.query_asset_info("asset:app_management_worker:v1")
    package_manager = runtime_center.query_asset_info("asset:package_manager:v1")

    app_methods = {cap["method"] for cap in app_worker["capabilities"]}
    package_methods = {cap["method"] for cap in package_manager["capabilities"]}

    assert {"start_app", "stop_app", "delete_app", "uninstall_app"}.issubset(app_methods)
    assert {"package_build", "package_install", "package_uninstall", "package_rollback"}.issubset(package_methods)


def test_bootstrap_runtime_write_paths_return_structured_results() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    build_result = runtime_center.call_asset_method(
        "asset:package_manager:v1",
        "package_build",
        {"asset_id": "app.workspace.assistant"},
    )
    assert build_result["ok"] is True
    assert build_result["result"]["asset_id"] == "app.workspace.assistant"
    assert "build_hash" in build_result["result"]

    uninstall_result = runtime_center.call_asset_method(
        "asset:package_manager:v1",
        "package_uninstall",
        {"asset_id": "app.workspace.assistant"},
    )
    assert uninstall_result["ok"] is True
    assert uninstall_result["result"] is None

    rollback_fail = runtime_center.call_asset_method(
        "asset:package_manager:v1",
        "package_rollback",
        {"asset_id": "app.workspace.assistant", "target_version": "0.0.0"},
    )
    assert rollback_fail["ok"] is True
    assert rollback_fail["result"] is None
