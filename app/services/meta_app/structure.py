from __future__ import annotations

from app.models.meta_app import MetaAppScopeRecord


class MetaAppStructureService:
    """Builds a minimal app-level structural working set compatible with AgentSystem flows."""

    def infer_initial_scopes(self, app_name: str, goal: str) -> list[MetaAppScopeRecord]:
        base = app_name.strip().lower().replace(" ", "-")
        return [
            MetaAppScopeRecord(
                scope_id=f"{base}-control",
                purpose=f"Primary app control scope for {app_name}.",
                owned_paths=[f"apps/{base}/control"],
            ),
            MetaAppScopeRecord(
                scope_id=f"{base}-workflow",
                purpose=f"Workflow and execution scope for {app_name}.",
                owned_paths=[f"apps/{base}/workflow"],
            ),
        ]
