from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.app_instance import AppInstance
from app.models.scheduling import ScheduleRecord
from app.services.refinement_memory import RefinementMemoryStore
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.system.chat_regression import list_saved_runs, make_testclient_poster, run_regression_governance_cycle
from app.system.regression_dashboard import build_regression_operator_summary
from app.system.regression_governance_policy import (
    PREFLIGHT_HOLD_AUTOMATION_DEGRADED_REQUIRES_REVIEW,
    PREFLIGHT_HOLD_AUTOMATION_RETRY_PENDING_REQUIRES_REVIEW,
    PREFLIGHT_HOLD_NONE,
    PREFLIGHT_HOLD_NO_RECOMMENDED_QUEUE,
    PREFLIGHT_HOLD_RECOMMENDED_QUEUE_MISSING,
    PREFLIGHT_HOLD_ROLLOUT_SERVICE_UNAVAILABLE,
    PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW,
    PREFLIGHT_REVIEW_REASON_AUTOMATION_DEGRADED,
    PREFLIGHT_REVIEW_REASON_AUTOMATION_RETRY_PENDING,
    PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY,
    PREFLIGHT_REVIEW_REASON_PRIORITY_SECONDARY,
    PREFLIGHT_REVIEW_REASON_PRIORITY_TIER_BLOCKED,
    PREFLIGHT_REVIEW_REASON_QUEUE_MISSING,
    PREFLIGHT_REVIEW_REASON_QUEUE_STATE_BLOCKED,
    PREFLIGHT_REVIEW_REASON_SELECTION_MISSING,
    PREFLIGHT_REVIEW_REASON_SERVICE_UNAVAILABLE,
    PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK,
    PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
    PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION,
    PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_QUEUE_STATE,
    build_governance_preflight_decision,
)
from app.refinement.refinement_rollout import RefinementRolloutService

APP_INSTANCE_ID = "agent_system"
REGRESSION_CYCLE_TASK_NAME = "regression_governance_cycle"
REGRESSION_NIGHTLY_SCHEDULE_ID = "sch.regression.governance.nightly"
REGRESSION_NIGHTLY_STATE_KEY = "regression_nightly_state"
REGRESSION_NIGHTLY_DRIVER_STATE_KEY = "regression_nightly_driver_state"
REGRESSION_NIGHTLY_SERVICE_SESSION_ID = "session_regression_nightly_service"


