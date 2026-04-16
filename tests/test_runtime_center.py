from app.system.catalog.runtime_center import RuntimeCenter


def test_runtime_center_register_heartbeat_unregister(tmp_path) -> None:
    center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))

    entry = center.register(
        asset_id="app.novel",
        version="1.2.0",
        pid=12345,
        endpoint="http://localhost:8001",
        owner="wangchienbo",
    )
    assert entry.asset_id == "app.novel"
    assert center.get("app.novel") is not None
    assert len(center.list_running()) == 1

    assert center.heartbeat("app.novel", pid=12345) is True
    assert center.heartbeat("app.novel", pid=99999) is False

    assert center.unregister("app.novel", pid=12345) is True
    assert center.get("app.novel") is None


def test_runtime_center_cleanup_and_uptime(tmp_path) -> None:
    center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))
    center.register(
        asset_id="app.qa",
        version="0.1.0",
        pid=777,
        endpoint="http://localhost:8002",
        owner="system",
    )
    assert center.get_uptime("app.qa") is not None

    entry = center.get("app.qa")
    assert entry is not None
    entry.last_heartbeat = "2000-01-01T00:00:00+00:00"
    center._entries["app.qa"] = entry  # intentional white-box test

    expired = center.cleanup_expired(timeout_seconds=1)
    assert expired == ["app.qa"]
    assert center.get("app.qa").status == "crashed"
