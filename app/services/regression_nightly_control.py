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
    ) -> None:
        self._scheduler = scheduler
        self._runtime_host = runtime_host
        self._runtime_store = runtime_store
        self._refinement_memory = refinement_memory

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
        }
        if driver_status is not None:
            status["driver"] = driver_status
            status["automation_control"] = {
                "driver": driver_status,
                "schedule_registered": status["registered"],
                "due_now": status["due_now"],
                "next_trigger_at": status["next_trigger_at"],
                "last_tick_at": status.get("last_tick_at"),
                "last_tick_decision": status.get("last_tick_decision"),
                "last_cycle_run_id": None if not status.get("last_cycle_result") else status["last_cycle_result"].get("run_id"),
            }
        return status

    def record_tick(self, *, decision: str, triggered: bool, cycle: dict[str, Any] | None = None, nightly_status: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.load_tick_state()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        state.update({
            "last_tick_at": now,
            "last_tick_decision": decision,
            "last_tick_triggered": triggered,
            "last_cycle_result": cycle,
            "last_nightly_status": nightly_status,
        })
        self.save_tick_state(state)
        return state

    def run_cycle(self, client: Any) -> dict[str, Any]:
        return run_regression_governance_cycle(make_testclient_poster(client), memory=self._refinement_memory)


    def trigger_due_tick(self, *, client: Any, driver_status: dict[str, Any] | None = None) -> dict[str, Any]:
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

        cycle_result = self.run_cycle(client)
        self._runtime_host.consume_pending_tasks(APP_INSTANCE_ID, REGRESSION_CYCLE_TASK_NAME)
        snapshot = self.build_nightly_status(driver_status)
        state = self.record_tick(decision="triggered_due", triggered=True, cycle=cycle_result, nightly_status=snapshot)
        refreshed = dict(snapshot)
        refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
        return {
            "triggered": True,
            "schedule_results": [item.model_dump(mode="json") for item in trigger_results],
            "cycle": cycle_result,
            "nightly_status": refreshed,
        }
