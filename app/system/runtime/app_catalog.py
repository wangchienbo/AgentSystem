from __future__ import annotations

from app.models.interaction import AppCatalogEntry


class AppCatalogError(ValueError):
    pass


class AppCatalogService:
    def __init__(self) -> None:
        self._apps: dict[str, AppCatalogEntry] = {}

    def register(self, entry: AppCatalogEntry) -> AppCatalogEntry:
        self._apps[entry.app_id] = entry
        return entry

    def list_apps(self) -> list[AppCatalogEntry]:
        return list(self._apps.values())

    def get_app(self, app_id: str) -> AppCatalogEntry:
        if app_id not in self._apps:
            raise AppCatalogError(f"App catalog entry not found: {app_id}")
        return self._apps[app_id]

    def match_command(self, text: str) -> tuple[AppCatalogEntry | None, list[str]]:
        normalized = text.strip().lower()
        best_match: AppCatalogEntry | None = None
        matched_phrases: list[str] = []
        for entry in self._apps.values():
            phrases = [phrase for phrase in entry.trigger_phrases if phrase.lower() in normalized]
            if len(phrases) > len(matched_phrases):
                best_match = entry
                matched_phrases = phrases
        return best_match, matched_phrases
