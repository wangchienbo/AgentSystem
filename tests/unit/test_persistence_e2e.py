"""App-level persistence & recovery E2E tests.

Verifies that the persistence service correctly saves and restores the
entire runtime state (app instances, lifecycle events, registry entries,
catalog entries, and session data) across a simulated restart.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.models.app_instance import AppInstance
from app.models.chat import ChatMessageResponse
from app.services.app_catalog import AppCatalogService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.persistence_service import PersistenceService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.light_brain_memory import LightBrainMemory


def test_persistence_service_save_and_restore():
    """Full round-trip: create state → persist → new service → restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        state_dir.mkdir()

        # Phase 1: Create and populate services with real store
        store = RuntimeStateStore(base_dir=str(tmpdir))
        lifecycle = AppLifecycleService(store=store)
        runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=store)
        registry = AppRegistryService(store=store)
        catalog = AppCatalogService()
        memory = LightBrainMemory(data_dir=tmpdir)
        persistence = PersistenceService(data_dir=str(state_dir))

        # Create an app instance
        instance = AppInstance(
            id="test-app-001",
            blueprint_id="bp-test",
            owner_user_id="user-1",
            status="installed",
            execution_mode="pipeline",
            resolved_skills=["skill-a"],
            data_namespace="ns-test",
        )
        runtime_host.register_instance(instance)

        # Create a conversation session
        memory.create_session("user-1", "webchat", "session-001")
        memory.record_user_message("session-001", "Hello")
        memory.record_reply("session-001", ChatMessageResponse(session_id="session-001", type="text", content="Hi!"))

        # Save state
        saved_path = persistence.save_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=registry,
            catalog=catalog,
            light_brain_memory=memory,
        )
        assert saved_path.exists()

        # Phase 2: Simulate restart — create fresh services
        store2 = RuntimeStateStore(base_dir=str(tmpdir))
        lifecycle2 = AppLifecycleService(store=store2)
        runtime_host2 = AppRuntimeHostService(lifecycle=lifecycle2, store=store2)
        registry2 = AppRegistryService(store=store2)
        catalog2 = AppCatalogService()
        memory2 = LightBrainMemory(data_dir=tmpdir)
        persistence2 = PersistenceService(data_dir=str(state_dir))

        # Restore state
        restore = persistence2.restore_state(
            lifecycle=lifecycle2,
            runtime_host=runtime_host2,
            registry=registry2,
            catalog=catalog2,
            light_brain_memory=memory2,
        )
        assert restore.get("status") != "error"

        # Verify restored state
        restored_instance = lifecycle2.get_instance("test-app-001")
        assert restored_instance is not None
        assert restored_instance.id == "test-app-001"
        assert restored_instance.status == "installed"

        # Verify sessions
        sessions = memory2.list_sessions()
        assert len(sessions) >= 1


def test_persistence_graceful_degradation():
    """Corrupted persistence files should not crash the system."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        state_dir.mkdir()

        # Write a corrupted JSON file
        corrupted_path = state_dir / "runtime_state.json"
        corrupted_path.write_text("{ invalid json !!!")

        persistence = PersistenceService(data_dir=str(state_dir))
        # Should not raise — should gracefully degrade
        lifecycle = AppLifecycleService()
        result = persistence.restore_state(
            lifecycle=lifecycle,
        )
        # Should return some status indicating the issue
        assert "status" in result


def test_persistence_state_changes_saved():
    """State changes should be persisted after each operation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        state_dir.mkdir()

        store = RuntimeStateStore(base_dir=str(tmpdir))
        lifecycle = AppLifecycleService(store=store)
        runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=store)
        registry = AppRegistryService(store=store)
        catalog = AppCatalogService()
        persistence = PersistenceService(data_dir=str(state_dir))

        # Create instance
        instance = AppInstance(
            id="test-app-002",
            blueprint_id="bp-002",
            owner_user_id="user-1",
            status="installed",
            execution_mode="service",
            data_namespace="ns-test-002",
        )
        runtime_host.register_instance(instance)

        # Start the app
        lifecycle.transition("test-app-002", "start")
        assert lifecycle.get_instance("test-app-002").status == "running"

        # Save and verify
        saved_path = persistence.save_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=registry,
            catalog=catalog,
        )
        assert saved_path.exists()
        assert saved_path.stat().st_size > 0


def test_archive_snapshot_persistence():
    """Archiving an app should save a snapshot that survives restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RuntimeStateStore(base_dir=str(tmpdir))
        lifecycle = AppLifecycleService(store=store)
        runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=store)

        # Create and install an app
        instance = AppInstance(
            id="archive-test",
            blueprint_id="bp-archive",
            owner_user_id="user-1",
            status="installed",
            execution_mode="pipeline",
            resolved_skills=["skill-x"],
            data_namespace="ns-archive",
        )
        runtime_host.register_instance(instance)

        # Archive it
        result = lifecycle.archive("archive-test", reason="testing")
        assert result.current_status == "archived"

        # Verify snapshot was saved
        snapshot = lifecycle._load_snapshot("archive-test")
        assert snapshot is not None
        assert snapshot.get("installed_version") == instance.installed_version
        assert snapshot.get("data_namespace") == "ns-archive"

        # Unarchive and verify restoration
        result2 = lifecycle.unarchive("archive-test", reason="testing restore")
        assert result2.current_status == "installed"
        restored = lifecycle.get_instance("archive-test")
        assert restored.status == "installed"
        assert restored.data_namespace == "ns-archive"
