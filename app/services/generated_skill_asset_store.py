from __future__ import annotations

import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillAsset, GeneratedSkillRequest
from app.models.skill_asset import SkillAssetMetadata
from app.services.skill_asset_service import SkillAssetService


class GeneratedSkillAssetStore:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._asset_service = SkillAssetService(base_dir)

    def create_scaffold(self, request: GeneratedSkillRequest) -> GeneratedSkillAsset:
        asset, _metadata = self.create_scaffold_with_metadata(request)
        return asset

    def create_scaffold_with_metadata(self, request: GeneratedSkillRequest) -> tuple[GeneratedSkillAsset, SkillAssetMetadata]:
        return self._asset_service.create_asset_scaffold(request, adapter_kind="executable", status="candidate")

    def promote_candidate_to_core(self, skill_id: str, accepted_by: str = "") -> SkillAssetMetadata:
        return self._asset_service.promote_candidate_to_core(skill_id, accepted_by=accepted_by)

    def list_assets(self, status: str | None = None):
        return self._asset_service.list_assets(status=status)

    def check_consistency(self, skill_id: str | None = None):
        return self._asset_service.check_consistency(skill_id=skill_id)

    def rebuild_index(self):
        return self._asset_service.rebuild_index()
