from __future__ import annotations

from datetime import UTC, datetime

from app.models.app_blueprint import AppBlueprint
from app.models.registry import AppReleaseComparison, AppReleaseHistorySummary, AppReleaseRecord, AppRegistryEntry
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
        initial_release = AppReleaseRecord(
            version=blueprint.version,
            status="active",
            approved_at=datetime.now(UTC),
            app_shape=blueprint.app_shape,
            required_skills=list(blueprint.required_skills),
            runtime_policy=blueprint.runtime_policy.model_dump(mode="json"),
            runtime_profile=blueprint.runtime_profile.model_dump(mode="json"),
        )
        entry = AppRegistryEntry(
            blueprint_id=blueprint.id,
            name=blueprint.name,
            version=blueprint.version,
            description=description or blueprint.goal,
            release_status="active",
            approved_at=initial_release.approved_at,
            releases=[initial_release],
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

    def list_releases(self, blueprint_id: str) -> list[AppReleaseRecord]:
        entry = self.get_entry(blueprint_id)
        return [release.model_copy(deep=True) for release in entry.releases]

    def get_release_history(self, blueprint_id: str) -> AppReleaseHistorySummary:
        entry = self.get_entry(blueprint_id)
        releases = sorted(entry.releases, key=lambda item: item.created_at, reverse=True)
        latest_release = releases[0] if releases else None
        latest_draft = next((item for item in releases if item.status == "draft"), None)
        rollback_target = next((item for item in releases if item.status == "superseded"), None)
        return AppReleaseHistorySummary(
            blueprint_id=blueprint_id,
            active_version=entry.version,
            active_release_status=entry.release_status,
            total_releases=len(entry.releases),
            draft_release_count=sum(1 for item in entry.releases if item.status == "draft"),
            superseded_release_count=sum(1 for item in entry.releases if item.status == "superseded"),
            rolled_back_release_count=sum(1 for item in entry.releases if item.status == "rolled_back"),
            latest_release_version="" if latest_release is None else latest_release.version,
            latest_release_created_at=None if latest_release is None else latest_release.created_at,
            latest_draft_version=None if latest_draft is None else latest_draft.version,
            latest_draft_created_at=None if latest_draft is None else latest_draft.created_at,
            rollback_target_version=None if rollback_target is None else rollback_target.version,
            releases=[item.model_copy(deep=True) for item in releases],
        )

    def add_release(
        self,
        blueprint_id: str,
        version: str,
        note: str = "",
        reviewer: str = "",
        activate_immediately: bool = False,
    ) -> AppRegistryEntry:
        entry = self.get_entry(blueprint_id)
        if any(release.version == version for release in entry.releases):
            raise AppRegistryError(f"App release already exists: {blueprint_id}@{version}")

        blueprint = self.get_blueprint(blueprint_id)
        release = AppReleaseRecord(
            version=version,
            status="draft",
            note=note,
            reviewer=reviewer,
            app_shape=blueprint.app_shape,
            required_skills=list(blueprint.required_skills),
            runtime_policy=blueprint.runtime_policy.model_dump(mode="json"),
            runtime_profile=blueprint.runtime_profile.model_dump(mode="json"),
        )
        entry.releases.append(release)
        if activate_immediately:
            activated = self.activate_release(blueprint_id, version, reviewer=reviewer)
            if note and not activated.release_note:
                activated.release_note = note
            return activated
        self._persist()
        return entry

    def activate_release(self, blueprint_id: str, version: str, reviewer: str = "") -> AppRegistryEntry:
        entry = self.get_entry(blueprint_id)
        target = next((release for release in entry.releases if release.version == version), None)
        if target is None:
            raise AppRegistryError(f"App release not found: {blueprint_id}@{version}")

        now = datetime.now(UTC)
        for release in entry.releases:
            if release.version == version:
                release.status = "active"
                release.reviewer = reviewer or release.reviewer
                release.approved_at = now
            elif release.status == "active":
                release.status = "superseded"

        entry.version = target.version
        entry.release_status = target.status
        entry.release_note = target.note
        entry.reviewer = target.reviewer
        entry.approved_at = target.approved_at
        entry.rollback_reason = target.rollback_reason
        entry.app_shape = target.app_shape or entry.app_shape
        if target.runtime_profile:
            entry.runtime_profile_summary = entry.runtime_profile_summary.model_validate(target.runtime_profile)
        self._persist()
        return entry

    def rollback_release(
        self,
        blueprint_id: str,
        target_version: str,
        reviewer: str = "",
        rollback_reason: str = "",
    ) -> AppRegistryEntry:
        entry = self.get_entry(blueprint_id)
        target = next((release for release in entry.releases if release.version == target_version), None)
        if target is None:
            raise AppRegistryError(f"App release not found: {blueprint_id}@{target_version}")

        now = datetime.now(UTC)
        for release in entry.releases:
            if release.version == target_version:
                release.status = "active"
                release.reviewer = reviewer or release.reviewer
                release.rollback_reason = rollback_reason
                release.approved_at = now
            elif release.status == "active":
                release.status = "rolled_back"

        entry.version = target.version
        entry.release_status = target.status
        entry.release_note = target.note
        entry.reviewer = target.reviewer
        entry.approved_at = target.approved_at
        entry.rollback_reason = rollback_reason
        entry.app_shape = target.app_shape or entry.app_shape
        if target.runtime_profile:
            entry.runtime_profile_summary = entry.runtime_profile_summary.model_validate(target.runtime_profile)
        self._persist()
        return entry

    def compare_releases(self, blueprint_id: str, from_version: str, to_version: str) -> AppReleaseComparison:
        entry = self.get_entry(blueprint_id)
        from_release = next((release for release in entry.releases if release.version == from_version), None)
        to_release = next((release for release in entry.releases if release.version == to_version), None)
        if from_release is None:
            raise AppRegistryError(f"App release not found: {blueprint_id}@{from_version}")
        if to_release is None:
            raise AppRegistryError(f"App release not found: {blueprint_id}@{to_version}")

        comparison = AppReleaseComparison(
            blueprint_id=blueprint_id,
            from_version=from_version,
            to_version=to_version,
            active_version=entry.version,
            active_is_from=entry.version == from_version,
            active_is_to=entry.version == to_version,
            from_status=from_release.status,
            to_status=to_release.status,
            from_note=from_release.note,
            to_note=to_release.note,
            from_reviewer=from_release.reviewer,
            to_reviewer=to_release.reviewer,
            from_created_at=from_release.created_at,
            to_created_at=to_release.created_at,
            app_shape_from=from_release.app_shape,
            app_shape_to=to_release.app_shape,
        )
        changed: list[str] = []

        if from_release.note != to_release.note:
            comparison.release_note_changed = True
            changed.append("release_note")

        from_skills = set(from_release.required_skills)
        to_skills = set(to_release.required_skills)
        comparison.required_skills_added = sorted(to_skills - from_skills)
        comparison.required_skills_removed = sorted(from_skills - to_skills)
        if comparison.required_skills_added or comparison.required_skills_removed:
            comparison.required_skills_changed = True
            changed.append("required_skills")

        runtime_policy_keys = sorted(set(from_release.runtime_policy) | set(to_release.runtime_policy))
        comparison.runtime_policy_changes = {
            key: {"from": from_release.runtime_policy.get(key), "to": to_release.runtime_policy.get(key)}
            for key in runtime_policy_keys
            if from_release.runtime_policy.get(key) != to_release.runtime_policy.get(key)
        }
        if comparison.runtime_policy_changes:
            comparison.runtime_policy_changed = True
            changed.append("runtime_policy")

        runtime_profile_keys = sorted(set(from_release.runtime_profile) | set(to_release.runtime_profile))
        comparison.runtime_profile_changes = {
            key: {"from": from_release.runtime_profile.get(key), "to": to_release.runtime_profile.get(key)}
            for key in runtime_profile_keys
            if from_release.runtime_profile.get(key) != to_release.runtime_profile.get(key)
        }
        if comparison.runtime_profile_changes:
            comparison.runtime_profile_changed = True
            changed.append("runtime_profile")

        if from_release.app_shape != to_release.app_shape:
            comparison.app_shape_changed = True
            changed.append("app_shape")

        comparison.changed_fields = changed
        comparison.change_count = len(changed)
        comparison.summary = "No changes detected" if not changed else "Changed: " + ", ".join(changed)
        return comparison

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("registry_entries", self._entries)
        self._store.save_mapping("registry_blueprints", self._blueprints)
