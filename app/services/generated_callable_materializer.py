from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


class GeneratedCallableMaterializerError(ValueError):
    pass


class GeneratedCallableMaterializer:
    def __init__(self, base_dir: str = "data/generated_callable_skills") -> None:
        self._base_path = Path(base_dir)
        self._base_path.mkdir(parents=True, exist_ok=True)

    def materialize_handler(self, *, skill_id: str, operation: str) -> str:
        module_name = skill_id.replace(".", "_")
        file_path = self._base_path / f"{module_name}.py"
        if operation == "normalize_object_keys":
            content = self._render_normalize_object_keys(skill_id)
        elif operation == "echo_object_keys":
            content = self._render_echo_object_keys(skill_id)
        else:
            raise GeneratedCallableMaterializerError(f"Unsupported callable generation operation: {operation}")
        file_path.write_text(content, encoding="utf-8")
        return f"{file_path}:{'handle'}"

    def load_handler(self, handler_entry: str) -> Callable[[SkillExecutionRequest], SkillExecutionResult]:
        try:
            file_path_str, function_name = handler_entry.split(":", 1)
        except ValueError as error:
            raise GeneratedCallableMaterializerError(f"Invalid handler entry: {handler_entry}") from error
        file_path = Path(file_path_str)
        if not file_path.exists():
            raise GeneratedCallableMaterializerError(f"Generated callable file not found: {file_path}")
        module = self._load_module(file_path)
        handler = getattr(module, function_name, None)
        if handler is None or not callable(handler):
            raise GeneratedCallableMaterializerError(f"Handler not found or not callable: {handler_entry}")
        return handler

    def _load_module(self, file_path: Path) -> ModuleType:
        module_name = f"generated_callable_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise GeneratedCallableMaterializerError(f"Unable to load generated callable module: {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _render_normalize_object_keys(skill_id: str) -> str:
        return f'''from __future__ import annotations

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


def _normalize(value):
    if isinstance(value, dict):
        normalized = {{}}
        for key, item in value.items():
            clean_key = str(key).strip().lower().replace(" ", "_").replace("-", "_")
            normalized[clean_key] = _normalize(item)
        return normalized
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def handle(request: SkillExecutionRequest) -> SkillExecutionResult:
    payload = request.inputs.get("payload", {{}})
    normalized = _normalize(payload)
    return SkillExecutionResult(
        skill_id="{skill_id}",
        status="completed",
        output={{
            "normalized": normalized,
            "top_level_keys": sorted(list(normalized.keys())) if isinstance(normalized, dict) else [],
            "adapter": "callable",
        }},
    )
'''

    @staticmethod
    def _render_echo_object_keys(skill_id: str) -> str:
        return f'''from __future__ import annotations

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


def handle(request: SkillExecutionRequest) -> SkillExecutionResult:
    echoed = {{key: value for key, value in request.inputs.items() if key != "working_set"}}
    return SkillExecutionResult(
        skill_id="{skill_id}",
        status="completed",
        output={{
            "echoed": echoed,
            "top_level_keys": sorted(list(echoed.keys())),
            "adapter": "callable",
        }},
    )
'''
