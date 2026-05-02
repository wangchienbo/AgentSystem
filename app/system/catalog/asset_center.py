"""Asset Center — manages static, installable asset definitions.

An Asset is a versioned, installable definition (skill template, app blueprint).
This is the DEVELOPMENT-TIME layer: definitions live in `source/`, are built,
and then installed into the runtime layer.

Key principle: modifying source/ does NOT affect running instances.
Only `build + install` promotes changes to the running system.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.system.invocation.invocation_compliance import InvocationComplianceValidator

logger = logging.getLogger(__name__)


@dataclass
class AssetDefinition:
    """Static, versioned asset definition."""
    asset_id: str
    name: str
    asset_type: str  # "skill" | "app" | "path"
    version: str
    source_path: str  # relative path in source/
    description: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute a deterministic hash of the asset definition."""
        content = json.dumps({
            "asset_id": self.asset_id,
            "version": self.version,
            "source_path": self.source_path,
            "manifest": self.manifest,
            "dependencies": sorted(self.dependencies),
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass
class AssetBuildRecord:
    """Record of a successful asset build."""
    asset_id: str
    version: str
    build_hash: str
    build_time: str  # ISO timestamp
    source_hash: str  # hash of source files at build time
    status: str = "success"  # "success" | "failed"


class AssetCenter:
    """Manages the full lifecycle of static asset definitions.

    Responsibilities:
    - Discover assets in source/ directories
    - Build assets (validate, package, compute hashes)
    - Install assets to installed/ (runtime layer)
    - Track build history and version lineage
    - Support rollback to previous versions
    """

    REQUIRED_MANIFEST_FIELDS = {
        "asset_id",
        "asset_type",
        "name",
        "version",
        "entry",
        "owner",
        "owner_role",
        "dependencies",
        "source_path",
        "description",
        "metadata",
    }
    _invocation_compliance = InvocationComplianceValidator()

    def __init__(
        self,
        source_dir: str = "source",
        installed_dir: str = "installed",
        build_dir: str = "build",
        data_dir: str = "data",
    ) -> None:
        self._source_dir = Path(source_dir)
        self._installed_dir = Path(installed_dir)
        self._build_dir = Path(build_dir)
        self._data_dir = Path(data_dir)
        self._registry: dict[str, AssetDefinition] = {}
        self._build_history: dict[str, list[AssetBuildRecord]] = {}
        self._load_registry()

    # ---- Discovery ----

    def discover(self) -> list[AssetDefinition]:
        """Scan source/ directories and discover all asset definitions."""
        assets = []
        if not self._source_dir.exists():
            return assets

        for asset_dir in self._source_dir.iterdir():
            if not asset_dir.is_dir():
                continue
            manifest_path = asset_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self._validate_manifest(manifest=manifest, asset_dir=asset_dir)
                asset = AssetDefinition(
                    asset_id=manifest["asset_id"],
                    name=manifest["name"],
                    asset_type=manifest["asset_type"],
                    version=manifest["version"],
                    source_path=str(asset_dir.relative_to(self._source_dir)),
                    description=manifest["description"],
                    manifest=manifest,
                    dependencies=manifest["dependencies"],
                    tags=manifest.get("tags", []),
                    metadata=manifest["metadata"],
                )
                assets.append(asset)
                self._registry[asset.asset_id] = asset
            except Exception as exc:
                logger.warning("Skip invalid asset manifest %s: %s", manifest_path, exc)
                continue

        return assets

    # ---- Build ----

    def build(self, asset_id: str) -> AssetBuildRecord:
        """Build an asset: validate and package it."""
        asset = self._registry.get(asset_id)
        if not asset:
            raise ValueError(f"Asset not found: {asset_id}")

        source_path = self._source_dir / asset.source_path
        if not source_path.exists():
            raise FileNotFoundError(f"Source path not found: {source_path}")

        # Compute source hash
        source_hash = self._compute_directory_hash(source_path)
        build_hash = asset.compute_hash()

        # Create build output
        build_output_dir = self._build_dir / asset_id / build_hash
        build_output_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            for item in source_path.iterdir():
                dest = build_output_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

        record = AssetBuildRecord(
            asset_id=asset_id,
            version=asset.version,
            build_hash=build_hash,
            build_time=self._now_iso(),
            source_hash=source_hash,
        )
        self._build_history.setdefault(asset_id, []).append(record)
        self._save_build_history()

        # N5-02: Resolve and copy dependencies into build output
        self._resolve_and_copy_dependencies(asset_id, record)

        return record

    # ---- Build-time dependency resolution ----

    def _resolve_and_copy_dependencies(self, asset_id: str, record: AssetBuildRecord) -> None:
        """N5-02: Resolve asset dependencies recursively and copy them to build output.

        Each dependency is copied into build_output/deps/{dep_id}/ so the
        installed asset has a self-contained copy of its dependencies.
        Version isolation (N5-03) is achieved because each build produces
        an independent build_output directory.
        """
        asset = self._registry.get(asset_id)
        if not asset:
            return

        build_output = self._build_dir / asset_id / record.build_hash
        deps_dir = build_output / "deps"

        visited: set[str] = set()
        self._copy_deps_recursive(asset_id, deps_dir, visited)

    def _copy_deps_recursive(self, asset_id: str, deps_dir: Path, visited: set[str]) -> None:
        """Recursively resolve and copy dependencies."""
        asset = self._registry.get(asset_id)
        if not asset:
            return

        for dep_id in asset.dependencies:
            if dep_id in visited:
                continue
            visited.add(dep_id)

            dep_asset = self._registry.get(dep_id)
            if not dep_asset:
                logger.warning("Dependency not found: %s (required by %s)", dep_id, asset_id)
                continue

            # Build the dependency if not already built
            try:
                dep_source = self._source_dir / dep_asset.source_path
                if dep_source.exists():
                    dep_dest = deps_dir / dep_id
                    if dep_source.is_dir():
                        if dep_dest.exists():
                            shutil.rmtree(dep_dest)
                        shutil.copytree(dep_source, dep_dest)
                    else:
                        deps_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dep_source, dep_dest)
                    logger.info("Resolved dependency: %s -> %s", dep_id, asset_id)
            except Exception as e:
                logger.error("Failed to resolve dependency %s: %s", dep_id, e)

    # ---- Install ----

    def install(self, asset_id: str, build_hash: str | None = None) -> str:
        """Install a built asset to the runtime layer (installed/).

        Returns the installed version string.
        """
        asset = self._registry.get(asset_id)
        if not asset:
            raise ValueError(f"Asset not found: {asset_id}")

        # Find the build to install
        history = self._build_history.get(asset_id, [])
        if build_hash:
            record = next((r for r in history if r.build_hash == build_hash), None)
        else:
            record = history[-1] if history else None

        if not record:
            raise ValueError(f"No build available for {asset_id}")

        # Copy to installed/
        installed_path = self._installed_dir / asset_id
        if installed_path.exists():
            shutil.rmtree(installed_path)
        build_output = self._build_dir / asset_id / record.build_hash
        shutil.copytree(build_output, installed_path)

        # Write installed manifest
        manifest = {**asset.manifest, "installed_version": asset.version, "build_hash": record.build_hash}
        (installed_path / "installed.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return asset.version

    # ---- Rollback ----

    def rollback(self, asset_id: str, target_version: str) -> str:
        """Rollback an installed asset to a previous version."""
        history = self._build_history.get(asset_id, [])
        record = next((r for r in history if r.version == target_version), None)
        if not record:
            raise ValueError(f"No build found for {asset_id} version {target_version}")

        return self.install(asset_id, record.build_hash)

    # ---- Queries ----

    def get_asset(self, asset_id: str) -> AssetDefinition | None:
        return self._registry.get(asset_id)

    def list_assets(self, asset_type: str | None = None) -> list[AssetDefinition]:
        assets = list(self._registry.values())
        if asset_type:
            assets = [a for a in assets if a.asset_type == asset_type]
        return assets

    def get_build_history(self, asset_id: str) -> list[AssetBuildRecord]:
        return self._build_history.get(asset_id, [])

    def get_installed_version(self, asset_id: str) -> str | None:
        installed_manifest = self._installed_dir / asset_id / "installed.json"
        if installed_manifest.exists():
            data = json.loads(installed_manifest.read_text(encoding="utf-8"))
            return data.get("installed_version")
        return None

    def list_installed(self, asset_type: str | None = None) -> list[dict[str, Any]]:
        """List all installed assets in installed/ directory."""
        if not self._installed_dir.exists():
            return []

        installed = []
        for item in self._installed_dir.iterdir():
            if not item.is_dir():
                continue
            manifest_path = item / "installed.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                asset_type_val = data.get("asset_type", "skill")
                if asset_type and asset_type_val != asset_type:
                    continue
                installed.append({
                    "asset_id": data.get("asset_id", item.name),
                    "name": data.get("name", item.name),
                    "asset_type": asset_type_val,
                    "installed_version": data.get("installed_version", "unknown"),
                    "build_hash": data.get("build_hash", ""),
                    "source_path": data.get("source_path", ""),
                    "description": data.get("description", ""),
                })
            except Exception:
                continue

        return installed

    def uninstall(self, asset_id: str) -> bool:
        """Uninstall an asset from the runtime layer (installed/).

        Note: This only removes the installed/ copy. source/ is untouched.
        """
        installed_path = self._installed_dir / asset_id
        if not installed_path.exists():
            raise FileNotFoundError(f"Asset not installed: {asset_id}")
        shutil.rmtree(installed_path)
        return True

    # ---- Persistence ----

    def _load_registry(self) -> None:
        registry_path = self._data_dir / "asset_registry.json"
        if registry_path.exists():
            try:
                data = json.loads(registry_path.read_text(encoding="utf-8"))
                for aid, raw in data.get("assets", {}).items():
                    self._registry[aid] = AssetDefinition(**raw)
                for aid, records in data.get("build_history", {}).items():
                    self._build_history[aid] = [
                        AssetBuildRecord(**r) for r in records
                    ]
            except Exception:
                pass

    def _save_build_history(self) -> None:
        self._save_registry()

    def _save_registry(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "assets": {
                aid: {
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "asset_type": a.asset_type,
                    "version": a.version,
                    "source_path": a.source_path,
                    "description": a.description,
                    "manifest": a.manifest,
                    "dependencies": a.dependencies,
                    "tags": a.tags,
                    "metadata": a.metadata,
                }
                for aid, a in self._registry.items()
            },
            "build_history": {
                aid: [
                    {
                        "asset_id": r.asset_id,
                        "version": r.version,
                        "build_hash": r.build_hash,
                        "build_time": r.build_time,
                        "source_hash": r.source_hash,
                        "status": r.status,
                    }
                    for r in records
                ]
                for aid, records in self._build_history.items()
            },
        }
        (self._data_dir / "asset_registry.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- Helpers ----

    @classmethod
    def _validate_manifest(cls, manifest: dict[str, Any], asset_dir: Path) -> None:
        missing = sorted(field for field in cls.REQUIRED_MANIFEST_FIELDS if field not in manifest)
        if missing:
            raise ValueError(f"missing required manifest fields: {', '.join(missing)}")

        if not isinstance(manifest["dependencies"], list):
            raise ValueError("dependencies must be a list")
        if not isinstance(manifest["metadata"], dict):
            raise ValueError("metadata must be an object")

        # Phase P: auto-inject compliance defaults for backward compatibility
        metadata = manifest["metadata"]
        metadata.setdefault("runtime_wrapper_compatibility", True)
        metadata.setdefault("session_binding_support", "supported")
        metadata.setdefault("invocation_contract_version", "phase-p-v1")
        metadata.setdefault("endpoint_requirement", "none")
        metadata.setdefault("tool_vllm_usage_mode", "local_session_only")

        expected_asset_id = asset_dir.name
        compliance = cls._invocation_compliance.validate_manifest(manifest)
        if not compliance.compliant:
            raise ValueError("invocation compliance validation failed: " + "; ".join(compliance.reasons))
        if manifest["asset_id"] != expected_asset_id:
            raise ValueError(
                f"asset_id must match source directory name: expected {expected_asset_id}, got {manifest['asset_id']}"
            )

        expected_source_path = f"source/{asset_dir.name}"
        if manifest["source_path"] != expected_source_path:
            raise ValueError(
                f"source_path must be {expected_source_path}, got {manifest['source_path']}"
            )

    @staticmethod
    def _compute_directory_hash(directory: Path) -> str:
        """Compute a hash of all files in a directory."""
        hasher = hashlib.sha256()
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                hasher.update(path.read_bytes())
        return hasher.hexdigest()[:16]

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
