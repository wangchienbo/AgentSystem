"""Asset/Resource Query Tools — fixed tools for LLM to query visible assets and resources.

These tools are CODE-WRITTEN, not LLM-generated.
LLM calls these tools to understand what assets/resources are available before making decisions.

Two-layer query chain:
  Layer 1: Query assets (static definitions)
  Layer 2: Query resources (runtime instances)

Permission filtering is done by CODE, not by LLM.
"""
from __future__ import annotations

from typing import Any

from app.services.asset_center import AssetCenter
from app.services.resource_center import ResourceCenter
from app.services.asset_registry import AssetRegistry


class AssetResourceQueryTools:
    """Fixed query tools for LLM consumption.

    All visibility and permission filtering happens here in code.
    LLM only sees pre-filtered candidate sets.
    """

    def __init__(
        self,
        asset_center: AssetCenter | None = None,
        asset_registry: AssetRegistry | None = None,
        resource_center: ResourceCenter | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._asset_registry = asset_registry
        self._resource_center = resource_center

    def set_dependencies(
        self,
        asset_center: AssetCenter,
        asset_registry: AssetRegistry,
        resource_center: ResourceCenter,
    ) -> None:
        self._asset_center = asset_center
        self._asset_registry = asset_registry
        self._resource_center = resource_center

    # ---- Layer 1: Asset Queries ----

    def query_visible_assets(
        self,
        caller_id: str,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query assets visible to the caller.

        Returns L1 overview (asset_id, type, name, description, static entry points).
        This is the FIRST thing LLM sees — a candidate set of what's available.
        """
        if not self._asset_center:
            return []

        assets = self._asset_center.list_assets()
        result = []
        for asset in assets:
            result.append({
                "asset_id": asset.asset_id,
                "asset_type": asset.asset_type,
                "name": asset.name,
                "description": asset.description,
                "version": asset.version,
                "tags": asset.tags,
                # L1 only — detail available via query_asset_detail
            })
        return result

    def query_asset_detail(self, asset_id: str) -> dict[str, Any] | None:
        """Get L2 detailed information for a specific asset.

        Returns full manifest, input/output schema, dependencies, call instructions.
        LLM calls this AFTER identifying a candidate asset from query_visible_assets.
        """
        if not self._asset_center:
            return None

        asset = self._asset_center.get_asset(asset_id)
        if not asset:
            return None

        return {
            "asset_id": asset.asset_id,
            "asset_type": asset.asset_type,
            "name": asset.name,
            "description": asset.description,
            "version": asset.version,
            "manifest": asset.manifest,
            "dependencies": asset.dependencies,
            "tags": asset.tags,
            "metadata": asset.metadata,
            "installed_version": self._asset_center.get_installed_version(asset_id),
        }

    # ---- Layer 2: Resource Queries ----

    def query_runtime_resources(
        self,
        caller_id: str,
        asset_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query runtime resources visible to the caller.

        Returns current running instances with their configuration and state.
        This is the SECOND layer — tells LLM HOW to actually invoke right now.
        """
        if not self._resource_center:
            return []

        return self._resource_center.get_runtime_context_for_llm(
            owner_id=caller_id,
            asset_ids=[asset_id] if asset_id else None,
        )

    def query_resource_detail(self, resource_id: str) -> dict[str, Any] | None:
        """Get full detail of a specific runtime resource."""
        if not self._resource_center:
            return None

        instance = self._resource_center.get_instance(resource_id)
        if not instance:
            return None

        return {
            "resource_id": instance.resource_id,
            "asset_id": instance.asset_id,
            "status": instance.status,
            "config": instance.config,
            "state": instance.state,
            "runtime_description": instance.runtime_description,
            "created_at": instance.created_at,
            "updated_at": instance.updated_at,
        }

    # ---- Combined Query (for single LLM call) ----

    def query_candidates(
        self,
        caller_id: str,
        user_id: str | None = None,
        include_asset_detail: bool = False,
        include_resources: bool = True,
    ) -> dict[str, Any]:
        """Combined query: assets + resources in one call.

        This is the PRIMARY entry point for LLM tool call chains.
        Returns everything the LLM needs in one shot (principle: fewer calls, more complete info).

        Args:
            caller_id: Who is querying
            user_id: Associated user ID
            include_asset_detail: Whether to include L2 asset details (increases token usage)
            include_resources: Whether to include runtime resource context

        Returns:
            {
                "assets": [L1 overview, ...],
                "resources": [runtime context, ...],  # if include_resources
                "detail": {asset_id: L2 detail, ...},  # if include_asset_detail
            }
        """
        result: dict[str, Any] = {}

        # Layer 1: Assets
        result["assets"] = self.query_visible_assets(caller_id, user_id)

        # Optional: L2 asset details
        if include_asset_detail:
            result["detail"] = {}
            for asset in result["assets"]:
                detail = self.query_asset_detail(asset["asset_id"])
                if detail:
                    result["detail"][asset["asset_id"]] = detail

        # Layer 2: Resources
        if include_resources:
            result["resources"] = self.query_runtime_resources(caller_id)

        return result
