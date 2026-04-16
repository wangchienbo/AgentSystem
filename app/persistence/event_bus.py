from __future__ import annotations

from app.models.event_bus import EventPublishResult, EventRecord, EventSubscription
from app.models.scheduling import ScheduleTriggerResult
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService


class EventBusError(ValueError):
    pass


class EventBusService:
    def __init__(self, scheduler: SchedulerService, store: RuntimeStateStore | None = None) -> None:
        self._scheduler = scheduler
        self._events: list[EventRecord] = []
        self._subscriptions: dict[str, EventSubscription] = {}
        self._store = store

    def publish(
        self,
        event_name: str,
        source: str = "system",
        app_instance_id: str | None = None,
        payload: dict | None = None,
    ) -> EventPublishResult:
        event = EventRecord(
            event_id=f"evt.{len(self._events) + 1}",
            event_name=event_name,
            source=source,
            app_instance_id=app_instance_id,
            payload=payload or {},
        )
        self._events.append(event)
        trigger_results = self._scheduler.emit_event(event_name, app_instance_id=app_instance_id)
        self._persist()
        return EventPublishResult(
            event=event,
            triggered_schedule_ids=[item.schedule_id for item in trigger_results if item.triggered],
            triggered_app_ids=self._collect_app_ids(trigger_results),
        )

    def subscribe(self, subscription: EventSubscription) -> EventSubscription:
        self._subscriptions[subscription.subscription_id] = subscription
        self._persist()
        return subscription

    def list_events(self, event_name: str | None = None) -> list[EventRecord]:
        if event_name is None:
            return list(self._events)
        return [item for item in self._events if item.event_name == event_name]

    def list_subscriptions(self, event_name: str | None = None) -> list[EventSubscription]:
        subscriptions = list(self._subscriptions.values())
        if event_name is None:
            return subscriptions
        return [item for item in subscriptions if item.event_name == event_name]

    def _collect_app_ids(self, results: list[ScheduleTriggerResult]) -> list[str]:
        app_ids: list[str] = []
        for item in results:
            if item.app_instance_id not in app_ids and item.triggered:
                app_ids.append(item.app_instance_id)
        return app_ids

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_collection("event_log", self._events)
        self._store.save_mapping("event_subscriptions", self._subscriptions)
