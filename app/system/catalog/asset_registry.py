"""Dynamic Asset Registry — runtime-only asset management.

Two-layer storage:
  - system_assets: dict[asset_id, Asset]  (system-level view)
  - user_assets:   dict[user_id, dict[asset_id, Asset]]  (per-user view)

Only *running* instances are registered.  Static blueprints are excluded.

Visibility rules:
  - system  → all user assets + public assets
  - user.*  → own assets + public assets (+ shared assets)
  - app.*   → bound running skills + public assets
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.models.asset import Asset, AssetType, Visibility

logger = logging.getLogger(__name__)


class AssetRegistry:
    """Thread-safe dynamic asset registry with two-layer storage."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # Layer 1: system-level assets (system tools, infrastructure)
        self._system_assets: dict[str, Asset] = {}

        # Layer 2: user-level assets  {owner_id: {asset_id: Asset}}
        self._user_assets: dict[str, dict[str, Asset]] = {}

    # ------------------------------------------------------------------
    # Registration / Unregistration
    # ------------------------------------------------------------------

    def register(self, asset: Asset) -> None:
        """Register a running asset into the appropriate layer."""
        with self._lock:
            if not asset.is_running:
                logger.warning("Refusing to register non-running asset: %s", asset.asset_id)
                return

            if asset.owner_id == "system" or asset.visibility == Visibility.PUBLIC:
                self._system_assets[asset.asset_id] = asset
                logger.info("Registered system/public asset: %s", asset.asset_id)
            else:
                owner_table = self._user_assets.setdefault(asset.owner_id, {})
                owner_table[asset.asset_id] = asset
                logger.info("Registered asset %s under owner %s", asset.asset_id, asset.owner_id)

    def unregister(self, asset_id: str, owner_id: str) -> None:
        """Remove an asset when its instance stops.

        If the stopped asset is an APP, cascade-unregister all skills it owns.
        """
        with self._lock:
            if owner_id == "system":
                self._system_assets.pop(asset_id, None)
            else:
                owner_table = self._user_assets.get(owner_id)
                if owner_table:
                    owner_table.pop(asset_id, None)
                    if not owner_table:
                        del self._user_assets[owner_id]

            # Cascade: if this was an App, unregister all assets it owns
            if asset_id in self._user_assets:
                del self._user_assets[asset_id]

            logger.info("Unregistered asset: %s (owner=%s)", asset_id, owner_id)

    # ------------------------------------------------------------------
    # Visibility query
    # ------------------------------------------------------------------

    def get_visible_assets(self, caller_name: str) -> list[Asset]:
        """Return assets visible to the given caller.

        Args:
            caller_name: "system", "user.<id>", or "app.<id>"
        """
        with self._lock:
            if caller_name == "system":
                return self._get_system_view()
            elif caller_name.startswith("user."):
                return self._get_user_view(caller_name)
            elif caller_name.startswith("app."):
                return self._get_app_view(caller_name)
            else:
                logger.warning("Unknown caller prefix: %s", caller_name)
                return []

    def _get_system_view(self) -> list[Asset]:
        """System sees all user assets + public assets."""
        result: list[Asset] = list(self._system_assets.values())
        for owner_table in self._user_assets.values():
            for asset in owner_table.values():
                if asset.asset_id not in {a.asset_id for a in result}:
                    result.append(asset)
        return result

    def _get_user_view(self, user_id: str) -> list[Asset]:
        """User sees own assets + public assets (+ shared assets)."""
        result: list[Asset] = []
        seen: set[str] = set()

        # Public assets from system layer
        for asset in self._system_assets.values():
            if asset.visibility == Visibility.PUBLIC:
                result.append(asset)
                seen.add(asset.asset_id)

        # Own assets
        own_table = self._user_assets.get(user_id, {})
        for asset in own_table.values():
            if asset.asset_id not in seen:
                result.append(asset)
                seen.add(asset.asset_id)

        # Shared assets (other users shared with this user)
        for owner_id, owner_table in self._user_assets.items():
            if owner_id == user_id:
                continue
            for asset in owner_table.values():
                if asset.visibility == Visibility.USER_SHARED and user_id in asset.shared_with:
                    if asset.asset_id not in seen:
                        result.append(asset)
                        seen.add(asset.asset_id)

        return result

    def _get_app_view(self, app_id: str) -> list[Asset]:
        """App sees its own bound running skills + public assets."""
        result: list[Asset] = []
        seen: set[str] = set()

        # Public assets
        for asset in self._system_assets.values():
            if asset.visibility == Visibility.PUBLIC:
                result.append(asset)
                seen.add(asset.asset_id)

        # App's own assets (skills bound to it)
        app_table = self._user_assets.get(app_id, {})
        for asset in app_table.values():
            if asset.asset_id not in seen:
                result.append(asset)
                seen.add(asset.asset_id)

        return result

    # ------------------------------------------------------------------
    # Detail lookup
    # ------------------------------------------------------------------

    def get_asset_detail(self, asset_id: str, caller_name: str) -> Asset | None:
        """Get full asset detail if visible to caller."""
        visible = self.get_visible_assets(caller_name)
        for a in visible:
            if a.asset_id == asset_id:
                return a
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ensure_owner_table(self, owner_id: str) -> None:
        """Ensure an owner table exists (create if missing)."""
        with self._lock:
            if owner_id != "system":
                self._user_assets.setdefault(owner_id, {})

    def list_owners(self) -> list[str]:
        """List all owner IDs that have registered assets."""
        with self._lock:
            owners = set()
            owners.add("system")
            owners.update(self._user_assets.keys())
            return sorted(owners)

    def asset_count(self) -> dict[str, int]:
        """Return counts of registered assets."""
        with self._lock:
            user_total = sum(len(t) for t in self._user_assets.values())
            return {
                "system": len(self._system_assets),
                "user_total": user_total,
                "owners": len(self._user_assets),
                "total": len(self._system_assets) + user_total,
            }
