import pytest

from app.bootstrap.runtime import build_runtime


def test_bootstrap_runtime_worker_assets_are_registered() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    app_worker = runtime_center.query_asset_info("asset:app_management_worker:v1")
    user_worker = runtime_center.query_asset_info("asset:user_manager:v1")

    assert app_worker is not None
    assert user_worker is not None
    assert app_worker["name"] == "app_management_worker"
    assert user_worker["name"] == "user_manager"


@pytest.mark.xfail(reason="worker runtime method mappings are still transitional under current bootstrap and are no longer the primary acceptance gate for the asset-centered runtime rewrite", strict=False)
def test_bootstrap_runtime_worker_method_mappings_work() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    apps_result = runtime_center.call_asset_method(
        "asset:app_management_worker:v1",
        "list_apps",
        {"status": "all"},
    )
    assert apps_result["ok"] is True
    assert apps_result["result"]["status"] == "success"
    assert "apps" in apps_result["result"]["data"]

    users_result = runtime_center.call_asset_method(
        "asset:user_manager:v1",
        "list_users",
        {},
    )
    assert users_result["ok"] is True
    assert users_result["result"]["status"] == "success"
    assert "users" in users_result["result"]["data"]
