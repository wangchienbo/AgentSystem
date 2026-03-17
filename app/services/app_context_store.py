from __future__ import annotations

from datetime import UTC, datetime

from app.models.app_context import AppContextEntry, AppSharedContext
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_state_store import RuntimeStateStore


class AppContextStoreError(ValueError):
    pass


class AppContextStore:
    def __init__(
        self,
        lifecycle: AppLifecycleService,
        store: RuntimeStateStore | None = None,
        runtime_host: AppRuntimeHostService | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._store = store
        self._runtime_host = runtime_host
        self._contexts: dict[str, AppSharedContext] = {}
        if self._store is not None:
            self._load()

    def ensure_context(self, app_instance_id: str) -> AppSharedContext:
        existing = self._contexts.get(app_instance_id)
        if existing is not None:
            return existing
        instance = self._lifecycle.get_instance(app_instance_id)
        context = AppSharedContext(
            app_instance_id=app_instance_id,
            app_name=instance.blueprint_id,
            owner_user_id=instance.owner_user_id,
            description=f"Shared context for {instance.blueprint_id}",
            current_goal="",
            current_stage=instance.status,
        )
        self._contexts[app_instance_id] = context
        self._save()
        return context

    def list_contexts(self) -> list[AppSharedContext]:
        return list(self._contexts.values())

    def get_context(self, app_instance_id: str) -> AppSharedContext:
        context = self._contexts.get(app_instance_id)
        if context is None:
            raise AppContextStoreError(f"App context not found: {app_instance_id}")
        return context

    def update_context(
        self,
        app_instance_id: str,
        current_goal: str | None = None,
        current_stage: str | None = None,
        status: str | None = None,
    ) -> AppSharedContext:
        context = self.ensure_context(app_instance_id)
        if current_goal is not None:
            context.current_goal = current_goal
        if current_stage is not None:
            context.current_stage = current_stage
        if status is not None:
            context.status = status
        context.updated_at = datetime.now(UTC)
        self._contexts[app_instance_id] = context
        self._save()
        return context

    def append_entry(
        self,
        app_instance_id: str,
        section: str,
        key: str,
        value,
        tags: list[str] | None = None,
    ) -> AppContextEntry:
        context = self.ensure_context(app_instance_id)
        entry = AppContextEntry(
            entry_id=f"ctx.{app_instance_id}.{len(context.entries) + 1}",
            app_instance_id=app_instance_id,
            section=section,
            key=key,
            value=value,
            tags=tags or [],
        )
        context.entries.append(entry)
        context.updated_at = datetime.now(UTC)
        self._contexts[app_instance_id] = context
        self._save()
        return entry

    def get_runtime_view(self, app_instance_id: str) -> dict:
        context = self.get_context(app_instance_id)
        runtime = None
        if self._runtime_host is not None:
            try:
                runtime = self._runtime_host.get_overview(app_instance_id)
            except (RuntimeHostError, LifecycleError):
                runtime = None
        return {
            "context": context,
            "runtime": runtime,
        }

    def _save(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("app_contexts", self._contexts)

    def _load(self) -> None:
        raw = self._store.load_json("app_contexts", {})
        contexts: dict[str, AppSharedContext] = {}
        for key, value in raw.items():
            payload = dict(value)
            payload.setdefault("owner_user_id", "unknown")
            contexts[key] = AppSharedContext.model_validate(payload)
        self._contexts = contexts
