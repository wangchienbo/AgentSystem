from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.models.app_instance import AppInstance
from app.persistence.runtime_state_store import RuntimeStateStore


class DraftAppService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store or RuntimeStateStore()
        self._apps: dict[str, AppInstance] = {}
        self._load()

    def create_draft_app(self, owner_user_id: str, name: str, goal: str = "") -> AppInstance:
        app_id = f"app_draft_{uuid4().hex[:8]}"
        app = AppInstance(
            id=app_id,
            blueprint_id=name,
            owner_user_id=owner_user_id,
            status="draft",
            data_namespace=f"draft.{owner_user_id}.{app_id}",
        )
        self._apps[app_id] = app
        self._save()
        return app

    def get_app(self, app_id: str) -> AppInstance | None:
        return self._apps.get(app_id)

    def mark_ready_for_lifecycle(self, app_id: str) -> AppInstance | None:
        app = self._apps.get(app_id)
        if app is None:
            return None
        app.status = "compiled"
        self._apps[app_id] = app
        self._save()
        return app

    def list_apps(self, owner_user_id: str | None = None) -> list[AppInstance]:
        items = list(self._apps.values())
        if owner_user_id is not None:
            items = [item for item in items if item.owner_user_id == owner_user_id]
        return items

    def _save(self) -> None:
        self._store.save_mapping("draft_apps", self._apps)

    def _load(self) -> None:
        raw = self._store.load_json("draft_apps", {})
        apps: dict[str, AppInstance] = {}
        if not isinstance(raw, dict):
            self._apps = {}
            return
        for app_id, payload in raw.items():
            apps[app_id] = AppInstance.model_validate(payload)
        self._apps = apps
