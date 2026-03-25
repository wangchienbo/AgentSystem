from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.registry import AppRegistryEntry
from app.services.runtime_state_store import RuntimeStateStore


class AppRegistryError(ValueError):
    pass


class AppRegistryService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._blueprints: dict[str, AppBlueprint] = {}
        self._entries: dict[str, AppRegistryEntry] = {}
        self._store = store

    def register_blueprint(self, blueprint: AppBlueprint, description: str = "") -> AppRegistryEntry:
        self._blueprints[blueprint.id] = blueprint
        entry = AppRegistryEntry(
            blueprint_id=blueprint.id,
            name=blueprint.name,
            version=blueprint.version,
            description=description or blueprint.goal,
            app_shape=blueprint.app_shape,
            runtime_profile_summary=blueprint.runtime_profile,
        )
        self._entries[blueprint.id] = entry
        self._persist()
        return entry

    def get_blueprint(self, blueprint_id: str) -> AppBlueprint:
        if blueprint_id not in self._blueprints:
            raise AppRegistryError(f"App blueprint not found: {blueprint_id}")
        return self._blueprints[blueprint_id]

    def get_entry(self, blueprint_id: str) -> AppRegistryEntry:
        if blueprint_id not in self._entries:
            raise AppRegistryError(f"App registry entry not found: {blueprint_id}")
        return self._entries[blueprint_id]

    def list_entries(self) -> list[AppRegistryEntry]:
        return list(self._entries.values())

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("registry_entries", self._entries)
        self._store.save_mapping("registry_blueprints", self._blueprints)
