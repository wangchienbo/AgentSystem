from __future__ import annotations

import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillAsset, GeneratedSkillRequest


class GeneratedSkillAssetStore:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def create_scaffold(self, request: GeneratedSkillRequest) -> GeneratedSkillAsset:
        asset_dir = self._base_dir / request.skill_id.replace('.', '_')
        asset_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = asset_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        entrypoint_name = "main.py"
        entrypoint_path = asset_dir / entrypoint_name
        manifest_path = asset_dir / "manifest.json"
        input_schema_path = asset_dir / "input.schema.json"
        output_schema_path = asset_dir / "output.schema.json"
        error_schema_path = asset_dir / "error.schema.json"
        readme_path = asset_dir / "README.md"
        smoke_test_path = tests_dir / "test_smoke.py"

        input_schema = self._build_input_schema(request.template_type)
        output_schema = self._build_output_schema(request.template_type)
        error_schema = {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
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
            "runtime_adapter": "executable",
            "adapter": {
                "kind": "executable",
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
        }
        entrypoint = self._build_python_entrypoint(request.template_type)
        readme = (
            f"# {request.name}\n\n"
            f"Generated executable skill scaffold for `{request.skill_id}`.\n\n"
            f"- template: `{request.template_type}`\n"
            f"- runtime: `python3` + `json_stdio`\n"
            f"- entrypoint: `{entrypoint_name}`\n\n"
            "## Input\n"
            f"See `input.schema.json`. Example payload: `{json.dumps(sample_input, ensure_ascii=False)}`\n\n"
            "## Output\n"
            f"See `output.schema.json`. Expected primary field: `{expected_field}`\n\n"
            "## Smoke test\n"
            "Run `pytest tests/test_smoke.py -q` inside this skill directory.\n"
        )
        smoke_test = (
            "import json, subprocess\n\n"
            f"def test_smoke():\n"
            f"    proc = subprocess.run(['python3', '{entrypoint_path}'], input=json.dumps({{'skill_id': '{request.skill_id}', 'inputs': {json.dumps(sample_input, ensure_ascii=False)}}}), text=True, capture_output=True, check=False)\n"
            f"    assert proc.returncode == 0\n"
            f"    payload = json.loads(proc.stdout)\n"
            f"    assert payload['skill_id'] == '{request.skill_id}'\n"
            f"    assert '{expected_field}' in payload['output']\n"
        )

        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        input_schema_path.write_text(json.dumps(input_schema, ensure_ascii=False, indent=2))
        output_schema_path.write_text(json.dumps(output_schema, ensure_ascii=False, indent=2))
        error_schema_path.write_text(json.dumps(error_schema, ensure_ascii=False, indent=2))
        entrypoint_path.write_text(entrypoint)
        readme_path.write_text(readme)
        smoke_test_path.write_text(smoke_test)

        return GeneratedSkillAsset(
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
            "properties": {
                "text": {"type": "string"},
            },
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
            f"{body}\n"
            "json.dump({'skill_id': payload.get('skill_id', ''), 'status': 'completed', 'output': output}, sys.stdout)\n"
        )