class RegressionNightlyControlService:
    def __init__(
        self,
        *,
        scheduler: SchedulerService,
        runtime_host: AppRuntimeHostService,
        runtime_store: RuntimeStateStore,
        refinement_memory: RefinementMemoryStore,
        refinement_rollout: RefinementRolloutService | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._runtime_host = runtime_host
        self._runtime_store = runtime_store
        self._refinement_memory = refinement_memory
        self._refinement_rollout = refinement_rollout

    def ensure_runtime_instance(self) -> None:
        try:
            self._scheduler._lifecycle.get_instance(APP_INSTANCE_ID)
            return
        except Exception:
            pass
        self._runtime_host.register_instance(AppInstance(
            id=APP_INSTANCE_ID,
            blueprint_id="bp.regression.governance",
            owner_user_id="system",
            status="running",
            data_namespace="governance/regression",
        ))

    def register_nightly_schedule(self, interval_seconds: int = 86400) -> ScheduleRecord:
        self.ensure_runtime_instance()
        return self._scheduler.register_schedule(
            ScheduleRecord(
                schedule_id=REGRESSION_NIGHTLY_SCHEDULE_ID,
                app_instance_id=APP_INSTANCE_ID,
                trigger_type="interval",
                task_name=REGRESSION_CYCLE_TASK_NAME,
                interval_seconds=interval_seconds,
            )
        )

    def list_nightly_schedules(self) -> list[ScheduleRecord]:
        self.ensure_runtime_instance()
        return [item for item in self._scheduler.list_schedules(APP_INSTANCE_ID) if item.task_name == REGRESSION_CYCLE_TASK_NAME]

    def load_tick_state(self) -> dict[str, Any]:
        return self._runtime_store.load_json(REGRESSION_NIGHTLY_STATE_KEY, {})

    def save_tick_state(self, state: dict[str, Any]) -> None:
        self._runtime_store._write_json(REGRESSION_NIGHTLY_STATE_KEY, state)

    def load_driver_state(self) -> dict[str, Any]:
        return self._runtime_store.load_json(REGRESSION_NIGHTLY_DRIVER_STATE_KEY, {})

    def save_driver_state(self, state: dict[str, Any]) -> None:
        self._runtime_store._write_json(REGRESSION_NIGHTLY_DRIVER_STATE_KEY, state)

    def build_nightly_status(self, driver_status: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_runtime_instance()
        schedules = self.list_nightly_schedules()
        overview = self._runtime_host.get_overview(APP_INSTANCE_ID)
        recent_runs = list_saved_runs(limit=1)
        latest_run = recent_runs[0]["summary"] if recent_runs else None
        due_schedules = []
        next_trigger_at = None
        now = datetime.now(UTC)
        for item in schedules:
            last = item.last_triggered_at or item.created_at
            due_at = last + timedelta(seconds=item.interval_seconds or 0)
            if item.status == "active" and due_at <= now:
                due_schedules.append(item.schedule_id)
            if next_trigger_at is None or due_at < next_trigger_at:
                next_trigger_at = due_at
        state = self.load_tick_state()
        status = {
            "registered": bool(schedules),
            "schedule_count": len(schedules),
            "schedules": [item.model_dump(mode="json") for item in schedules],
            "pending_task_count": sum(1 for task in overview.pending_tasks if task == REGRESSION_CYCLE_TASK_NAME),
            "latest_run": latest_run,
            "due_schedule_ids": due_schedules,
            "due_now": bool(due_schedules),
            "next_trigger_at": None if next_trigger_at is None else next_trigger_at.isoformat().replace("+00:00", "Z"),
            "last_tick_at": state.get("last_tick_at"),
            "last_tick_decision": state.get("last_tick_decision"),
            "last_tick_triggered": state.get("last_tick_triggered"),
            "last_cycle_result": state.get("last_cycle_result"),
            "last_failure_at": state.get("last_failure_at"),
            "consecutive_failures": state.get("consecutive_failures", 0),
            "degraded": state.get("degraded", False),
            "retry_pending": state.get("retry_pending", False),
        }
        if driver_status is not None:
            status["driver"] = driver_status
            last_cycle = status.get("last_cycle_result") or {}
            last_decision = status.get("last_tick_decision")
            consecutive_failures = status.get("consecutive_failures", 0)
            degraded = status.get("degraded", False)
            retry_pending = status.get("retry_pending", False)
            if degraded:
                automation_health = "degraded"
                attention_reason = "consecutive_failures"
            elif retry_pending:
                automation_health = "warning"
                attention_reason = "retry_pending"
            else:
                automation_health = "healthy"
                attention_reason = ""
            status["automation_control"] = {
                "driver": driver_status,
                "schedule_registered": status["registered"],
                "due_now": status["due_now"],
                "next_trigger_at": status["next_trigger_at"],
                "last_tick_at": status.get("last_tick_at"),
                "last_tick_decision": last_decision,
                "last_cycle_run_id": last_cycle.get("run_id"),
                "last_cycle_error": last_cycle.get("error"),
                "last_cycle_error_type": last_cycle.get("error_type"),
                "last_failure_at": status.get("last_failure_at"),
                "consecutive_failures": consecutive_failures,
                "degraded": degraded,
                "retry_pending": retry_pending,
                "automation_health": automation_health,
                "attention_reason": attention_reason,
                "last_tick_outcome": (
                    "failed" if last_decision == "failed_cycle" else
                    "triggered" if last_decision == "triggered_due" else
                    "skipped"
                ),
            }
            operator_summary = build_regression_operator_summary(
                memory=self._refinement_memory,
                nightly_status={
                    "automation_control": status["automation_control"],
                },
            )
            governance = operator_summary.get("refinement", {}).get("governance", {})
            cross = governance.get("cross_level_summary") or {}
            status["automation_control"]["governance_attention"] = {
                "priority_domain": operator_summary.get("refinement", {}).get("priority_domain"),
                "priority_family": operator_summary.get("refinement", {}).get("priority_family"),
                "priority_subdomain_candidate": operator_summary.get("refinement", {}).get("priority_subdomain_candidate"),
                "priority_signal": operator_summary.get("refinement", {}).get("priority_signal"),
                "recommended_action": operator_summary.get("refinement", {}).get("recommended_action"),
                "priority_lane": cross.get("priority_lane"),
                "family_warning_density": cross.get("family_warning_density", {}).get(operator_summary.get("refinement", {}).get("priority_family") or ""),
                "subdomain_warning_density": cross.get("subdomain_warning_density", {}).get(operator_summary.get("refinement", {}).get("priority_subdomain_candidate") or ""),
            }
        return status

    def record_tick(self, *, decision: str, triggered: bool, cycle: dict[str, Any] | None = None, nightly_status: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.load_tick_state()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        consecutive_failures = int(state.get("consecutive_failures") or 0)
        last_failure_at = state.get("last_failure_at")
        if decision == "failed_cycle":
            consecutive_failures += 1
            last_failure_at = now
        elif decision == "triggered_due":
            consecutive_failures = 0
        degraded = consecutive_failures >= 2
        retry_pending = decision == "failed_cycle"
        state.update({
            "last_tick_at": now,
            "last_tick_decision": decision,
            "last_tick_triggered": triggered,
            "last_cycle_result": cycle,
            "last_nightly_status": nightly_status,
            "last_failure_at": last_failure_at,
            "consecutive_failures": consecutive_failures,
            "degraded": degraded,
            "retry_pending": retry_pending,
        })
        self.save_tick_state(state)
        return state

    def run_cycle(self, client: Any) -> dict[str, Any]:
        return run_regression_governance_cycle(make_testclient_poster(client), memory=self._refinement_memory)

    def build_governance_execution_preflight(self, *, nightly_status: dict[str, Any] | None = None) -> dict[str, Any]:
        summary = build_regression_operator_summary(
            memory=self._refinement_memory,
            nightly_status=nightly_status,
        )
        governance = summary.get("refinement", {}).get("governance", {})
        selection = governance.get("rollout_selection") or {}
        packet = governance.get("rollout_review_packet") or {}
        queue_id = selection.get("recommended_queue_id")
        priority_tier = selection.get("recommended_priority_tier")
        automation_attention = packet.get("automation_attention") or {}
        automation_control = (nightly_status or {}).get("automation_control") or {}
        automation_health = automation_control.get("automation_health") or automation_attention.get("health") or "healthy"
        control_attention_reason = automation_control.get("attention_reason") or automation_attention.get("reason") or ""
        last_tick_outcome = automation_control.get("last_tick_outcome") or automation_attention.get("last_tick_outcome") or "unknown"
        consecutive_failures = int(automation_control.get("consecutive_failures") or 0)
        retry_pending = bool(automation_control.get("retry_pending") or False)
        priority_lane = packet.get("priority_lane") or ""

        base = {
            "recommended_queue_id": queue_id,
            "priority_tier": priority_tier,
            "automation_health": automation_health,
            "automation_attention_reason": control_attention_reason,
            "last_tick_outcome": last_tick_outcome,
            "consecutive_failures": consecutive_failures,
        }

        if self._refinement_rollout is None:
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="blocked",
                hold_reason=PREFLIGHT_HOLD_ROLLOUT_SERVICE_UNAVAILABLE,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
                review_reason=PREFLIGHT_REVIEW_REASON_SERVICE_UNAVAILABLE,
            ).to_payload()
        if not queue_id:
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="blocked",
                hold_reason=PREFLIGHT_HOLD_NO_RECOMMENDED_QUEUE,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
                review_reason=PREFLIGHT_REVIEW_REASON_SELECTION_MISSING,
            ).to_payload()

        queue_item = next((item for item in self._refinement_memory.list_queue(APP_INSTANCE_ID) if item.queue_id == queue_id), None)
        if queue_item is None:
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="blocked",
                hold_reason=PREFLIGHT_HOLD_RECOMMENDED_QUEUE_MISSING,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
                review_reason=PREFLIGHT_REVIEW_REASON_QUEUE_MISSING,
            ).to_payload()
        if queue_item.status != "queued":
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="blocked",
                hold_reason=f"queue_status_blocked:{queue_item.status}",
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_QUEUE_STATE,
                review_reason=PREFLIGHT_REVIEW_REASON_QUEUE_STATE_BLOCKED,
                queue_status=queue_item.status,
            ).to_payload()
        if automation_health == "degraded" or control_attention_reason == "consecutive_failures":
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="high",
                hold_reason=PREFLIGHT_HOLD_AUTOMATION_DEGRADED_REQUIRES_REVIEW,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION,
                review_reason=PREFLIGHT_REVIEW_REASON_AUTOMATION_DEGRADED,
                queue_status=queue_item.status,
                priority_lane=priority_lane,
            ).to_payload()
        if retry_pending or automation_health == "warning" or control_attention_reason == "retry_pending":
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="medium",
                hold_reason=PREFLIGHT_HOLD_AUTOMATION_RETRY_PENDING_REQUIRES_REVIEW,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION,
                review_reason=PREFLIGHT_REVIEW_REASON_AUTOMATION_RETRY_PENDING,
                queue_status=queue_item.status,
                priority_lane=priority_lane,
            ).to_payload()
        if priority_tier == "primary":
            return build_governance_preflight_decision(
                base=base,
                can_apply=True,
                apply_risk="medium",
                hold_reason=PREFLIGHT_HOLD_NONE,
                review_scope=PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK,
                review_reason=PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY,
                queue_status=queue_item.status,
                priority_lane=priority_lane,
            ).to_payload()
        if priority_tier == "secondary":
            return build_governance_preflight_decision(
                base=base,
                can_apply=False,
                apply_risk="medium",
                hold_reason=PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW,
                review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
                review_reason=PREFLIGHT_REVIEW_REASON_PRIORITY_SECONDARY,
                queue_status=queue_item.status,
                priority_lane=priority_lane,
            ).to_payload()
        return build_governance_preflight_decision(
            base=base,
            can_apply=False,
            apply_risk="high",
            hold_reason=f"priority_tier_blocked:{priority_tier or 'none'}",
            review_scope=PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED,
            review_reason=PREFLIGHT_REVIEW_REASON_PRIORITY_TIER_BLOCKED,
            queue_status=queue_item.status,
            priority_lane=priority_lane,
        ).to_payload()

    def apply_governance_selected_rollout(self, *, nightly_status: dict[str, Any] | None = None) -> dict[str, Any]:
        preflight = self.build_governance_execution_preflight(nightly_status=nightly_status)
        if not preflight.get("can_apply"):
            return {"applied": False, "reason": preflight.get("hold_reason"), "preflight": preflight}
        if self._refinement_rollout is None:
            return {"applied": False, "reason": "rollout_service_unavailable", "preflight": preflight}

        summary = build_regression_operator_summary(
            memory=self._refinement_memory,
            nightly_status=nightly_status,
        )
        governance = summary.get("refinement", {}).get("governance", {})
        selection = governance.get("rollout_selection") or {}
        packet = governance.get("rollout_review_packet") or {}
        queue_id = selection.get("recommended_queue_id")
        if not queue_id:
            return {"applied": False, "reason": "no_recommended_queue"}

        priority_tier = selection.get("recommended_priority_tier")
        if priority_tier not in {"primary", "secondary"}:
            return {"applied": False, "reason": f"priority_tier_blocked:{priority_tier or 'none'}", "queue_id": queue_id}

        note = (
            f"governance_auto_apply::{priority_tier}::"
            f"{packet.get('selection_reason') or 'unspecified'}::"
            f"{packet.get('priority_lane') or 'unclassified'}"
        )
        item = self._refinement_rollout.transition(queue_id=queue_id, action="apply", reviewer="governance", note=note)
        return {
            "applied": True,
            "queue_id": queue_id,
            "priority_tier": priority_tier,
            "selection_reason": packet.get("selection_reason"),
            "preflight": preflight,
            "item": item.model_dump(mode="json"),
        }


    def trigger_due_tick(self, *, client: Any, driver_status: dict[str, Any] | None = None, auto_apply_governance: bool = False) -> dict[str, Any]:
        snapshot = self.build_nightly_status(driver_status)
        if not snapshot["due_now"]:
            state = self.record_tick(decision="skipped_not_due", triggered=False, nightly_status=snapshot)
            refreshed = dict(snapshot)
            refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
            return {"triggered": False, "nightly_status": refreshed}

        trigger_results = self._scheduler.trigger_interval_schedules(APP_INSTANCE_ID)
        matched = [item.model_dump(mode="json") for item in trigger_results if item.task_name == REGRESSION_CYCLE_TASK_NAME and item.triggered]
        if not matched:
            snapshot = self.build_nightly_status(driver_status)
            state = self.record_tick(decision="skipped_no_trigger_match", triggered=False, nightly_status=snapshot)
            refreshed = dict(snapshot)
            refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
            return {"triggered": False, "nightly_status": refreshed, "schedule_results": [item.model_dump(mode="json") for item in trigger_results]}

        try:
            cycle_result = self.run_cycle(client)
        except Exception as exc:
            snapshot = self.build_nightly_status(driver_status)
            state = self.record_tick(
                decision="failed_cycle",
                triggered=False,
                cycle={"error": str(exc), "error_type": exc.__class__.__name__},
                nightly_status=snapshot,
            )
            raise
        self._runtime_host.consume_pending_tasks(APP_INSTANCE_ID, REGRESSION_CYCLE_TASK_NAME)
        snapshot = self.build_nightly_status(driver_status)
        state = self.record_tick(decision="triggered_due", triggered=True, cycle=cycle_result, nightly_status=snapshot)
        refreshed = dict(snapshot)
        refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
        governance_rollout = None
        if auto_apply_governance:
            governance_rollout = self.apply_governance_selected_rollout(nightly_status={"automation_control": refreshed.get("automation_control")})
        return {
            "triggered": True,
            "schedule_results": [item.model_dump(mode="json") for item in trigger_results],
            "cycle": cycle_result,
            "nightly_status": refreshed,
            "governance_rollout": governance_rollout,
        }

    def trigger_manual_cycle(self, *, client: Any, auto_apply_governance: bool = False) -> dict[str, Any]:
        trigger_results = self._scheduler.trigger_interval_schedules(APP_INSTANCE_ID)
        matched = [item.model_dump(mode="json") for item in trigger_results if item.task_name == REGRESSION_CYCLE_TASK_NAME and item.triggered]
        if not matched:
            return {"triggered": False, "schedule_results": [item.model_dump(mode="json") for item in trigger_results]}
        cycle_result = self.run_cycle(client)
        self._runtime_host.consume_pending_tasks(APP_INSTANCE_ID, REGRESSION_CYCLE_TASK_NAME)
        governance_rollout = None
        if auto_apply_governance:
            governance_rollout = self.apply_governance_selected_rollout(nightly_status=self.build_nightly_status())
        return {
            "triggered": True,
            "schedule_results": [item.model_dump(mode="json") for item in trigger_results],
            "cycle": cycle_result,
            "governance_rollout": governance_rollout,
        }
