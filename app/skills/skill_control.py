from __future__ import annotations

from app.models.skill_control import SkillMutationResult, SkillRegistryEntry, SkillVersion
from app.services.skill_manifest_validator import SkillManifestValidationError, SkillManifestValidatorService


class SkillControlError(ValueError):
    pass


class SkillControlService:
    def __init__(self, manifest_validator: SkillManifestValidatorService | None = None) -> None:
        self._skills: dict[str, SkillRegistryEntry] = {}
        self._manifest_validator = manifest_validator or SkillManifestValidatorService()

    def register(self, entry: SkillRegistryEntry) -> SkillRegistryEntry:
        try:
            self._manifest_validator.validate(entry)
        except SkillManifestValidationError as error:
            raise SkillControlError(str(error)) from error
        self._skills[entry.skill_id] = entry
        return entry

    def list_skills(self) -> list[SkillRegistryEntry]:
        return list(self._skills.values())

    def get_skill(self, skill_id: str) -> SkillRegistryEntry:
        if skill_id not in self._skills:
            raise SkillControlError(f"Skill not found: {skill_id}")
        return self._skills[skill_id]

    def replace_skill(self, skill_id: str, version: str, content: str, note: str = "") -> SkillMutationResult:
        entry = self.get_skill(skill_id)
        self._ensure_mutable(entry)
        entry.versions.append(SkillVersion(version=version, content=content, note=note))
        entry.active_version = version
        entry.status = "active"
        return SkillMutationResult(
            skill_id=skill_id,
            action="replace",
            status=entry.status,
            active_version=entry.active_version,
        )

    def rollback_skill(self, skill_id: str, target_version: str) -> SkillMutationResult:
        entry = self.get_skill(skill_id)
        self._ensure_mutable(entry)
        versions = {version.version for version in entry.versions}
        if target_version not in versions:
            raise SkillControlError(f"Rollback target not found: {target_version}")
        entry.active_version = target_version
        entry.status = "rollback_ready"
        return SkillMutationResult(
            skill_id=skill_id,
            action="rollback",
            status=entry.status,
            active_version=entry.active_version,
        )

    def disable_skill(self, skill_id: str) -> SkillMutationResult:
        entry = self.get_skill(skill_id)
        self._ensure_mutable(entry)
        entry.status = "disabled"
        return SkillMutationResult(
            skill_id=skill_id,
            action="disable",
            status=entry.status,
            active_version=entry.active_version,
        )

    def enable_skill(self, skill_id: str) -> SkillMutationResult:
        entry = self.get_skill(skill_id)
        self._ensure_mutable(entry)
        entry.status = "active"
        return SkillMutationResult(
            skill_id=skill_id,
            action="enable",
            status=entry.status,
            active_version=entry.active_version,
        )

    def _ensure_mutable(self, entry: SkillRegistryEntry) -> None:
        if entry.immutable_interface:
            raise SkillControlError(
                f"Skill {entry.skill_id} is protected by immutable interface rules and cannot be modified."
            )
