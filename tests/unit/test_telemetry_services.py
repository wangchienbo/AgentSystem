from datetime import UTC, datetime
from pathlib import Path

from app.models.telemetry import (
    CollectionPolicyRecord,
    FeedbackRecord,
    InteractionTelemetryRecord,
    StepTelemetryRecord,
    VersionBindingRecord,
)
from app.models.upgrade_log import UpgradeLogEvent
from app.services.collection_policy_service import CollectionPolicyService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.telemetry_service import TelemetryService
from app.services.upgrade_log_service import UpgradeLogService


def test_collection_policy_precedence(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    service = CollectionPolicyService(store=store)
    service.set_policy(CollectionPolicyRecord(scope_type="global", scope_id="default", level="light"))
    service.set_policy(CollectionPolicyRecord(scope_type="app", scope_id="app.alpha", level="medium"))
    service.set_policy(CollectionPolicyRecord(scope_type="skill", scope_id="skill.beta", level="off", enabled=False))

    resolved_app = service.resolve_policy(app_id="app.alpha")
    resolved_skill = service.resolve_policy(app_id="app.alpha", skill_id="skill.beta")

    assert resolved_app.level == "medium"
    assert resolved_skill.enabled is False
    assert resolved_skill.level == "off"


def test_upgrade_log_service_appends_jsonl_by_day(tmp_path: Path) -> None:
    service = UpgradeLogService(base_dir=str(tmp_path / "upgrade"))
    event = UpgradeLogEvent(
        event_id="evt.001",
        ts=datetime(2026, 3, 28, 10, 0, tzinfo=UTC),
        event_type="interaction_completed",
        scope="interaction",
        app_id="app.alpha",
        interaction_id="i.001",
        payload={"ok": True},
    )
    path = service.append_event("interactions", event)
    service.append_event("interactions", event.model_copy(update={"event_id": "evt.002"}))

    assert path.name == "2026-03-28.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    events = service.read_events("interactions", "2026-03-28")
    assert [item.event_id for item in events] == ["evt.001", "evt.002"]


def test_telemetry_service_records_and_persists(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    policy_service = CollectionPolicyService(store=store)
    upgrade_log_service = UpgradeLogService(base_dir=str(tmp_path / "upgrade"))
    telemetry = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)

    interaction = InteractionTelemetryRecord(
        interaction_id="i.100",
        app_id="app.alpha",
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
        total_latency_ms=900,
    )
    step = StepTelemetryRecord(
        interaction_id="i.100",
        step_id="s.1",
        step_type="skill",
        name="cost-analyzer",
        latency_ms=200,
        payload_summary={"kind": "analysis"},
    )
    feedback = FeedbackRecord(
        feedback_id="f.1",
        interaction_id="i.100",
        scope_type="app",
        scope_id="app.alpha",
        feedback_kind="explicit",
        score=4,
        labels=["useful"],
    )
    binding = VersionBindingRecord(
        interaction_id="i.100",
        app_version="v1",
        skill_versions={"cost-analyzer": "0.1.0"},
        agent_version="a1",
    )

    telemetry.record_interaction(interaction)
    telemetry.record_step(step, app_id="app.alpha")
    telemetry.record_feedback(feedback, app_id="app.alpha")
    telemetry.bind_versions(binding, app_id="app.alpha")

    reloaded = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)
    assert reloaded.get_interaction("i.100") is not None
    assert len(reloaded.list_steps("i.100")) == 1
    assert len(reloaded.list_feedback(scope_id="app.alpha")) == 1
    assert reloaded.get_version_binding("i.100") is not None


def test_telemetry_service_medium_policy_records_step_upgrade_events(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    policy_service = CollectionPolicyService(store=store)
    policy_service.set_policy(CollectionPolicyRecord(scope_type="app", scope_id="app.alpha", level="medium"))
    upgrade_log_service = UpgradeLogService(base_dir=str(tmp_path / "upgrade"))
    telemetry = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)

    telemetry.record_step(
        StepTelemetryRecord(
            interaction_id="i.200",
            step_id="s.1",
            step_type="skill",
            name="acceptance-report",
        ),
        app_id="app.alpha",
    )

    events = upgrade_log_service.read_events("interactions", datetime.now(UTC).date().isoformat())
    assert any(item.event_type == "step_completed" for item in events)
