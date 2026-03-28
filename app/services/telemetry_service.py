from __future__ import annotations

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
from app.services.upgrade_log_service import UpgradeLogService


class TelemetryService:
    def __init__(
        self,
        store: RuntimeStateStore,
        policy_service: CollectionPolicyService,
        upgrade_log_service: UpgradeLogService,
    ) -> None:
        self.store = store
        self.policy_service = policy_service
        self.upgrade_log_service = upgrade_log_service
        self._interactions: dict[str, InteractionTelemetryRecord] = {}
        self._steps: dict[str, list[StepTelemetryRecord]] = {}
        self._feedback: dict[str, FeedbackRecord] = {}
        self._version_bindings: dict[str, VersionBindingRecord] = {}
        self._load()

    def record_interaction(self, record: InteractionTelemetryRecord) -> InteractionTelemetryRecord:
        policy = self.policy_service.resolve_policy(app_id=record.app_id)
        if not policy.enabled or policy.level == "off":
            return record
        self._interactions[record.interaction_id] = record
        self._persist()
        self._append_upgrade_event(
            stream="interactions",
            policy=policy,
            event=UpgradeLogEvent(
                event_id=f"interaction:{record.interaction_id}",
                event_type="interaction_completed",
                scope="interaction",
                app_id=record.app_id,
                interaction_id=record.interaction_id,
                payload=record.model_dump(mode="json"),
            ),
        )
        return record

    def record_step(self, record: StepTelemetryRecord, *, app_id: str | None = None) -> StepTelemetryRecord:
        policy = self.policy_service.resolve_policy(app_id=app_id)
        if not policy.enabled or policy.level == "off":
            return record
        self._steps.setdefault(record.interaction_id, []).append(record)
        self._persist()
        if policy.level in {"medium", "heavy", "custom"}:
            self._append_upgrade_event(
                stream="interactions",
                policy=policy,
                event=UpgradeLogEvent(
                    event_id=f"step:{record.interaction_id}:{record.step_id}",
                    event_type="step_completed",
                    scope="interaction",
                    app_id=app_id,
                    interaction_id=record.interaction_id,
                    payload=record.model_dump(mode="json"),
                ),
            )
        return record

    def record_feedback(self, record: FeedbackRecord, *, app_id: str | None = None, skill_id: str | None = None) -> FeedbackRecord:
        policy = self.policy_service.resolve_policy(app_id=app_id, skill_id=skill_id)
        if not policy.enabled or policy.level == "off" or not policy.capture_feedback:
            return record
        self._feedback[record.feedback_id] = record
        self._persist()
        self._append_upgrade_event(
            stream="interactions",
            policy=policy,
            event=UpgradeLogEvent(
                event_id=f"feedback:{record.feedback_id}",
                event_type="feedback_received",
                scope=record.scope_type,
                app_id=app_id,
                skill_id=skill_id,
                interaction_id=record.interaction_id,
                payload=record.model_dump(mode="json"),
            ),
        )
        return record

    def bind_versions(self, record: VersionBindingRecord, *, app_id: str | None = None) -> VersionBindingRecord:
        policy = self.policy_service.resolve_policy(app_id=app_id)
        if not policy.enabled or policy.level == "off":
            return record
        self._version_bindings[record.interaction_id] = record
        self._persist()
        return record

    def get_interaction(self, interaction_id: str) -> InteractionTelemetryRecord | None:
        return self._interactions.get(interaction_id)

    def list_steps(self, interaction_id: str) -> list[StepTelemetryRecord]:
        return self._steps.get(interaction_id, [])

    def list_feedback(self, *, scope_id: str | None = None) -> list[FeedbackRecord]:
        items = list(self._feedback.values())
        if scope_id is not None:
            items = [item for item in items if item.scope_id == scope_id]
        return items

    def get_version_binding(self, interaction_id: str) -> VersionBindingRecord | None:
        return self._version_bindings.get(interaction_id)

    def _append_upgrade_event(self, *, stream: str, policy: CollectionPolicyRecord, event: UpgradeLogEvent) -> None:
        try:
            if policy.level != "off":
                self.upgrade_log_service.append_event(stream, event)
        except OSError:
            return

    def _persist(self) -> None:
        self.store.save_mapping("telemetry_interactions", self._interactions)
        self.store.save_nested_mapping("telemetry_steps", self._steps)
        self.store.save_mapping("telemetry_feedback", self._feedback)
        self.store.save_mapping("telemetry_version_bindings", self._version_bindings)

    def _load(self) -> None:
        self._interactions = {
            key: InteractionTelemetryRecord.model_validate(value)
            for key, value in self.store.load_json("telemetry_interactions", {}).items()
        }
        self._steps = {
            key: [StepTelemetryRecord.model_validate(item) for item in values]
            for key, values in self.store.load_json("telemetry_steps", {}).items()
        }
        self._feedback = {
            key: FeedbackRecord.model_validate(value)
            for key, value in self.store.load_json("telemetry_feedback", {}).items()
        }
        self._version_bindings = {
            key: VersionBindingRecord.model_validate(value)
            for key, value in self.store.load_json("telemetry_version_bindings", {}).items()
        }
