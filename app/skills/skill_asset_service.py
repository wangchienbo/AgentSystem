from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.skill_asset import SkillAssetConsistencyIssue, SkillAssetConsistencyResult, SkillAssetIndex, SkillAssetIndexEntry, SkillAssetMetadata
from app.models.generated_skill import GeneratedSkillAsset, GeneratedSkillRequest
from app.runtime_paths import resolve_runtime_paths

PHASE_P_INVOCATION_DEFAULTS = {
    "invocation_contract_version": "phase-p-v1",
    "runtime_wrapper_compatibility": True,
    "session_binding_support": "supported",
    "endpoint_requirement": "none",
    "tool_vllm_usage_mode": "local_session_only",
}


class SkillAssetService:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._assets_root = self._base_dir / "skill_assets"
        self._core_root = self._assets_root / "core"
        self._candidate_root = self._assets_root / "candidates"
        self._archived_root = self._assets_root / "archived"
        self._deprecated_root = self._assets_root / "deprecated"
        self._index_path = self._assets_root / "index.json"
        self._assets_root.mkdir(parents=True, exist_ok=True)
        self._write_index(self._load_index())

    def _resolve_index_path(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        if str(path).startswith("data/"):
            return resolve_runtime_paths().data_dir / path.relative_to("data")
        return self._base_dir / path

    def asset_slug(self, skill_id: str) -> str:
        return skill_id.replace('.', '_')

    def resolve_asset_dir(self, skill_id: str, *, adapter_kind: str = "executable", status: str = "candidate") -> Path:
        slug = self.asset_slug(skill_id)
        root = {
            "core": self._core_root,
            "candidate": self._candidate_root,
            "archived": self._archived_root,
            "deprecated": self._deprecated_root,
            "draft": self._candidate_root,
        }[status]
        return root / adapter_kind / slug

    def create_asset_scaffold(
        self,
        request: GeneratedSkillRequest,
        *,
        adapter_kind: str = "executable",
        status: str = "candidate",
        source_workflow: str | None = None,
        source_experience_id: str | None = None,
    ) -> tuple[GeneratedSkillAsset, SkillAssetMetadata]:
        asset_dir = self.resolve_asset_dir(request.skill_id, adapter_kind=adapter_kind, status=status)
        asset_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = asset_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        entrypoint_name = "main.py"
        entrypoint_path = asset_dir / entrypoint_name
        manifest_path = asset_dir / "manifest.json"
        input_schema_path = asset_dir / "input.schema.json"
        output_schema_path = asset_dir / "output.schema.json"
        error_schema_path = asset_dir / "error.schema.json"
        metadata_path = asset_dir / "metadata.json"
        readme_path = asset_dir / "README.md"
        smoke_test_path = tests_dir / "test_smoke.py"

        input_schema = self._build_input_schema(request.template_type)
        output_schema = self._build_output_schema(request.template_type)
        error_schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": True,
        }
        sample_input = self._sample_input(request.template_type)
        expected_field = self._expected_field(request.template_type)
        manifest = {
            "skill_id": request.skill_id,
            "name": request.name,
            "version": "0.1.0",
            "description": request.description,
            "runtime_adapter": adapter_kind,
            "adapter": {
                "kind": adapter_kind,
                "command": ["python3"],
                "entry": str(entrypoint_path),
                "invocation_protocol": "json_stdio",
                "timeout_seconds": 15,
            },
            "contract": {
                "input_schema_ref": str(input_schema_path),
                "output_schema_ref": str(output_schema_path),
                "error_schema_ref": str(error_schema_path),
            },
            "tags": ["generated", request.template_type, f"template:{request.template_type}", "source:local_generator"],
            "risk": {
                "risk_level": "R1_local_write",
                "allow_network": False,
                "allow_filesystem_write": True,
                "allow_shell": False,
            },
            "phase_p_invocation": dict(PHASE_P_INVOCATION_DEFAULTS),
        }
        metadata = SkillAssetMetadata(
            skill_id=request.skill_id,
            asset_slug=self.asset_slug(request.skill_id),
            asset_status=status,
            asset_origin="generated",
            runtime_adapter=adapter_kind,
            version="0.1.0",
            content_maturity="scaffold",
            source_template=request.template_type,
            source_workflow=source_workflow,
            source_experience_id=source_experience_id,
            tags=manifest["tags"],
        )
        entrypoint = self._build_python_entrypoint(request.template_type)
        readme = (
            f"# {request.name}\n\n"
            f"Generated {status} executable skill scaffold for `{request.skill_id}`.\n\n"
            f"- template: `{request.template_type}`\n"
            f"- runtime: `python3` + `json_stdio`\n"
            f"- entrypoint: `{entrypoint_name}`\n"
            f"- asset status: `{status}`\n"
            "- phase-p invocation: runtime wrapper compatible, local-session aware\n\n"
            "## Input\n"
            f"See `input.schema.json`. Example payload: `{json.dumps(sample_input, ensure_ascii=False)}`\n\n"
            "## Output\n"
            f"See `output.schema.json`. Expected primary field: `{expected_field}`\n\n"
            "## Phase P runtime hook\n"
            "The scaffold expects invocation envelope metadata under `__invocation_envelope__` and preserves `local_session_id` when present.\n\n"
            "## Smoke test\n"
            "Run `pytest tests/test_smoke.py -q` inside this skill directory.\n"
        )
        smoke_test = (
            "import json, subprocess\n\n"
            f"def test_smoke():\n"
            f"    proc = subprocess.run(['python3', '{entrypoint_path}'], input=json.dumps({{'skill_id': '{request.skill_id}', 'inputs': {json.dumps(sample_input, ensure_ascii=False)}, '__invocation_envelope__': {{'request_id': 'req-1'}}, 'local_session_id': 'local-1'}}), text=True, capture_output=True, check=False)\n"
            f"    assert proc.returncode == 0\n"
            f"    payload = json.loads(proc.stdout)\n"
            f"    assert payload['skill_id'] == '{request.skill_id}'\n"
            f"    assert '{expected_field}' in payload['output']\n"
            f"    assert payload['metadata']['runtime_wrapper_compatible'] is True\n"
            f"    assert payload['metadata']['local_session_id'] == 'local-1'\n"
        )

        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        input_schema_path.write_text(json.dumps(input_schema, ensure_ascii=False, indent=2))
        output_schema_path.write_text(json.dumps(output_schema, ensure_ascii=False, indent=2))
        error_schema_path.write_text(json.dumps(error_schema, ensure_ascii=False, indent=2))
        metadata_path.write_text(metadata.model_dump_json(indent=2))
        entrypoint_path.write_text(entrypoint)
        readme_path.write_text(readme)
        smoke_test_path.write_text(smoke_test)

        asset = GeneratedSkillAsset(
            skill_id=request.skill_id,
            asset_dir=str(asset_dir),
            manifest_path=str(manifest_path),
            schema_path=str(input_schema_path),
            input_schema_path=str(input_schema_path),
            output_schema_path=str(output_schema_path),
            error_schema_path=str(error_schema_path),
            entrypoint_path=str(entrypoint_path),
            readme_path=str(readme_path),
        )
        self._upsert_index(metadata=metadata, asset=asset)
        return asset, metadata

    def promote_candidate_to_core(self, skill_id: str, accepted_by: str = "") -> SkillAssetMetadata:
        candidate_dir = self.resolve_asset_dir(skill_id, status="candidate")
        core_dir = self.resolve_asset_dir(skill_id, status="core")
        if not candidate_dir.exists():
            raise ValueError(f"Candidate skill asset not found: {skill_id}")
        core_dir.parent.mkdir(parents=True, exist_ok=True)
        if core_dir.exists():
            raise ValueError(f"Core skill asset already exists: {skill_id}")
        candidate_dir.rename(core_dir)
        metadata_path = core_dir / "metadata.json"
        metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
        metadata.asset_status = "core"
        metadata.accepted = True
        metadata.accepted_at = datetime.now(UTC).isoformat()
        metadata.accepted_by = accepted_by or None
        metadata.updated_at = datetime.now(UTC).isoformat()
        metadata_path.write_text(metadata.model_dump_json(indent=2))
        manifest_path = core_dir / "manifest.json"
        asset = GeneratedSkillAsset(
            skill_id=skill_id,
            asset_dir=str(core_dir),
            manifest_path=str(manifest_path),
            schema_path=str(core_dir / "input.schema.json"),
            input_schema_path=str(core_dir / "input.schema.json"),
            output_schema_path=str(core_dir / "output.schema.json"),
            error_schema_path=str(core_dir / "error.schema.json"),
            entrypoint_path=str(core_dir / "main.py"),
            readme_path=str(core_dir / "README.md"),
        )
        self._remove_index_entry(skill_id, "candidate")
        self._upsert_index(metadata=metadata, asset=asset)
        return metadata

    def archive_asset(self, skill_id: str, status: str = "candidate") -> SkillAssetMetadata:
        source_dir = self.resolve_asset_dir(skill_id, status=status)
        archived_dir = self.resolve_asset_dir(skill_id, status="archived")
        if not source_dir.exists():
            raise ValueError(f"Skill asset not found for archive: {skill_id}@{status}")
        archived_dir.parent.mkdir(parents=True, exist_ok=True)
        if archived_dir.exists():
            raise ValueError(f"Archived skill asset already exists: {skill_id}")
        source_dir.rename(archived_dir)
        metadata_path = archived_dir / "metadata.json"
        metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
        metadata.archived_from = status
        metadata.asset_status = "archived"
        metadata.updated_at = datetime.now(UTC).isoformat()
        metadata_path.write_text(metadata.model_dump_json(indent=2))
        self._remove_index_entry(skill_id, status)
        self._upsert_index(
            metadata=metadata,
            asset=GeneratedSkillAsset(
                skill_id=skill_id,
                asset_dir=str(archived_dir),
                manifest_path=str(archived_dir / "manifest.json"),
                schema_path=str(archived_dir / "input.schema.json"),
                input_schema_path=str(archived_dir / "input.schema.json"),
                output_schema_path=str(archived_dir / "output.schema.json"),
                error_schema_path=str(archived_dir / "error.schema.json"),
                entrypoint_path=str(archived_dir / "main.py"),
                readme_path=str(archived_dir / "README.md"),
            ),
        )
        return metadata

    def restore_archived_to_candidate(self, skill_id: str) -> SkillAssetMetadata:
        archived_dir = self.resolve_asset_dir(skill_id, status="archived")
        candidate_dir = self.resolve_asset_dir(skill_id, status="candidate")
        if not archived_dir.exists():
            raise ValueError(f"Archived skill asset not found: {skill_id}")
        candidate_dir.parent.mkdir(parents=True, exist_ok=True)
        if candidate_dir.exists():
            raise ValueError(f"Candidate skill asset already exists: {skill_id}")
        archived_dir.rename(candidate_dir)
        metadata_path = candidate_dir / "metadata.json"
        metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
        metadata.asset_status = "candidate"
        metadata.updated_at = datetime.now(UTC).isoformat()
        metadata_path.write_text(metadata.model_dump_json(indent=2))
        self._remove_index_entry(skill_id, "archived")
        self._upsert_index(
            metadata=metadata,
            asset=GeneratedSkillAsset(
                skill_id=skill_id,
                asset_dir=str(candidate_dir),
                manifest_path=str(candidate_dir / "manifest.json"),
                schema_path=str(candidate_dir / "input.schema.json"),
                input_schema_path=str(candidate_dir / "input.schema.json"),
                output_schema_path=str(candidate_dir / "output.schema.json"),
                error_schema_path=str(candidate_dir / "error.schema.json"),
                entrypoint_path=str(candidate_dir / "main.py"),
                readme_path=str(candidate_dir / "README.md"),
            ),
        )
        return metadata

    def deprecate_core_asset(self, skill_id: str) -> SkillAssetMetadata:
        core_dir = self.resolve_asset_dir(skill_id, status="core")
        deprecated_dir = self.resolve_asset_dir(skill_id, status="deprecated")
        if not core_dir.exists():
            raise ValueError(f"Core skill asset not found: {skill_id}")
        deprecated_dir.parent.mkdir(parents=True, exist_ok=True)
        if deprecated_dir.exists():
            raise ValueError(f"Deprecated skill asset already exists: {skill_id}")
        core_dir.rename(deprecated_dir)
        metadata_path = deprecated_dir / "metadata.json"
        metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
        metadata.asset_status = "deprecated"
        metadata.updated_at = datetime.now(UTC).isoformat()
        metadata_path.write_text(metadata.model_dump_json(indent=2))
        manifest_path = deprecated_dir / "manifest.json"
        self._remove_index_entry(skill_id, "core")
        self._upsert_index(
            metadata=metadata,
            asset=GeneratedSkillAsset(
                skill_id=skill_id,
                asset_dir=str(deprecated_dir),
                manifest_path=str(manifest_path),
                schema_path=str(deprecated_dir / "input.schema.json"),
                input_schema_path=str(deprecated_dir / "input.schema.json"),
                output_schema_path=str(deprecated_dir / "output.schema.json"),
                error_schema_path=str(deprecated_dir / "error.schema.json"),
                entrypoint_path=str(deprecated_dir / "main.py"),
                readme_path=str(deprecated_dir / "README.md"),
            ),
        )
        return metadata

    def list_assets(self, status: str | None = None) -> list[SkillAssetIndexEntry]:
        index = self._load_index()
        if status is None:
            return index.assets
        return [item for item in index.assets if item.asset_status == status]

    def check_consistency(self, skill_id: str | None = None) -> list[SkillAssetConsistencyResult]:
        index = self._load_index()
        results: list[SkillAssetConsistencyResult] = []
        for item in index.assets:
            if skill_id and item.skill_id != skill_id:
                continue
            issues: list[SkillAssetConsistencyIssue] = []
            base = self._resolve_index_path(item.path)
            manifest_path = self._resolve_index_path(item.manifest_path)
            metadata_path = self._resolve_index_path(item.metadata_path)
            for path, label in [(base, "asset_dir"), (manifest_path, "manifest"), (metadata_path, "metadata")]:
                if not path.exists():
                    issues.append(SkillAssetConsistencyIssue(kind="missing_file", message=f"Missing {label}", details={"path": str(path)}))
            if metadata_path.exists():
                metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
                if metadata.asset_status != item.asset_status:
                    issues.append(SkillAssetConsistencyIssue(kind="index_mismatch", message="Asset status mismatch", details={"index": item.asset_status, "metadata": metadata.asset_status}))
                entrypoint = base / "main.py"
                if not entrypoint.exists():
                    issues.append(SkillAssetConsistencyIssue(kind="missing_entrypoint", message="Missing entrypoint", details={"path": str(entrypoint)}))
                smoke = base / "tests" / "test_smoke.py"
                if not smoke.exists():
                    issues.append(SkillAssetConsistencyIssue(kind="missing_smoke_test", message="Missing smoke test", details={"path": str(smoke)}))
            results.append(SkillAssetConsistencyResult(skill_id=item.skill_id, ok=not issues, issues=issues))
        return results

    def rebuild_index(self) -> SkillAssetIndex:
        assets: list[SkillAssetIndexEntry] = []
        for status_root, status in [(self._core_root, "core"), (self._candidate_root, "candidate"), (self._archived_root, "archived"), (self._deprecated_root, "deprecated")]:
            if not status_root.exists():
                continue
            for metadata_path in status_root.glob("*/*/metadata.json"):
                metadata = SkillAssetMetadata.model_validate_json(metadata_path.read_text())
                asset_dir = metadata_path.parent
                assets.append(
                    SkillAssetIndexEntry(
                        skill_id=metadata.skill_id,
                        asset_slug=metadata.asset_slug,
                        asset_status=metadata.asset_status,
                        asset_origin=metadata.asset_origin,
                        runtime_adapter=metadata.runtime_adapter,
                        version=metadata.version,
                        content_maturity=metadata.content_maturity,
                        path=str(asset_dir.relative_to(self._base_dir)),
                        manifest_path=str((asset_dir / "manifest.json").relative_to(self._base_dir)),
                        metadata_path=str(metadata_path.relative_to(self._base_dir)),
                        accepted=metadata.accepted,
                        accepted_at=metadata.accepted_at,
                    )
                )
        index = SkillAssetIndex(assets=sorted(assets, key=lambda x: (x.skill_id, x.version, x.asset_status)))
        self._write_index(index)
        return index

    def _upsert_index(self, *, metadata: SkillAssetMetadata, asset: GeneratedSkillAsset) -> None:
        index = self._load_index()
        entry = SkillAssetIndexEntry(
            skill_id=metadata.skill_id,
            asset_slug=metadata.asset_slug,
            asset_status=metadata.asset_status,
            asset_origin=metadata.asset_origin,
            runtime_adapter=metadata.runtime_adapter,
            version=metadata.version,
            content_maturity=metadata.content_maturity,
            path=str(Path(asset.asset_dir).relative_to(self._base_dir)),
            manifest_path=str(Path(asset.manifest_path).relative_to(self._base_dir)),
            metadata_path=str((Path(asset.asset_dir) / "metadata.json").relative_to(self._base_dir)),
            accepted=metadata.accepted,
            accepted_at=metadata.accepted_at,
        )
        index.assets = [item for item in index.assets if not (item.skill_id == entry.skill_id and item.asset_status == entry.asset_status)]
        index.assets.append(entry)
        index.updated_at = datetime.now(UTC).isoformat()
        self._write_index(index)

    def _remove_index_entry(self, skill_id: str, status: str) -> None:
        index = self._load_index()
        index.assets = [item for item in index.assets if not (item.skill_id == skill_id and item.asset_status == status)]
        index.updated_at = datetime.now(UTC).isoformat()
        self._write_index(index)

    def _load_index(self) -> SkillAssetIndex:
        if not self._index_path.exists():
            return SkillAssetIndex()
        return SkillAssetIndex.model_validate_json(self._index_path.read_text())

    def _write_index(self, index: SkillAssetIndex) -> None:
        self._assets_root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(index.model_dump_json(indent=2))

    def _sample_input(self, template_type: str) -> dict[str, str]:
        if template_type == "key_value":
            return {"text": "name: Alice\nrole: Engineer"}
        return {"text": "Hello World"}

    def _expected_field(self, template_type: str) -> str:
        if template_type == "slugify":
            return "slug"
        if template_type == "key_value":
            return "lines"
        return "text"

    def _build_input_schema(self, template_type: str) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }

    def _build_output_schema(self, template_type: str) -> dict:
        if template_type == "slugify":
            return {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
                "additionalProperties": False,
            }
        if template_type == "key_value":
            return {
                "type": "object",
                "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
                "required": ["lines"],
                "additionalProperties": False,
            }
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }

    def _build_python_entrypoint(self, template_type: str) -> str:
        if template_type == "slugify":
            body = "text = inputs.get('text', '')\noutput = {'slug': text.lower().replace(' ', '-')}"
        elif template_type == "key_value":
            body = "text = inputs.get('text', '')\noutput = {'lines': [line.strip() for line in text.splitlines() if ':' in line]}"
        else:
            body = "text = inputs.get('text', '')\noutput = {'text': text.strip()}"
        return (
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read() or '{}')\n"
            "inputs = payload.get('inputs', {})\n"
            "runtime_envelope = payload.get('__invocation_envelope__') or {}\n"
            "local_session_id = payload.get('local_session_id')\n"
            f"{body}\n"
            "json.dump({'skill_id': payload.get('skill_id', ''), 'status': 'completed', 'output': output, 'metadata': {'runtime_wrapper_compatible': True, 'local_session_id': local_session_id, 'request_id': runtime_envelope.get('request_id')}}, sys.stdout)\n"
        )
