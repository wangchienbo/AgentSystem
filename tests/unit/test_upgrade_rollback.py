"""Tests for Phase 9: App Upgrade / Rollback services."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.app_blueprint import (
    AppBlueprint,
    Role,
    Task,
    Workflow,
    WorkflowStep,
    StoragePlan,
)
from app.models.app_instance import AppInstance, AppStatus
from app.models.app_profile import AppRuntimeProfile
from app.models.runtime_policy import RuntimePolicy
from app.services.blueprint_compare import (
    BlueprintCompareError,
    BlueprintCompareService,
    BlueprintDiffItem,
)
from app.services.lifecycle import AppLifecycleService, LifecycleError
from app.services.rollback_service import RollbackError, RollbackService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.upgrade_log_service import UpgradeLogService
from app.services.upgrade_service import UpgradeError, UpgradeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bp(
    bp_id: str = "bp-1",
    name: str = "TestApp",
    version: str = "0.1.0",
    roles: list | None = None,
    tasks: list | None = None,
    workflows: list | None = None,
    skills: list | None = None,
    modules: list | None = None,
    runtime_policy: RuntimePolicy | None = None,
    storage_plan: StoragePlan | None = None,
    app_shape: str = "generic",
) -> AppBlueprint:
    return AppBlueprint(
        id=bp_id,
        name=name,
        goal="test",
        version=version,
        app_shape=app_shape,
        roles=roles or [],
        tasks=tasks or [],
        workflows=workflows or [],
        required_skills=set(skills or []),
        required_modules=modules or [],
        runtime_policy=runtime_policy or RuntimePolicy(),
        storage_plan=storage_plan or StoragePlan(),
    )


def _make_instance(
    instance_id: str = "app-1",
    bp_id: str = "bp-1",
    status: AppStatus = "draft",
    version: str = "0.1.0",
) -> AppInstance:
    return AppInstance(
        id=instance_id,
        blueprint_id=bp_id,
        owner_user_id="user-1",
        status=status,
        installed_version=version,
        data_namespace="test",
        execution_mode="service",
        runtime_policy=RuntimePolicy(),
        system_skills=["system.app_config"],
        resolved_skills=["system.app_config"],
    )


def _setup_lifecycle_and_registry():
    """Set up lifecycle with a registered instance and blueprint in registry."""
    store = RuntimeStateStore(base_dir="data/runtime/test_upgrade")
    lifecycle = AppLifecycleService(store=store)

    bp = _make_bp()
    instance = _make_instance()

    # Register directly
    lifecycle.register_instance(instance)
    lifecycle.transition(instance.id, "validate", reason="test")
    lifecycle.transition(instance.id, "compile", reason="test")
    lifecycle.transition(instance.id, "install", reason="test")

    return lifecycle, bp


# ---------------------------------------------------------------------------
# Blueprint Compare Tests
# ---------------------------------------------------------------------------

class TestBlueprintCompareService:
    def setup_method(self):
        self.service = BlueprintCompareService()

    def test_identical_blueprints_no_changes(self):
        bp = _make_bp()
        result = self.service.compare(bp, bp.model_copy(deep=True))
        assert result.total_changes == 0
        assert result.risk_level == "low"
        assert result.summary == "No changes detected"

    def test_different_ids_raises(self):
        bp1 = _make_bp(bp_id="bp-1")
        bp2 = _make_bp(bp_id="bp-2")
        with pytest.raises(BlueprintCompareError, match="different IDs"):
            self.service.compare(bp1, bp2)

    def test_role_added(self):
        old = _make_bp()
        new = _make_bp(roles=[Role(id="r1", name="Admin", type="human")])
        result = self.service.compare(old, new)
        assert len(result.roles_added) == 1
        assert result.roles_added[0]["id"] == "r1"

    def test_role_removed(self):
        old = _make_bp(roles=[Role(id="r1", name="Admin", type="human")])
        new = _make_bp()
        result = self.service.compare(old, new)
        assert len(result.roles_removed) == 1

    def test_role_modified(self):
        old = _make_bp(roles=[Role(id="r1", name="Admin", type="human")])
        new = _make_bp(roles=[Role(id="r1", name="SuperAdmin", type="human")])
        result = self.service.compare(old, new)
        assert len(result.roles_modified) == 1
        assert result.roles_modified[0]["changes"]["name"]["from"] == "Admin"
        assert result.roles_modified[0]["changes"]["name"]["to"] == "SuperAdmin"

    def test_task_added_and_removed(self):
        old = _make_bp(tasks=[Task(id="t1", owner_role="r1", trigger="manual")])
        new = _make_bp(tasks=[Task(id="t2", owner_role="r1", trigger="manual")])
        result = self.service.compare(old, new)
        assert len(result.tasks_added) == 1
        assert len(result.tasks_removed) == 1

    def test_workflow_changes(self):
        step = WorkflowStep(id="s1", kind="skill", ref="skill.1")
        old = _make_bp(workflows=[Workflow(id="wf1", name="Old", steps=[step])])
        new = _make_bp(workflows=[Workflow(id="wf2", name="New", steps=[step])])
        result = self.service.compare(old, new)
        assert len(result.workflows_added) == 1
        assert len(result.workflows_removed) == 1

    def test_skills_diff(self):
        old = _make_bp(skills=["skill-a", "skill-b"])
        new = _make_bp(skills=["skill-b", "skill-c"])
        result = self.service.compare(old, new)
        assert result.skills_added == ["skill-c"]
        assert result.skills_removed == ["skill-a"]

    def test_modules_diff(self):
        old = _make_bp(modules=["mod-a"])
        new = _make_bp(modules=["mod-b"])
        result = self.service.compare(old, new)
        assert result.modules_added == ["mod-b"]
        assert result.modules_removed == ["mod-a"]

    def test_storage_plan_change(self):
        old = _make_bp()
        new = _make_bp(storage_plan=StoragePlan(user_data="custom"))
        result = self.service.compare(old, new)
        assert result.storage_plan_changed is True
        assert "user_data" in result.storage_plan_diff

    def test_runtime_policy_change(self):
        old = _make_bp(runtime_policy=RuntimePolicy(execution_mode="service"))
        new = _make_bp(runtime_policy=RuntimePolicy(execution_mode="pipeline"))
        result = self.service.compare(old, new)
        assert result.runtime_policy_changed is True
        assert "execution_mode" in result.runtime_policy_diff

    def test_app_shape_change(self):
        old = _make_bp(app_shape="generic")
        new = _make_bp(app_shape="pipeline_chain")
        result = self.service.compare(old, new)
        assert result.app_shape_changed is True
        assert result.app_shape_from == "generic"
        assert result.app_shape_to == "pipeline_chain"

    def test_risk_level_breaking_change_role_removed(self):
        old = _make_bp(roles=[Role(id="r1", name="Admin", type="human")])
        new = _make_bp()
        result = self.service.compare(old, new)
        assert result.risk_level in ("medium", "high", "critical")
        assert len(result.breaking_changes) > 0

    def test_risk_level_low_no_breaking(self):
        old = _make_bp()
        new = _make_bp(version="0.2.0")
        result = self.service.compare(old, new)
        assert result.risk_level == "low"

    def test_summary_with_changes(self):
        old = _make_bp(skills=["skill-a"])
        new = _make_bp(skills=["skill-b"])
        result = self.service.compare(old, new)
        assert "change(s)" in result.summary
        assert "risk:" in result.summary


# ---------------------------------------------------------------------------
# Upgrade Service Tests
# ---------------------------------------------------------------------------

class TestUpgradeService:
    def setup_method(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="test_upgrade_svc_"))
        self.store = RuntimeStateStore(base_dir=str(self._tmpdir / "runtime"))
        self.lifecycle = AppLifecycleService(store=self.store)
        self.log_dir = self._tmpdir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_service = UpgradeLogService(base_dir=str(self.log_dir))
        self.compare_service = BlueprintCompareService()
        self.service = UpgradeService(
            lifecycle=self.lifecycle,
            log_service=self.log_service,
            compare_service=self.compare_service,
        )

        # Set up a valid instance
        self.bp = _make_bp(bp_id="bp-test", version="0.1.0", skills=["skill-a"])
        self.instance = _make_instance(instance_id="app-up", bp_id="bp-test", status="draft", version="0.1.0")
        self.lifecycle.register_instance(self.instance)
        self.lifecycle.transition(self.instance.id, "validate", reason="test")
        self.lifecycle.transition(self.instance.id, "compile", reason="test")
        self.lifecycle.transition(self.instance.id, "install", reason="test")

    def test_upgrade_from_installed(self):
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0", skills=["skill-a", "skill-b"])
        result = self.service.upgrade(
            app_instance_id="app-up",
            new_blueprint=new_bp,
            reviewer="test",
            reason="add skill-b",
        )
        assert result.success is True
        assert result.from_version == "0.1.0"
        assert result.to_version == "0.2.0"
        assert result.app_instance_id == "app-up"
        assert result.snapshot_id == "snapshot:app-up"

    def test_upgrade_blocked_from_failed(self):
        # Transition to failed
        self.lifecycle.transition(self.instance.id, "start", reason="test")
        self.lifecycle.transition(self.instance.id, "fail", reason="test")

        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        with pytest.raises(UpgradeError, match="blocked"):
            self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

    def test_upgrade_blocked_from_archived(self):
        self.lifecycle.transition(self.instance.id, "archive", reason="test")

        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        with pytest.raises(UpgradeError, match="blocked"):
            self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

    def test_upgrade_blocked_from_draft(self):
        # Instance is already in "installed" state; reset to draft
        fresh_instance = _make_instance(instance_id="app-draft", status="draft")
        self.lifecycle.register_instance(fresh_instance)

        new_bp = _make_bp(bp_id="bp-draft", version="0.2.0")
        with pytest.raises(UpgradeError, match="blocked"):
            self.service.upgrade(app_instance_id="app-draft", new_blueprint=new_bp)

    def test_upgrade_blueprint_id_mismatch(self):
        new_bp = _make_bp(bp_id="bp-other", version="0.2.0")
        with pytest.raises(UpgradeError, match="Blueprint ID mismatch"):
            self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

    def test_upgrade_requires_reviewer(self):
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        with pytest.raises(UpgradeError, match="requires a reviewer"):
            self.service.upgrade(
                app_instance_id="app-up",
                new_blueprint=new_bp,
                require_reviewer=True,
            )

    def test_upgrade_snapshot_created(self):
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

        snapshot = self.service.get_snapshot("app-up")
        assert snapshot is not None
        assert snapshot.installed_version == "0.1.0"
        assert snapshot.status == "installed"

    def test_upgrade_log_recorded(self):
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

        events = self.service.get_upgrade_log("app-up")
        assert len(events) > 0
        assert events[0].event_type == "app_upgrade"
        assert events[0].app_id == "app-up"

    def test_upgrade_empty_skills_rejected(self):
        # Create instance with resolved skills but no system skills
        inst = _make_instance(instance_id="app-no-sys", bp_id="bp-test", status="draft", version="0.1.0")
        inst.resolved_skills = ["skill-a"]
        inst.system_skills = []
        self.lifecycle.register_instance(inst)
        self.lifecycle.transition(inst.id, "validate", reason="test")
        self.lifecycle.transition(inst.id, "compile", reason="test")
        self.lifecycle.transition(inst.id, "install", reason="test")

        # New blueprint removes all skills
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0", skills=[])
        with pytest.raises(UpgradeError, match="removes all required skills"):
            self.service.upgrade(app_instance_id="app-no-sys", new_blueprint=new_bp)

    def test_list_snapshots(self):
        new_bp = _make_bp(bp_id="bp-test", version="0.2.0")
        self.service.upgrade(app_instance_id="app-up", new_blueprint=new_bp)

        snapshots = self.service.list_snapshots()
        assert "app-up" in snapshots


# ---------------------------------------------------------------------------
# Rollback Service Tests
# ---------------------------------------------------------------------------

class TestRollbackService:
    def setup_method(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="test_rollback_"))
        self.store = RuntimeStateStore(base_dir=str(self._tmpdir / "runtime"))
        self.lifecycle = AppLifecycleService(store=self.store)
        self.log_dir = self._tmpdir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_service = UpgradeLogService(base_dir=str(self.log_dir))
        self.compare_service = BlueprintCompareService()
        self.upgrade_service = UpgradeService(
            lifecycle=self.lifecycle,
            log_service=self.log_service,
            compare_service=self.compare_service,
        )
        self.rollback_service = RollbackService(
            upgrade_service=self.upgrade_service,
            log_service=self.log_service,
        )

        # Set up instance through install
        self.bp = _make_bp(bp_id="bp-rb", version="0.1.0", skills=["skill-a"])
        self.instance = _make_instance(instance_id="app-rb", bp_id="bp-rb", status="draft", version="0.1.0")
        self.lifecycle.register_instance(self.instance)
        self.lifecycle.transition(self.instance.id, "validate", reason="test")
        self.lifecycle.transition(self.instance.id, "compile", reason="test")
        self.lifecycle.transition(self.instance.id, "install", reason="test")

    def test_rollback_after_upgrade(self):
        # First upgrade
        new_bp = _make_bp(bp_id="bp-rb", version="0.2.0", skills=["skill-a", "skill-b"])
        self.upgrade_service.upgrade(
            app_instance_id="app-rb",
            new_blueprint=new_bp,
            reviewer="test",
        )

        # Now rollback
        result = self.rollback_service.rollback(
            app_instance_id="app-rb",
            reviewer="test",
            reason="upgrade caused issues",
        )
        assert result.success is True
        assert result.from_version == "0.2.0"
        assert result.to_version == "0.1.0"
        assert result.snapshot_restored is True

    def test_rollback_no_snapshot(self):
        with pytest.raises(RollbackError, match="No rollback snapshot found"):
            self.rollback_service.rollback(app_instance_id="app-rb")

    def test_rollback_instance_not_found(self):
        # Create a snapshot for a non-existent instance
        with pytest.raises(RollbackError, match="not found"):
            self.rollback_service.rollback(app_instance_id="nonexistent")

    def test_rollback_log_recorded(self):
        # Upgrade first
        new_bp = _make_bp(bp_id="bp-rb", version="0.2.0")
        self.upgrade_service.upgrade(
            app_instance_id="app-rb",
            new_blueprint=new_bp,
            reviewer="test",
        )

        # Rollback
        self.rollback_service.rollback(app_instance_id="app-rb", reason="test")

        # Check log
        events = self.upgrade_service.get_upgrade_log("app-rb")
        rollback_events = [e for e in events if e.event_type == "app_rollback"]
        assert len(rollback_events) > 0

    def test_rollback_history(self):
        # Upgrade and rollback
        new_bp = _make_bp(bp_id="bp-rb", version="0.2.0")
        self.upgrade_service.upgrade(
            app_instance_id="app-rb",
            new_blueprint=new_bp,
            reviewer="test",
        )
        self.rollback_service.rollback(app_instance_id="app-rb")

        history = self.rollback_service.get_rollback_history("app-rb")
        assert len(history) > 0
        assert all(e.event_type == "app_rollback" for e in history)
