from __future__ import annotations

from app.models.meta_app import MetaAppBootstrapRequest, MetaAppBootstrapResult
from app.models.meta_app_skill import MetaAppSkillRequest
from app.services.meta_app.governance import MetaAppGovernanceService
from app.services.meta_app.structure import MetaAppStructureService


class MetaAppBootstrapService:
    """Builds an app-scoped control bootstrap result without breaking current app generation/modification flows."""

    def __init__(self) -> None:
        self._structure = MetaAppStructureService()
        self._governance = MetaAppGovernanceService()

    def bootstrap(self, request: MetaAppBootstrapRequest | MetaAppSkillRequest) -> MetaAppBootstrapResult:
        scopes = self._structure.infer_initial_scopes(request.app_name, request.goal)
        notes = self._governance.build_governance_notes(scopes)
        app_slug = request.app_name.strip().lower().replace(" ", "-")
        return MetaAppBootstrapResult(
            app_name=request.app_name,
            anchor_name=f"{app_slug}-APP_CONTROL.md",
            project_map_name=f"{app_slug}-project-map.yaml",
            module_records=scopes,
            subordinate_registry_name=f"{app_slug}-subordinate-registry.yaml",
            notes=notes,
        )
