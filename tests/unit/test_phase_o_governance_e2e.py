"""Phase O: Production governance E2E validation."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.context_compaction import ContextCompactionService
from app.governance.policy_authority_service import PolicyAuthorityService
from app.governance.collection_policy_service import CollectionPolicyService
from app.persistence.persistence_health_service import PersistenceHealthService
from app.services.runtime_state_store import RuntimeStateStore
from app.models.telemetry import CollectionPolicyRecord
from app.models.app_context import AppSharedContext


class MockCtxStore:
    def get_context(self, app_id):
        return AppSharedContext(
            app_instance_id=app_id, app_name="test", owner_user_id="user1",
            description="test", current_goal="test goal", current_stage="running",
        )
    def ensure_context(self, app_id):
        return self.get_context(app_id)


class MockWorkflowExecutor:
    def list_history(self, app_id):
        return []


@pytest.fixture
def governance_env(tmp_path):
    """Create a minimal governance environment."""
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    return {
        "store": store,
        "ctx_store": MockCtxStore(),
        "workflow_executor": MockWorkflowExecutor(),
    }


def test_persistence_health(governance_env):
    """O-02: Persistence health check returns valid summary."""
    ph = PersistenceHealthService(store=governance_env["store"])
    summary = ph.get_summary()
    assert summary.healthy is True
    assert summary.file_count >= 0


def test_policy_authority_enforce(governance_env):
    """O-04: Policy authority enforcement works."""
    pa = PolicyAuthorityService(store=governance_env["store"])
    pa.set_policy(pa.get_policy("app_install"))
    decision = pa.enforce(scope="app_install", automatic=True)
    assert decision.allowed is True


def test_collection_policy_resolve(governance_env):
    """O-04: Collection policy resolution works."""
    cp = CollectionPolicyService(store=governance_env["store"])
    cp.set_policy(CollectionPolicyRecord(scope_type="global", scope_id="default"))
    resolved = cp.resolve_policy()
    assert resolved.scope_type == "global"


def test_context_compaction_working_set(governance_env):
    """O-01: Context compaction builds working set."""
    compaction = ContextCompactionService(
        app_context_store=governance_env["ctx_store"],
        workflow_executor=governance_env["workflow_executor"],
        store=governance_env["store"],
    )
    ws = compaction.build_working_set("test.app.v1")
    assert ws.layer == "working_set"
    assert ws.current_goal == "test goal"


def test_context_compaction_summary(governance_env):
    """O-01: Context compaction produces summary."""
    compaction = ContextCompactionService(
        app_context_store=governance_env["ctx_store"],
        workflow_executor=governance_env["workflow_executor"],
        store=governance_env["store"],
    )
    summary = compaction.compact("test.app.v1", reason="e2e_test")
    assert summary.layer == "summary"
    assert "compact_reason" in summary.metadata


def test_context_compaction_list_layers(governance_env):
    """O-01: Context compaction lists all layers."""
    compaction = ContextCompactionService(
        app_context_store=governance_env["ctx_store"],
        workflow_executor=governance_env["workflow_executor"],
        store=governance_env["store"],
    )
    layers = compaction.list_layers("test.app.v1")
    assert "working_set" in layers["layers"]
    assert "summary" in layers["layers"]
    assert "detail" in layers["layers"]


def test_governance_e2e_integration(governance_env):
    """O-05: Full governance loop — health + policy + context."""
    store = governance_env["store"]
    
    # 1. Health check
    ph = PersistenceHealthService(store=store)
    assert ph.get_summary().healthy is True
    
    # 2. Policy authority
    pa = PolicyAuthorityService(store=store)
    pa.set_policy(pa.get_policy("app_install"))
    
    # 3. Collection policy
    cp = CollectionPolicyService(store=store)
    cp.set_policy(CollectionPolicyRecord(scope_type="global", scope_id="default"))
    
    # 4. Context compaction
    compaction = ContextCompactionService(
        app_context_store=governance_env["ctx_store"],
        workflow_executor=governance_env["workflow_executor"],
        store=store,
    )
    ws = compaction.build_working_set("test.app.v1")
    assert ws.layer == "working_set"
    
    # All services work together — governance loop verified
    assert len(pa.list_policies()) >= 1
    assert cp.resolve_policy() is not None
    assert compaction.list_layers("test.app.v1") is not None
