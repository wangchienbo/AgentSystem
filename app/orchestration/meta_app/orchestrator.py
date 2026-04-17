"""Orchestrator that bridges the LLM-powered meta-app design layer with deterministic assembly/execution."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.app_meta_app import AppCreationFromMetaAppRequest
from app.models.meta_app import AppControlSkillResult
from app.models.meta_app_skill import MetaAppSkillRequest
from app.models.skill_creation import (
    AppFromSkillsRequest,
    SkillCreationRequest,
    SkillSchemaDefinition,
)
from app.services.asset_center import AssetCenter
from app.services.meta_app.bootstrap import MetaAppBootstrapService
from app.services.skill_factory import SkillFactoryService, SkillFactoryError
from app.services.system_catalog import CatalogEntry, SystemCatalog


class MetaAppOrchestratorError(ValueError):
    pass


@dataclass
class AppCreationOrchestrationResult:
    """End-to-end result from meta-app design through blueprint generation."""
    app_name: str
    control_plan: AppControlSkillResult
    blueprint: AppBlueprint | None = None
    created_skill_ids: list[str] = field(default_factory=list)
    installed_app: AppInstance | None = None
    asset_id: str = ""
    build_hash: str = ""
    version: str = ""
    error: str = ""


class MetaAppCreationOrchestrator:
    """Orchestrates app creation through the meta-app LLM design layer.

    Flow:
    1. Call meta_app_bootstrap (LLM) to design app control structure
    2. Create the suggested subordinate skills via skill_factory
    3. Build blueprint from the created skills
    4. Write blueprint to source/ (for asset management)
    5. Build + Install via AssetCenter (source/ → build/ → installed/)
    6. Create AppInstance and register with lifecycle + runtime_host
    7. Register with system_catalog
    """

    def __init__(
        self,
        *,
        meta_app_bootstrap: MetaAppBootstrapService,
        skill_factory: SkillFactoryService,
        lifecycle: Any = None,
        runtime_host: Any = None,
        app_registry: Any = None,
        asset_center: AssetCenter | None = None,
        system_catalog: SystemCatalog | None = None,
        source_dir: str = "source",
    ) -> None:
        self._meta_app = meta_app_bootstrap
        self._skill_factory = skill_factory
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._app_registry = app_registry
        self._asset_center = asset_center
        self._system_catalog = system_catalog
        self._source_dir = Path(source_dir)

    def create_app_through_meta_app(
        self,
        request: AppCreationFromMetaAppRequest,
    ) -> AppCreationOrchestrationResult:
        """Full flow: LLM design → skill creation → blueprint assembly → source/ → build → install → register."""

        # Step 1: LLM design layer — produce app control plan
        meta_request = MetaAppSkillRequest(
            app_name=request.app_name,
            goal=request.goal,
            app_kind=request.app_kind,
            complexity=request.complexity,
            scope=request.scope,
            context={"user_description": request.context} if request.context else {},
        )
        control_plan = self._meta_app.bootstrap(meta_request)

        # Step 2: Create subordinate skills from the LLM plan
        created_skill_ids = self._create_subordinate_skills(
            control_plan, request.app_name, request.goal,
        )

        # Step 3: Build blueprint from created skills
        blueprint: AppBlueprint | None = None
        asset_id: str = ""
        build_hash: str = ""
        try:
            if created_skill_ids:
                blueprint_id = f"bp-{control_plan.app_slug}"
                asset_id = f"app.{control_plan.app_slug}"
                bp_request = AppFromSkillsRequest(
                    blueprint_id=blueprint_id,
                    name=request.app_name,
                    goal=request.goal,
                    skill_ids=created_skill_ids,
                    step_inputs=request.workflow_inputs,
                )
                blueprint, _app_result = self._skill_factory.build_blueprint_from_skills(bp_request)
        except (SkillFactoryError, ValueError) as exc:
            return AppCreationOrchestrationResult(
                app_name=request.app_name,
                control_plan=control_plan,
                created_skill_ids=created_skill_ids,
                error=f"Blueprint assembly failed: {exc}",
            )

        # Step 4: Write blueprint to source/ (source path = asset management entry)
        if blueprint and self._asset_center:
            try:
                self._write_to_source(blueprint, asset_id)
            except Exception:
                # Non-fatal: continue even if source write fails
                pass

        # Step 5: Build + Install via AssetCenter (if available)
        if blueprint and self._asset_center:
            try:
                self._asset_center.discover()  # refresh registry
                build_record = self._asset_center.build(asset_id)
                build_hash = build_record.build_hash
                self._asset_center.install(asset_id, build_hash=build_hash)
            except Exception:
                # Non-fatal: instance still created, but asset not packaged
                pass

        # Step 6: Create AppInstance and register with lifecycle + runtime_host
        installed_app: AppInstance | None = None
        if blueprint and self._lifecycle:
            try:
                instance_id = control_plan.app_slug or request.app_name
                instance = AppInstance(
                    id=instance_id,
                    blueprint_id=blueprint.id,
                    owner_user_id=request.user_id or "system",
                    status="installed",
                    data_namespace=f"app_{instance_id}",
                    execution_mode="service" if request.app_kind == "service" else "pipeline",
                    system_skills=created_skill_ids,
                    resolved_skills=created_skill_ids,
                )
                self._lifecycle.register_instance(instance)
                if self._runtime_host:
                    self._runtime_host.register_instance(instance)
                if self._app_registry:
                    self._app_registry.register_blueprint(blueprint, description=f"Auto-created: {request.app_name}")
                installed_app = instance
            except Exception as exc:
                return AppCreationOrchestrationResult(
                    app_name=request.app_name,
                    control_plan=control_plan,
                    blueprint=blueprint,
                    created_skill_ids=created_skill_ids,
                    asset_id=asset_id,
                    build_hash=build_hash,
                    version=blueprint.version,
                    error=f"Instance registration failed: {exc}",
                )

        # Step 7: Register in system_catalog (if available)
        if blueprint and self._system_catalog:
            try:
                entry = CatalogEntry(
                    asset_id=asset_id,
                    name=request.app_name,
                    asset_type="app",
                    version=blueprint.version,
                    owner=request.user_id or "system",
                    status="active",
                    source_path=f"source/{asset_id}/",
                    metadata={
                        "blueprint_id": blueprint.id,
                        "skill_ids": created_skill_ids,
                        "app_slug": control_plan.app_slug,
                        "build_hash": build_hash,
                    },
                )
                self._system_catalog.register(entry)
            except Exception:
                pass  # Non-fatal

        return AppCreationOrchestrationResult(
            app_name=request.app_name,
            control_plan=control_plan,
            blueprint=blueprint,
            created_skill_ids=created_skill_ids,
            installed_app=installed_app,
            asset_id=asset_id,
            build_hash=build_hash,
            version=blueprint.version if blueprint else "",
        )

    def _create_subordinate_skills(
        self,
        control_plan: AppControlSkillResult,
        app_name: str,
        app_goal: str,
    ) -> list[str]:
        """Create skill stubs for each suggested subordinate in the control plan."""
        created: list[str] = []
        for suggestion in control_plan.subordinate_suggestions:
            skill_id = suggestion.suggested_name
            # Skip if already exists
            try:
                self._skill_factory._skill_control.get_skill(skill_id)
                created.append(skill_id)
                continue
            except Exception:
                pass

            # Generate stub handler code
            handler_code = self._generate_skill_stub_code(
                skill_id=skill_id,
                name=suggestion.responsibility,
                scope=suggestion.scope,
                app_name=app_name,
                app_goal=app_goal,
            )

            # Write handler to disk
            skills_dir = f"skills/generated/{skill_id}"
            os.makedirs(skills_dir, exist_ok=True)
            handler_path = f"{skills_dir}/handler.py"
            with open(handler_path, "w") as f:
                f.write(handler_code)

            # Create the skill in the registry
            creation_request = SkillCreationRequest(
                skill_id=skill_id,
                name=suggestion.responsibility,
                description=f"Subordinate skill for {app_name}: {suggestion.responsibility}",
                adapter_kind="script",
                handler_entry=handler_path,
                command=["python", handler_path],
                tags=[control_plan.app_slug, suggestion.priority, "generated-by-meta-app"],
                schemas=SkillSchemaDefinition(
                    input={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                    output={"type": "object", "properties": {"result": {"type": "string"}, "skill_id": {"type": "string"}}},
                    error={"type": "object", "properties": {"message": {"type": "string"}}},
                ),
            )
            self._skill_factory.create_skill(creation_request)
            created.append(skill_id)

        return created

    def _write_to_source(self, blueprint: AppBlueprint, asset_id: str) -> None:
        """Serialize blueprint to source/{asset_id}/ for asset management."""
        source_path = self._source_dir / asset_id
        source_path.mkdir(parents=True, exist_ok=True)

        manifest = {
            "asset_id": asset_id,
            "asset_type": "app",
            "name": blueprint.name,
            "version": blueprint.version,
            "entry": "blueprint.json",
            "owner": "system",
            "owner_role": "admin",
            "source_path": f"source/{asset_id}",
            "description": blueprint.goal,
            "dependencies": [],
            "tags": ["generated-by-meta-app"],
            "metadata": {
                "blueprint_id": blueprint.id,
                "app_shape": blueprint.app_shape,
                "required_skills": blueprint.required_skills,
                "required_modules": blueprint.required_modules,
            },
        }
        (source_path / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Also write the full blueprint for fidelity during build
        (source_path / "blueprint.json").write_text(
            blueprint.model_dump_json(indent=2), encoding="utf-8"
        )

    @staticmethod
    def _generate_skill_stub_code(
        skill_id: str,
        name: str,
        scope: str,
        app_name: str,
        app_goal: str,
    ) -> str:
        """Generate a minimal Python handler for a subordinate skill stub."""
        return (
            f'"""Auto-generated skill stub: {skill_id}\n'
            f"App: {app_name} | Goal: {app_goal}\n"
            f"Purpose: {name}\n"
            f"Scope: {scope}\n"
            'This is a placeholder — refine the handler for production use.\n'
            '"""\n\n'
            f"def handle(request: dict) -> dict:\n"
            f'    text = request.get("text", "")\n'
            f'    return {{"skill_id": "{skill_id}", "result": f"Processed: {{text}}", "status": "stub"}}\n'
        )
