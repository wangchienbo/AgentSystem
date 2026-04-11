from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.services.generated_skill_asset_store import GeneratedSkillAssetStore
from app.services.skill_control import SkillControlService


class ScriptSkillGenerationError(ValueError):
    """Raised when skill generation or smoke test fails."""
    pass


class ScriptSkillGenerator:
    def __init__(self, asset_store: GeneratedSkillAssetStore, skill_control: SkillControlService) -> None:
        self._asset_store = asset_store
        self._skill_control = skill_control

    @staticmethod
    def _auto_description(skill_id: str, name: str, template_type: str) -> str:
        """Generate a skill description when the user doesn't provide one.

        Derives a concise description from the skill_id, name, and template_type.
        """
        # Extract the last segment of the skill_id as a short identifier
        short_id = skill_id.rsplit(".", 1)[-1].replace("_", " ")
        return f"Auto-generated {template_type} skill '{name}' ({short_id})."

    def _enrich_request(self, request: GeneratedSkillRequest) -> GeneratedSkillRequest:
        """Enrich the request with auto-generated fields if missing."""
        if not request.description:
            description = self._auto_description(
                request.skill_id, request.name, request.template_type
            )
            return GeneratedSkillRequest(
                skill_id=request.skill_id,
                name=request.name,
                description=description,
                language=request.language,
                template_type=request.template_type,
            )
        return request

    def generate_and_register(
        self,
        request: GeneratedSkillRequest,
        *,
        run_smoke_test: bool = True,
    ) -> SkillRegistryEntry:
        """Generate, scaffold, validate, and register a skill.

        Args:
            request: The skill generation request.
            run_smoke_test: If True, execute the smoke test after scaffolding
                to verify the generated skill is functional.
        """
        # Auto-generate description if missing
        enriched = self._enrich_request(request)

        # Create scaffold assets (manifest, adapter, contract, entrypoint, schemas, smoke test)
        asset = self._asset_store.create_scaffold(enriched)
        manifest = json.loads(Path(asset.manifest_path).read_text())

        # Validate scaffold completeness
        self._validate_scaffold(asset)

        # Run smoke test to verify the generated skill is executable
        if run_smoke_test:
            self._run_smoke_test(asset)

        entry = SkillRegistryEntry(
            skill_id=enriched.skill_id,
            name=enriched.name,
            active_version="0.1.0",
            versions=[SkillVersion(version="0.1.0", content="generated")],
            runtime_adapter="executable",
            capability_profile=SkillCapabilityProfile(
                intelligence_level="L0_deterministic",
                network_requirement="N0_none",
                runtime_criticality="C2_required_runtime",
                execution_locality="local",
                invocation_default="automatic",
                risk_level="R1_local_write",
            ),
            manifest=SkillManifest(
                skill_id=manifest["skill_id"],
                name=manifest["name"],
                version=manifest["version"],
                description=manifest["description"],
                runtime_adapter=manifest["runtime_adapter"],
                adapter=SkillAdapterSpec(**manifest["adapter"]),
                contract=SkillContractRef(**manifest["contract"]),
                tags=manifest["tags"],
                risk=SkillManifestRisk(**manifest["risk"]),
            ),
            origin="generated",
        )
        self._skill_control.register(entry)
        return entry

    def _validate_scaffold(self, asset) -> None:
        """Verify all scaffold files exist and are well-formed."""
        required_files = [
            asset.manifest_path,
            asset.schema_path,
            asset.entrypoint_path,
            asset.readme_path,
            asset.input_schema_path,
            asset.output_schema_path,
            asset.error_schema_path,
        ]
        for path_str in required_files:
            p = Path(path_str)
            if not p.exists():
                raise ScriptSkillGenerationError(
                    f"Scaffold file missing: {p}"
                )
            if p.suffix == ".json":
                try:
                    json.loads(p.read_text())
                except json.JSONDecodeError as exc:
                    raise ScriptSkillGenerationError(
                        f"Invalid JSON in scaffold file: {p}: {exc}"
                    ) from exc

    def _run_smoke_test(self, asset) -> None:
        """Run the generated smoke test script to verify the skill works."""
        tests_dir = Path(asset.asset_dir) / "tests"
        smoke_test = tests_dir / "test_smoke.py"
        if not smoke_test.exists():
            raise ScriptSkillGenerationError(
                f"Smoke test not found: {smoke_test}"
            )

        result = subprocess.run(
            ["python3", str(smoke_test)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise ScriptSkillGenerationError(
                f"Smoke test failed for {asset.skill_id}:\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
