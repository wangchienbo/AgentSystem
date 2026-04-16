from __future__ import annotations

from pathlib import Path

from app.models.skill_control import SkillRegistryEntry
from app.services.schema_registry import SchemaRegistryError, SchemaRegistryService


ALLOWED_SCRIPT_COMMAND_PREFIXES = (
    "python",
    "python3",
    "bash",
    "sh",
    "node",
    "uv",
)


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
        if manifest.runtime_adapter in {"script", "executable"}:
            adapter_label = "Script" if manifest.runtime_adapter == "script" else "Executable"
            if not isinstance(manifest.adapter.command, list):
                raise SkillManifestValidationError(f"{adapter_label} adapter command must be a list")
            if not manifest.adapter.command:
                raise SkillManifestValidationError(f"{adapter_label} adapter command must not be empty")
            command_head = manifest.adapter.command[0]
            if command_head not in ALLOWED_SCRIPT_COMMAND_PREFIXES:
                raise SkillManifestValidationError(
                    f"{adapter_label} adapter command prefix not allowed: {command_head}"
                )
            if manifest.adapter.invocation_protocol not in {"", "json_stdio"}:
                raise SkillManifestValidationError(f"{adapter_label} adapter invocation_protocol must be empty or json_stdio")
            if manifest.adapter.timeout_seconds < 1:
                raise SkillManifestValidationError(f"{adapter_label} adapter timeout_seconds must be >= 1")
            if manifest.runtime_adapter == "executable":
                entrypoint = manifest.adapter.entry.strip()
                if not entrypoint:
                    raise SkillManifestValidationError("Executable adapter entry must not be empty")
                if not Path(entrypoint).exists():
                    raise SkillManifestValidationError(f"Executable adapter entrypoint not found: {entrypoint}")
            if manifest.risk.allow_shell and command_head not in {"bash", "sh"}:
                raise SkillManifestValidationError(
                    f"allow_shell may only be set for shell-based {manifest.runtime_adapter} adapters"
                )
            if command_head in {"bash", "sh"} and not manifest.risk.allow_shell:
                raise SkillManifestValidationError(
                    f"Shell-based {manifest.runtime_adapter} adapters require risk.allow_shell=true"
                )
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
