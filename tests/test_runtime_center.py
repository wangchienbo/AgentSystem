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
    entry.metadata["last_heartbeat"] = "2000-01-01T00:00:00+00:00"
    center._entries["app.qa"] = entry  # intentional white-box test

    expired = center.cleanup_expired(timeout_seconds=1)
    assert expired == ["app.qa"]
    assert center.get("app.qa").status == "crashed"


def test_runtime_center_register_and_persist_session_entity(tmp_path) -> None:
    path = tmp_path / "runtime_center.json"
    center = RuntimeCenter(data_file=str(path))
    node = center.register_session(session_id="sess-root", user_id="u1", channel="webchat")

    assert node.session_id == "sess-root"
    assert node.root_session_id == "sess-root"
    assert center.get_session("sess-root") is not None

    restored = RuntimeCenter(data_file=str(path))
    restored_node = restored.get_session("sess-root")
    assert restored_node is not None
    assert restored_node.user_id == "u1"


def test_runtime_center_list_sessions_by_user(tmp_path) -> None:
    center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))
    center.register_session(session_id="sess-a", user_id="u1", channel="webchat")
    center.register_session(session_id="sess-b", user_id="u2", channel="qqbot")

    assert len(center.list_sessions()) == 2
    assert [node.session_id for node in center.list_sessions(user_id="u1")] == ["sess-a"]
