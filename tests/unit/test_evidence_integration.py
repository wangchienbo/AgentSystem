from pathlib import Path

from app.models.app_context import AppSharedContext
from app.services.app_context_store import AppContextStore
from app.services.context_compaction import ContextCompactionService
from app.services.lifecycle import AppLifecycleService
from app.services.log_evidence_service import LogEvidenceService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.skill_risk_policy import SkillRiskPolicyService



def test_context_compaction_reads_promoted_evidence_summary(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "evidence-integration-store"))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store)
    evidence = LogEvidenceService(store=store)

    class StubWorkflowExecutor:
        def __init__(self) -> None:
            self._skill_runtime = None

        def list_history(self, app_instance_id: str):
            return []

    context_store._contexts["app.evidence"] = AppSharedContext(
        app_instance_id="app.evidence",
        app_name="bp.evidence",
        owner_user_id="user.evidence",
        description="evidence context",
        status="active",
        current_goal="inspect evidence",
        current_stage="running",
        entries=[],
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.evidence",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.evidence",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )
    compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=StubWorkflowExecutor(),
        store=store,
        log_evidence_service=evidence,
    )

    summary = compaction.compact("app.evidence", reason="manual")

    assert evidence.get_stats_summary()["signal_count"] >= 1
    assert summary.metadata["evidence_summary"]["count"] >= 1



def test_skill_risk_policy_blocked_events_feed_evidence(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "skill-risk-evidence"))
    evidence = LogEvidenceService(store=store)
    service = SkillRiskPolicyService(store=store, log_evidence_service=evidence)

    service.record_event(skill_id="skill.blocked.demo", event_type="policy_blocked", reason="blocked once")
    service.record_event(skill_id="skill.blocked.demo", event_type="policy_blocked", reason="blocked twice")
    service.record_event(skill_id="skill.blocked.demo", event_type="policy_blocked", reason="blocked third")

    stats = evidence.get_stats_summary()
    assert stats["signal_count"] >= 1
    assert stats["promoted_evidence_count"] >= 1
