from __future__ import annotations

from datetime import UTC, datetime

from app.models.scheduling import ScheduleRecord, ScheduleTriggerResult
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


class SchedulerError(ValueError):
    pass


class SchedulerService:
    def __init__(self, lifecycle: AppLifecycleService, runtime_host: AppRuntimeHostService, store: RuntimeStateStore | None = None) -> None:
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._schedules: dict[str, ScheduleRecord] = {}
        self._store = store

    def register_schedule(self, record: ScheduleRecord) -> ScheduleRecord:
        self._lifecycle.get_instance(record.app_instance_id)
        self._validate_record(record)
        self._schedules[record.schedule_id] = record
        self._persist()
        return record

    def list_schedules(self, app_instance_id: str | None = None) -> list[ScheduleRecord]:
        schedules = list(self._schedules.values())
        if app_instance_id is None:
            return schedules
        return [item for item in schedules if item.app_instance_id == app_instance_id]

    def trigger_interval_schedules(self, app_instance_id: str | None = None) -> list[ScheduleTriggerResult]:
        results: list[ScheduleTriggerResult] = []
        for schedule in self.list_schedules(app_instance_id):
            if schedule.trigger_type != "interval":
                continue
            results.append(self._trigger(schedule, reason="interval tick"))
        return results

    def emit_event(self, event_name: str, app_instance_id: str | None = None) -> list[ScheduleTriggerResult]:
        results: list[ScheduleTriggerResult] = []
        for schedule in self.list_schedules(app_instance_id):
            if schedule.trigger_type != "event":
                continue
            if schedule.event_name != event_name:
                continue
            results.append(self._trigger(schedule, reason=f"event:{event_name}"))
        return results

    def pause_schedule(self, schedule_id: str) -> ScheduleRecord:
        schedule = self.get_schedule(schedule_id)
        schedule.status = "paused"
        self._persist()
        return schedule

    def resume_schedule(self, schedule_id: str) -> ScheduleRecord:
        schedule = self.get_schedule(schedule_id)
        schedule.status = "active"
        self._persist()
        return schedule

    def disable_schedule(self, schedule_id: str) -> ScheduleRecord:
        schedule = self.get_schedule(schedule_id)
        schedule.status = "disabled"
        self._persist()
        return schedule

    def get_schedule(self, schedule_id: str) -> ScheduleRecord:
        if schedule_id not in self._schedules:
            raise SchedulerError(f"Schedule not found: {schedule_id}")
        return self._schedules[schedule_id]

    def _trigger(self, schedule: ScheduleRecord, reason: str) -> ScheduleTriggerResult:
        if schedule.status != "active":
            return ScheduleTriggerResult(
                schedule_id=schedule.schedule_id,
                app_instance_id=schedule.app_instance_id,
                task_name=schedule.task_name,
                triggered=False,
                reason=f"schedule is {schedule.status}",
                pending_tasks=self._runtime_host.get_overview(schedule.app_instance_id).pending_tasks,
            )
        pending_tasks = self._runtime_host.enqueue_task(schedule.app_instance_id, schedule.task_name)
        schedule.last_triggered_at = datetime.now(UTC)
        self._persist()
        return ScheduleTriggerResult(
            schedule_id=schedule.schedule_id,
            app_instance_id=schedule.app_instance_id,
            task_name=schedule.task_name,
            triggered=True,
            reason=reason,
            pending_tasks=pending_tasks,
        )

    def _validate_record(self, record: ScheduleRecord) -> None:
        if record.trigger_type == "interval" and record.interval_seconds is None:
            raise SchedulerError("Interval schedule requires interval_seconds")
        if record.trigger_type == "event" and not record.event_name:
            raise SchedulerError("Event schedule requires event_name")

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("runtime_schedules", self._schedules)
