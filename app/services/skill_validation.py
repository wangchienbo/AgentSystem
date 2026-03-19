from __future__ import annotations

from app.models.skill_control import SkillRegistryEntry
from app.services.skill_control import SkillControlError, SkillControlService
from app.services.skill_manifest_validator import SkillManifestValidationError, SkillManifestValidatorService
from app.services.schema_registry import SchemaRegistryService


class SkillValidationError(ValueError):
    pass


class SkillValidationService:
    def __init__(
        self,
        skill_control: SkillControlService,
        manifest_validator: SkillManifestValidatorService | None = None,
        schema_registry: SchemaRegistryService | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._manifest_validator = manifest_validator or SkillManifestValidatorService(schema_registry=schema_registry)

    def validate_skill_exists(self, skill_id: str) -> SkillRegistryEntry:
        try:
            entry = self._skill_control.get_skill(skill_id)
        except SkillControlError as error:
            raise SkillValidationError(f"Required skill not found: {skill_id}") from error
        try:
            self._manifest_validator.validate(entry)
        except SkillManifestValidationError as error:
            raise SkillValidationError(f"Invalid skill manifest for {skill_id}: {error}") from error
        return entry

    def validate_runtime_skill(self, skill_id: str) -> SkillRegistryEntry:
        entry = self.validate_skill_exists(skill_id)
        if entry.capability_profile.runtime_criticality == "C0_build_only":
            raise SkillValidationError(f"Build-only skill cannot be used in runtime workflow steps: {skill_id}")
        return entry
