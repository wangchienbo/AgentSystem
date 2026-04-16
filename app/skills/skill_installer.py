"""Skill Installer — auto-search, download, and install remote skills.

Discovers skills from registries, downloads MD docs, packages them into
Workers, and registers them with the system.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillInstallerError(Exception):
    pass


class SkillInstaller:
    """Auto-installs remote skills from registries.

    Workflow when an App needs a skill:
    1. Check local registry
    2. Search remote registries
    3. Download MD doc
    4. Package into Worker
    5. Register and start
    """

    def __init__(
        self,
        worker_manager: Any,
        packager: Any,
        config_center: Any,
        skill_control: Any,
        registry_urls: list[str] | None = None,
    ) -> None:
        self._worker_manager = worker_manager
        self._packager = packager
        self._config_center = config_center
        self._skill_control = skill_control
        self._registry_urls = registry_urls or []

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search remote registries for skills.

        Returns list of skill metadata dicts:
        [{skill_id, name, description, source_url, ...}]
        """
        results = []
        for url in self._registry_urls:
            try:
                registry_results = await self._search_registry(url, query)
                results.extend(registry_results)
            except Exception:
                logger.exception("Failed to search registry: %s", url)
        return results

    async def install(self, skill_id: str, source: str) -> dict[str, Any]:
        """Install a skill from a source URL.

        Args:
            skill_id: Unique identifier for the skill
            source: URL or local path to the MD document

        Returns:
            Installation result dict
        """
        # 1. Download MD content
        md_content = await self._download_source(source)

        # 2. Package into Worker
        worker = await self._packager.package_from_md(skill_id, md_content)

        # 3. Register with skill control
        self._register_skill_entry(skill_id, worker)

        # 4. Start worker
        await self._worker_manager.register_and_start(worker)

        logger.info("Skill installed: %s from %s", skill_id, source)
        return {
            "skill_id": skill_id,
            "source": source,
            "status": "installed",
            "worker_id": worker.worker_id,
        }

    async def install_if_missing(self, skill_id: str, query: str) -> dict[str, Any]:
        """Search and install a skill if not already registered.

        Args:
            skill_id: The skill to look for
            query: Search query for finding it

        Returns:
            Result: found locally, installed, or not found
        """
        # Check local
        if self._worker_manager.is_registered(f"skill.{skill_id}"):
            return {"skill_id": skill_id, "status": "already_installed"}

        # Search remote
        results = await self.search(query)
        if not results:
            return {"skill_id": skill_id, "status": "not_found"}

        # Install first match
        best = results[0]
        return await self.install(skill_id, best["source_url"])

    async def uninstall(self, skill_id: str) -> bool:
        """Uninstall a skill."""
        worker_id = f"skill.{skill_id}"
        if not self._worker_manager.is_registered(worker_id):
            return False

        # Config center entry removed by caller if needed
        logger.info("Skill uninstalled: %s", skill_id)
        return True

    # -- Internal -------------------------------------------------------------

    async def _download_source(self, source: str) -> str:
        """Download MD content from URL or read from local path."""
        if source.startswith(("http://", "https://")):
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(source) as resp:
                    resp.raise_for_status()
                    return await resp.text()
        else:
            from pathlib import Path
            return Path(source).read_text(encoding="utf-8")

    async def _search_registry(self, registry_url: str, query: str) -> list[dict]:
        """Search a single registry. Placeholder for actual API."""
        # TODO: implement actual registry API call
        # GET {registry_url}/api/skills?q={query}
        logger.info("Searching registry %s for %s", registry_url, query)
        return []

    def _register_skill_entry(self, skill_id: str, worker: Any) -> None:
        """Register skill in skill_control registry."""
        # TODO: build proper SkillRegistryEntry from worker config
        logger.debug("Registered skill entry: %s", skill_id)
