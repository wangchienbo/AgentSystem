from __future__ import annotations

import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.services.generated_skill_asset_store import GeneratedSkillAssetStore
from app.services.skill_control import SkillControlService


class ScriptSkillGenerator:
    def __init__(self, asset_store: GeneratedSkillAssetStore, skill_control: SkillControlService) -> None:
        self._asset_store = asset_store
        self._skill_control = skill_control

    def generate_and_register(self, request: GeneratedSkillRequest) -> SkillRegistryEntry:
        asset = self._asset_store.create_scaffold(request)
        manifest = json.loads(Path(asset.manifest_path).read_text())
        entry = SkillRegistryEntry(
            skill_id=request.skill_id,
            name=request.name,
            active_version="0.1.0",
            versions=[SkillVersion(version="0.1.0", content="generated")],
            runtime_adapter="executable",
            capability_profile=SkillCapabilityProfile(
                intelligence_level="L0_deterministic",
                network_requirement="N0_none",
                runtime_criticality="C2_required_runtime",
                execution_locality="local",
                invocation_default="automatic",
                risk_level="R1_local_write",
            ),
            manifest=SkillManifest(
                skill_id=manifest["skill_id"],
                name=manifest["name"],
                version=manifest["version"],
                description=manifest["description"],
                runtime_adapter=manifest["runtime_adapter"],
                adapter=SkillAdapterSpec(**manifest["adapter"]),
                contract=SkillContractRef(**manifest["contract"]),
                tags=manifest["tags"],
                risk=SkillManifestRisk(**manifest["risk"]),
            ),
            origin="generated",
        )
        self._skill_control.register(entry)
        return entry
