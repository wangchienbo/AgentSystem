from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from app.models.skill_creation import GeneratedSkillVersionComparison, SkillCreationRequest, SkillSchemaDefinition
from app.models.skill_control import SkillRegistryEntry
from app.services.app_data_store import AppDataStore
from app.services.skill_authoring import SkillAuthoringService
from app.services.skill_asset_service import SkillAssetService
from app.models.generated_skill import GeneratedSkillAsset, GeneratedSkillRequest


class GeneratedSkillAssetStore:
    def __init__(self, data_store: AppDataStore, authoring: SkillAuthoringService | None = None) -> None:
        self._data_store = data_store
        self._authoring = authoring or SkillAuthoringService()
        self._namespace_id = self._data_store.ensure_skill_asset_namespace().namespace_id
        self._file_asset_base_dir = self._data_store.base_path / "generated_executable_skills"
        self._file_asset_service = SkillAssetService(str(self._file_asset_base_dir))

    def persist_generated_skill(
        self,
        *,
        request: SkillCreationRequest,
        schema_refs: dict[str, str],
        entry: SkillRegistryEntry,
        version_override: str | None = None,
    ) -> None:
        existing = self.get_generated_asset(request.skill_id) or {}
        revisions = list(existing.get("revisions", []))
        revision_version = version_override or entry.active_version
        payload = {
            "version": revision_version,