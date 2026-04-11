from __future__ import annotations

from app.models.meta_app import MetaAppScopeRecord


class MetaAppGovernanceService:
    """Produces lightweight governance notes for app-level control bootstrap."""

    def build_governance_notes(self, scopes: list[MetaAppScopeRecord]) -> list[str]:
        notes: list[str] = [
            "Meta-app bootstrap must stay compatible with current blueprint/install/runtime paths.",
            "App-level subordinate records should be generated before deeper app-level recursive decomposition.",
        ]
        for scope in scopes:
            notes.append(f"Scope {scope.scope_id} owns: {', '.join(scope.owned_paths) or 'n/a'}")
        return notes
