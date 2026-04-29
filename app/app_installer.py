from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.app_instance import AppInstance
from app.models.registry import AppInstallResult
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_registry import AppRegistryService
from app.services.config_center import ConfigCenterService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.app_config_service import AppConfigService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.blueprint_validation import BlueprintValidationError, BlueprintValidationService
from app.services.asset_center import AssetCenter
from app.services.system_catalog import CatalogEntry, SystemCatalog
from app.services.skill_control import SkillControlService


class AppInstallerError(ValueError):
    pass


DEFAULT_SYSTEM_SKILLS = [
    "system.app_config",
    "system.context",
    "system.state",
    "system.audit",
]


def _skill_id_to_asset_dependency(skill_id: str) -> str:
    return skill_id if skill_id.startswith("skill.") else f"skill.{skill_id}"


def _skill_asset_slug(skill_id: str) -> str:
    return skill_id.replace('.', '_')


def _skill_asset_manifest_path(base_dir: Path, skill_id: str) -> Path:
    return base_dir / "skill_assets" / "core" / "executable" / _skill_asset_slug(skill_id) / "manifest.json"


def _app_blueprint_to_asset_id(blueprint_id: str) -> str:
    return f"app.{blueprint_id.replace('bp.', '').replace(':', '.')}"


class AppInstallerService:
    def __init__(
        self,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
        runtime_host: AppRuntimeHostService,
        data_store: AppDataStore,
        context_store: AppContextStore | None = None,
        app_config_service: AppConfigService | None = None,
        app_profile_resolver: AppProfileResolverService | None = None,
        blueprint_validation: BlueprintValidationService | None = None,
        config_center: ConfigCenterService | None = None,
        asset_center: AssetCenter | None = None,
        runtime_center: Any = None,
        system_catalog: SystemCatalog | None = None,
        skill_control: SkillControlService | None = None,
        skill_asset_base_dir: str | None = None,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._data_store = data_store
        self._context_store = context_store
        self._app_config_service = app_config_service
        self._app_profile_resolver = app_profile_resolver
        self._blueprint_validation = blueprint_validation
        self._config_center = config_center
        self._asset_center = asset_center
        self._runtime_center = runtime_center
        self._system_catalog = system_catalog
        self._skill_control = skill_control
        store_base = getattr(getattr(data_store, "_store", None), "base_path", None)
        self._skill_asset_base_dir = Path(skill_asset_base_dir) if skill_asset_base_dir is not None else (Path(store_base).parent if store_base is not None else None)

    def install_app(self, blueprint_id: str, user_id: str, app_instance_id: str | None = None) -> AppInstallResult:
        blueprint = self._registry.get_blueprint(blueprint_id)
        if self._blueprint_validation is not None:
            try:
                self._blueprint_validation.require_valid(blueprint)
            except BlueprintValidationError as error:
                raise AppInstallerError(str(error)) from error

        installed_version = self._ensure_asset_installed(blueprint)
        self._register_static_catalog_entry(blueprint, user_id, installed_version)
        instance_id = app_instance_id or f"{blueprint_id}:{user_id}"

        try:
            instance = self._lifecycle.get_instance(instance_id)
            install_status = "upgraded"
        except Exception:
            resolved_skills = list(dict.fromkeys([*DEFAULT_SYSTEM_SKILLS, *blueprint.required_skills]))
            runtime_profile = self._app_profile_resolver.resolve(resolved_skills) if self._app_profile_resolver is not None else None
            instance = AppInstance(
                id=instance_id,
                blueprint_id=blueprint.id,
                owner_user_id=user_id,
                status="draft",
                installed_version=installed_version,
                data_namespace=f"users/{user_id}/apps/{instance_id}",
                execution_mode=blueprint.runtime_policy.execution_mode,
                runtime_policy=blueprint.runtime_policy,
                system_skills=list(DEFAULT_SYSTEM_SKILLS),
                resolved_skills=resolved_skills,
                runtime_profile=runtime_profile.model_dump() if runtime_profile is not None else {},
            )
            # Phase II.1: Materialize per-app skill instance isolation snapshot
            if self._config_center is not None:
                instance.skill_instances = self._config_center.materialize_app_skill_instances(
                    instance_id, resolved_skills,
                )
            self._runtime_host.register_instance(instance)
            install_status = "installed"

        if instance.status == "draft":
            self._lifecycle.transition(instance.id, "validate", reason="installer")
            self._lifecycle.transition(instance.id, "compile", reason="installer")
            self._lifecycle.transition(instance.id, "install", reason="installer")

        self._data_store.ensure_app_namespaces(instance.id, instance.owner_user_id)
        if self._app_config_service is not None:
            self._app_config_service.ensure_initialized(
                instance.id,
                defaults={
                    "app": {"id": instance.id, "blueprint_id": blueprint.id},
                    "runtime": {
                        "execution_mode": instance.execution_mode,
                        "runtime_profile": instance.runtime_profile.model_dump(mode="json"),
                    },
                },
            )
        if self._context_store is not None:
            context = self._context_store.ensure_context(instance.id)
            context.current_stage = self._lifecycle.get_instance(instance.id).status
            if install_status == "installed" and not context.current_goal:
                context.current_goal = blueprint.goal
            self._context_store.update_context(
                instance.id,
                current_goal=context.current_goal,
                current_stage=context.current_stage,
                status="active",
            )

        return AppInstallResult(
            app_instance_id=instance.id,
            blueprint_id=blueprint.id,
            install_status=install_status,
            execution_mode=instance.execution_mode,
            status=self._lifecycle.get_instance(instance.id).status,
            release_version=instance.installed_version,
            app_shape=blueprint.app_shape,
            runtime_profile=instance.runtime_profile,
        )


    def _register_static_catalog_entry(self, blueprint, user_id: str, release_version: str) -> None:
        if self._system_catalog is None:
            return
        asset_id = _app_blueprint_to_asset_id(blueprint.id)
        owner_id = f"user.{user_id}" if user_id != "system" else "system"
        entry = CatalogEntry(
            asset_id=asset_id,
            asset_type="app",
            owner_id=owner_id,
            name=blueprint.name,
            description=blueprint.goal,
            status="active",
            visibility="public" if user_id == "system" else "private",
            metadata={
                "blueprint_id": blueprint.id,
                "app_shape": blueprint.app_shape,
                "required_modules": list(blueprint.required_modules),
                "required_skills": list(blueprint.required_skills),
                "release_version": release_version,
            },
        )
        self._system_catalog.register(entry)

    def upgrade_app(self, app_instance_id: str, new_blueprint_id: str, user_id: str) -> dict:
        """Upgrade an app instance through AssetCenter -> RuntimeCenter chain."""
        try:
            instance = self._lifecycle.get_instance(app_instance_id)
            old_version = instance.installed_version
            old_asset_id = _app_blueprint_to_asset_id(instance.blueprint_id)
        except Exception:
            return {"status": "error", "message": f"App instance not found: {app_instance_id}"}

        # Route through AssetCenter for the new blueprint
        result = self.install_app(new_blueprint_id, user_id, app_instance_id)
        new_asset_id = _app_blueprint_to_asset_id(new_blueprint_id)

        # Sync RuntimeCenter version change
        if self._asset_center and self._runtime_host:
            runtime_center = getattr(self, '_runtime_center', None)
            if runtime_center:
                entry = runtime_center.get(app_instance_id)
                if entry:
                    runtime_center.register(
                        asset_id=app_instance_id,
                        version=result.release_version,
                        pid=entry.pid,
                        endpoint=entry.endpoint,
                        owner=entry.owner,
                    )

        if self._asset_center and old_asset_id != new_asset_id:
            try:
                self._asset_center.uninstall(old_asset_id)
            except FileNotFoundError:
                pass

        return {
            "status": "success",
            "app_instance_id": app_instance_id,
            "from_version": old_version,
            "to_version": result.release_version,
            "from_asset_id": old_asset_id,
            "to_asset_id": new_asset_id,
        }

    def uninstall_app_full(self, app_instance_id: str) -> dict:
        """Full uninstall: AssetCenter + RuntimeCenter + lifecycle + registry."""
        try:
            instance = self._lifecycle.get_instance(app_instance_id)
            asset_id = _app_blueprint_to_asset_id(instance.blueprint_id)
        except Exception:
            asset_id = f"app.{app_instance_id}"

        # 1. Stop runtime
        if self._runtime_host:
            try:
                self._runtime_host.unregister_instance(app_instance_id)
            except Exception:
                pass

        # 2. Uninstall from AssetCenter
        if self._asset_center:
            try:
                self._asset_center.uninstall(asset_id)
            except FileNotFoundError:
                pass  # Already uninstalled or never installed via AssetCenter

        # 3. Sync RuntimeCenter
        runtime_center = getattr(self, '_runtime_center', None)
        if runtime_center:
            runtime_center.mark_stopped(app_instance_id)
            runtime_center.unregister(app_instance_id)

        # 4. Remove adjacent persisted state
        if self._system_catalog is not None:
            self._system_catalog.unregister(asset_id)
        if self._context_store is not None:
            self._context_store.delete_context(app_instance_id)
        if self._app_config_service is not None:
            self._app_config_service.delete_app_config(app_instance_id)
        self._data_store.delete_app_namespaces(app_instance_id)

        # 5. Remove from lifecycle
        try:
            self._lifecycle.delete_app(app_instance_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        return {"status": "success", "app_instance_id": app_instance_id, "asset_id": asset_id}

    def _materialize_skill_asset_source_from_core(self, *, skill_id: str, asset_id: str, source_dir: Path) -> bool:
        if self._skill_asset_base_dir is None:
            return False
        manifest_path = _skill_asset_manifest_path(self._skill_asset_base_dir, skill_id)
        if not manifest_path.exists():
            return False
        core_dir = manifest_path.parent
        source_dir.mkdir(parents=True, exist_ok=True)
        skill_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = {
            "asset_id": asset_id,
            "asset_type": "skill",
            "name": skill_manifest.get("name", skill_id),
            "version": skill_manifest.get("version", "0.1.0"),
            "entry": "main.py",
            "owner": "system",
            "owner_role": "admin",
            "dependencies": [],
            "source_path": f"source/{asset_id}",
            "description": skill_manifest.get("description", skill_id),
            "tags": list(skill_manifest.get("tags", [])),
            "metadata": {
                "skill_id": skill_id,
                "runtime_adapter": skill_manifest.get("runtime_adapter", "executable"),
                "source": "skill_assets_core",
            },
        }
        (source_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        for name in ["main.py", "input.schema.json", "output.schema.json", "error.schema.json", "README.md"]:
            path = core_dir / name
            if path.exists():
                (source_dir / name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        metadata_path = core_dir / "metadata.json"
        if metadata_path.exists():
            (source_dir / "skill-asset-metadata.json").write_text(metadata_path.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    def _ensure_skill_asset_sources(self, skill_ids: list[str]) -> None:
        if self._asset_center is None or self._skill_control is None:
            return
        for skill_id in skill_ids:
            asset_id = _skill_id_to_asset_dependency(skill_id)
            if self._asset_center.get_asset(asset_id) is not None:
                continue
            source_dir = self._asset_center._source_dir / asset_id  # noqa: SLF001
            if self._materialize_skill_asset_source_from_core(skill_id=skill_id, asset_id=asset_id, source_dir=source_dir):
                continue
            try:
                entry = self._skill_control.get_skill(skill_id)
            except Exception:
                continue
            source_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "asset_id": asset_id,
                "asset_type": "skill",
                "name": entry.name,
                "version": entry.active_version or "0.1.0",
                "entry": "skill.json",
                "owner": "system",
                "owner_role": "admin",
                "dependencies": [],
                "source_path": f"source/{asset_id}",
                "description": entry.manifest.description if entry.manifest is not None else entry.name,
                "metadata": {
                    "skill_id": entry.skill_id,
                    "runtime_adapter": entry.runtime_adapter,
                    "tags": [] if entry.manifest is None else list(entry.manifest.tags),
                    "source": "skill_control_registry",
                },
            }
            skill_payload = entry.model_dump(mode="json")
            (source_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            (source_dir / "skill.json").write_text(json.dumps(skill_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._asset_center.discover()

    def _ensure_asset_installed(self, blueprint) -> str:
        entry = self._registry.get_entry(blueprint.id)
        release_version = entry.version
        if self._asset_center is None:
            return release_version

        self._ensure_skill_asset_sources(list(blueprint.required_skills))

        asset_id = f"app.{blueprint.id.replace('bp.', '').replace(':', '.')}"
        source_dir = self._asset_center._source_dir / asset_id  # noqa: SLF001
        source_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "asset_id": asset_id,
            "asset_type": "app",
            "name": blueprint.name,
            "version": blueprint.version,
            "entry": "blueprint.json",
            "owner": "system",
            "owner_role": "admin",
            "dependencies": [_skill_id_to_asset_dependency(skill_id) for skill_id in blueprint.required_skills],
            "source_path": f"source/{asset_id}",
            "description": blueprint.goal,
            "metadata": {
                "blueprint_id": blueprint.id,
                "app_shape": blueprint.app_shape,
                "required_modules": list(blueprint.required_modules),
                "required_skills": list(blueprint.required_skills),
            },
        }
        (source_dir / "manifest.json").write_text(__import__("json").dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_dir / "blueprint.json").write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")

        self._asset_center.discover()
        try:
            build_record = self._asset_center.build(asset_id)
            release_version = self._asset_center.install(asset_id, build_hash=build_record.build_hash)
        except Exception as exc:
            raise AppInstallerError(f"AssetCenter install failed for {asset_id}: {exc}") from exc
        return release_version
