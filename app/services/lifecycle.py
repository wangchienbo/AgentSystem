from __future__ import annotations

from app.models.app_instance import AppInstance, AppStatus
from app.models.runtime import LifecycleEvent, LifecycleTransitionResult


class LifecycleError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[AppStatus, set[AppStatus]] = {
    "draft": {"validating", "archived"},
    "validating": {"compiled", "draft", "archived"},
    "compiled": {"installed", "draft", "archived"},
    "installed": {"running", "archived"},
    "running": {"paused", "stopped", "failed", "upgrading", "archived"},
    "paused": {"running", "stopped", "failed", "archived"},
    "stopped": {"running", "archived"},
    "failed": {"stopped", "running", "archived"},
    "upgrading": {"running", "failed", "stopped", "archived"},
    "archived": set(),
}

_EVENT_TO_TARGET: dict[str, AppStatus] = {
    "validate": "validating",
    "compile": "compiled",
    "install": "installed",
    "start": "running",
    "pause": "paused",
    "resume": "running",
    "stop": "stopped",
    "fail": "failed",
    "upgrade": "upgrading",
    "archive": "archived",
}


class AppLifecycleService:
    def __init__(self) -> None:
        self._instances: dict[str, AppInstance] = {}
        self._events: dict[str, list[LifecycleEvent]] = {}

    def register_instance(self, instance: AppInstance) -> AppInstance:
        self._instances[instance.id] = instance
        self._events.setdefault(instance.id, [])
        return instance

    def get_instance(self, app_instance_id: str) -> AppInstance:
        if app_instance_id not in self._instances:
            raise LifecycleError(f"App instance not found: {app_instance_id}")
        return self._instances[app_instance_id]

    def list_instances(self) -> list[AppInstance]:
        return list(self._instances.values())

    def list_events(self, app_instance_id: str) -> list[LifecycleEvent]:
        self.get_instance(app_instance_id)
        return list(self._events.get(app_instance_id, []))

    def transition(self, app_instance_id: str, event: str, reason: str = "") -> LifecycleTransitionResult:
        instance = self.get_instance(app_instance_id)
        if event not in _EVENT_TO_TARGET:
            raise LifecycleError(f"Unsupported lifecycle event: {event}")
        target = _EVENT_TO_TARGET[event]
        if target not in _ALLOWED_TRANSITIONS[instance.status]:
            raise LifecycleError(
                f"Invalid lifecycle transition for {app_instance_id}: {instance.status} -> {target}"
            )

        previous_status = instance.status
        instance.status = target
        self._events[app_instance_id].append(
            LifecycleEvent(
                app_instance_id=app_instance_id,
                event_type=event,  # type: ignore[arg-type]
                from_status=previous_status,
                to_status=target,
                reason=reason,
            )
        )
        return LifecycleTransitionResult(
            app_instance_id=app_instance_id,
            previous_status=previous_status,
            current_status=target,
            event=event,  # type: ignore[arg-type]
            recorded_events=len(self._events[app_instance_id]),
        )
