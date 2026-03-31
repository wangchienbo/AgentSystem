from app.services.log_evidence_service import LogEvidenceService



def test_workflow_failures_promote_after_repetition() -> None:
    service = LogEvidenceService()

    assert service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    ) is None

    signal = service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )
    assert signal is not None
    assert signal.category == "workflow_failure"
    assert signal.frequency == 2

    service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.3",
        status="partial",
    )
    stats = service.get_stats_summary()
    assert stats["promoted_evidence_count"] >= 1
    assert stats["signal_count"] >= 1



def test_policy_pressure_promotes_after_repeated_events() -> None:
    service = LogEvidenceService()

    assert service.ingest_policy_event(skill_id="skill.demo", event_type="policy_blocked", reason="blocked", scope="generated_app_assembly") is None
    signal = service.ingest_policy_event(skill_id="skill.demo", event_type="policy_blocked", reason="blocked again", scope="generated_app_assembly")

    assert signal is not None
    assert signal.category == "policy_pressure"

    service.ingest_policy_event(skill_id="skill.demo", event_type="policy_blocked", reason="blocked third", scope="generated_app_assembly")
    evidence_page = service.list_promoted_evidence()
    assert len(evidence_page.items) >= 1



def test_clarify_unresolved_becomes_signal_after_repetition() -> None:
    service = LogEvidenceService()

    assert service.ingest_clarify_unresolved(
        request_text="做一个系统",
        requirement_type="unclear",
        readiness="needs_clarification",
        missing_fields=["artifact_type", "goal"],
    ) is None

    signal = service.ingest_clarify_unresolved(
        request_text="做一个系统",
        requirement_type="unclear",
        readiness="needs_clarification",
        missing_fields=["artifact_type", "goal"],
    )
    assert signal is not None
    assert signal.category == "clarify_unresolved"



def test_index_entries_are_created_for_signals_and_evidence() -> None:
    service = LogEvidenceService()
    service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    )
    service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )
    service.ingest_workflow_failure(
        app_instance_id="app.demo",
        workflow_id="wf.main",
        failed_step_ids=["step.a"],
        execution_id="exec.3",
        status="partial",
    )

    index_page = service.list_index_entries()
    assert len(index_page.items) >= 2
