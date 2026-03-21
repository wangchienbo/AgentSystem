from __future__ import annotations

from app.models.skill_control import SkillRegistryEntry
from app.services.schema_registry import SchemaRegistryError, SchemaRegistryService


class SkillManifestValidationError(ValueError):
    pass


class SkillManifestValidatorService:
    def __init__(self, schema_registry: SchemaRegistryService | None = None) -> None:
        self._schema_registry = schema_registry

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
        if manifest.adapter.kind != manifest.runtime_adapter:
            raise SkillManifestValidationError("Manifest adapter kind must match manifest runtime_adapter")
        if manifest.runtime_adapter == "callable" and not isinstance(manifest.adapter.entry, str):
            raise SkillManifestValidationError("Callable adapter entry must be a string")
        if manifest.runtime_adapter == "script" and not isinstance(manifest.adapter.command, list):
            raise SkillManifestValidationError("Script adapter command must be a list")
        contract = manifest.contract
        if not isinstance(contract.input_schema_ref, str) or not isinstance(contract.output_schema_ref, str) or not isinstance(contract.error_schema_ref, str):
            raise SkillManifestValidationError("Manifest contract refs must be strings")
        if self._schema_registry is not None:
            for schema_ref in [contract.input_schema_ref, contract.output_schema_ref, contract.error_schema_ref]:
                if not schema_ref:
                    continue
                try:
                    self._schema_registry.resolve(schema_ref)
                except SchemaRegistryError as error:
                    raise SkillManifestValidationError(str(error)) from error
