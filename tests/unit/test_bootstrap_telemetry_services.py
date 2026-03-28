from app.bootstrap.runtime import build_runtime


def test_build_runtime_includes_telemetry_services() -> None:
    services = build_runtime()

    assert "collection_policy_service" in services
    assert "upgrade_log_service" in services
    assert "telemetry_service" in services
    assert "evaluation_summary_service" in services
