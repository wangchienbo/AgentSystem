from __future__ import annotations

from app.models.skill_control import SkillRegistryEntry


class SkillManifestValidationError(ValueError):
    pass


class SkillManifestValidatorService:
    def validate(self, entry: SkillRegistryEntry) -> None:
        manifest = entry.manifest
        if manifest is None:
            return
        if manifest.skill_id != entry.skill_id:
            raise SkillManifestValidationError("Manifest skill_id must match registry skill_id")
        if manifest.name != entry.name:
            raise SkillManifestValidationError("Manifest name must match registry name")
        if manifest.version != entry.active_version:
            raise SkillManifestValidationError("Manifest version must match active_version")
        if manifest.runtime_adapter != entry.runtime_adapter:
            raise SkillManifestValidationError("Manifest runtime_adapter must match registry runtime_adapter")
        contract = manifest.contract
        if not isinstance(contract.input_schema_ref, str) or not isinstance(contract.output_schema_ref, str) or not isinstance(contract.error_schema_ref, str):
            raise SkillManifestValidationError("Manifest contract refs must be strings")
