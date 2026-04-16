"""Skill Meta Service — manage and query skill metadata for App creators.

Provides structured metadata (input/output schemas, actions, dependencies)
that creators use to compose skills into an App.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.skill_meta import ActionMeta, SkillMetaInfo


class SkillMetaService:
    """Maintains metadata registry for all known skills.

    Skills register their metadata at startup. Creators query this
    service to discover available skills and validate compositions.
    """

    def __init__(self) -> None:
        self._meta: dict[str, SkillMetaInfo] = {}

    # -- Registration ---------------------------------------------------------

    def register(self, meta: SkillMetaInfo) -> SkillMetaInfo:
        """Register or update skill metadata."""
        meta.updated_at = datetime.now(UTC)
        self._meta[meta.skill_id] = meta
        return meta

    def register_simple(
        self,
        skill_id: str,
        name: str,
        description: str = "",
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        actions: dict[str, dict] | None = None,
        dependencies: list[str] | None = None,
        offline_capable: bool = False,
        source: str = "builtin",
    ) -> SkillMetaInfo:
        """Quick registration from basic fields."""
        action_metas = {}
        if actions:
            for aname, aconfig in actions.items():
                action_metas[aname] = ActionMeta(
                    name=aname,
                    description=aconfig.get("description", ""),
                    input_schema=aconfig.get("input_schema", {}),
                    output_schema=aconfig.get("output_schema", {}),
                    timeout_default=aconfig.get("timeout", 30.0),
                )

        meta = SkillMetaInfo(
            skill_id=skill_id,
            name=name,
            description=description,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            actions=action_metas,
            dependencies=dependencies or [],
            offline_capable=offline_capable,
            source=source,
        )
        return self.register(meta)

    def unregister(self, skill_id: str) -> bool:
        return self._meta.pop(skill_id, None) is not None

    # -- Query ----------------------------------------------------------------

    def get(self, skill_id: str) -> SkillMetaInfo | None:
        return self._meta.get(skill_id)

    def list_all(self) -> list[SkillMetaInfo]:
        return list(self._meta.values())

    def list_available_for_app(self, *, offline_only: bool = False) -> list[SkillMetaInfo]:
        """Skills suitable for a particular app type."""
        skills = list(self._meta.values())
        if offline_only:
            skills = [s for s in skills if s.offline_capable]
        return skills

    def search(self, query: str) -> list[SkillMetaInfo]:
        """Search skills by name, description, or action."""
        q = query.lower()
        results = []
        for meta in self._meta.values():
            if (
                q in meta.name.lower()
                or q in meta.description.lower()
                or any(q in a.description.lower() for a in meta.actions.values())
            ):
                results.append(meta)
        return results

    # -- Validation -----------------------------------------------------------

    def validate_composition(
        self,
        skills: list[str],
    ) -> dict[str, Any]:
        """Validate that a set of skills can be composed together.

        Checks:
        - All skills exist
        - Dependencies are satisfied
        - No circular dependencies
        """
        issues: list[str] = []
        warnings: list[str] = []

        # Check existence
        registered = set(self._meta.keys())
        for sid in skills:
            if sid not in registered:
                issues.append(f"Skill not registered: {sid}")

        if issues:
            return {"valid": False, "issues": issues, "warnings": warnings}

        # Check dependencies
        for sid in skills:
            meta = self._meta[sid]
            for dep in meta.dependencies:
                if dep not in skills and dep not in registered:
                    issues.append(f"Missing dependency: {sid} requires {dep}")
                elif dep not in skills:
                    warnings.append(f"External dependency: {sid} requires {dep} (not in app)")

        # Check offline consistency
        any_offline = any(self._meta[s].offline_capable for s in skills if s in self._meta)
        all_offline = all(self._meta[s].offline_capable for s in skills if s in self._meta)
        if any_offline and not all_offline:
            warnings.append("Mixed offline/online skills — app will not work fully offline")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def get_compatibility_report(
        self,
        upstream_skill: str,
        downstream_skill: str,
        action: str = "execute",
    ) -> dict[str, Any]:
        """Check if upstream output is compatible with downstream input."""
        up_meta = self._meta.get(upstream_skill)
        down_meta = self._meta.get(downstream_skill)

        if not up_meta or not down_meta:
            return {"compatible": False, "error": "One or both skills not found"}

        upstream_output = up_meta.output_schema
        if action in down_meta.actions:
            downstream_input = down_meta.actions[action].input_schema
        else:
            downstream_input = down_meta.input_schema

        compatible = down_meta.compatible_with(upstream_output)

        return {
            "compatible": compatible,
            "upstream": upstream_skill,
            "downstream": downstream_skill,
            "action": action,
            "upstream_output_schema": upstream_output,
            "downstream_input_schema": downstream_input,
        }
