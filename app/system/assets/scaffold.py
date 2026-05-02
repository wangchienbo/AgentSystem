from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AssetScaffoldTemplate:
    """Phase P 5.4: Scaffold template for new assets with Phase P compliance defaults."""
    asset_id: str = ""
    kind: str = "system_asset"
    summary: str = ""
    detail: str = ""
    methods: list[dict[str, Any]] = field(default_factory=list)
    preferred_model: str | None = None
    fallback_model: str | None = None

    def to_manifest(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.asset_id,
            "version": "1.0.0",
            "source_path": f"source/{self.asset_id}",
            "dependencies": [],
            "metadata": {
                "invocation_contract_version": "phase-p-v1",
                "runtime_wrapper_compatibility": True,
                "session_binding_support": "required",
                "endpoint_requirement": "none",
                "tool_vllm_usage_mode": "local_session_only",
                "kind": self.kind,
                "summary": self.summary,
            },
        }

    def to_descriptor_init(self) -> str:
        methods_code = ",\n            ".join(
            f'AssetMethodSpec(name="{m["name"]}", description="{m.get("description", "")}", input_schema={m.get("input_schema", {})})'
            for m in self.methods
        )
        return f"""from app.system.assets.base_asset import BaseAsset, AssetMethodHandler
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetModelRequirement


class {self._class_name}(BaseAsset):
    def build_descriptor(self) -> AssetDescriptorRecord:
        return AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="{self.asset_id}",
            kind="{self.kind}",
            summary="{self.summary}",
            detail="{self.detail}",
            methods=(
                {methods_code}
            ),
            model_requirement=AssetModelRequirement(
                preferred_model={repr(self.preferred_model)},
                fallback_model={repr(self.fallback_model)},
                minimum_requirements={{}},
            ),
            metadata={{
                "invocation_contract_version": "phase-p-v1",
                "runtime_wrapper_compatibility": True,
                "session_binding_support": "required",
                "endpoint_requirement": "none",
                "tool_vllm_usage_mode": "local_session_only",
            }},
        )

    def build_method_mappings(self) -> dict[str, AssetMethodHandler]:
        return {{
            {self._method_mappings()}
        }}

    def get_service_ref(self):
        return self
"""

    @property
    def _class_name(self) -> str:
        return "".join(part.capitalize() for part in self.asset_id.replace("asset:", "").replace(":v1", "").split("_")) + "Asset"

    def _method_mappings(self) -> str:
        return ",\n            ".join(
            f'"{m["name"]}": self.{m.get("handler", m["name"])}'
            for m in self.methods
        )


def generate_asset_scaffold(
    asset_id: str,
    *,
    kind: str = "system_asset",
    summary: str = "",
    methods: list[dict[str, Any]] | None = None,
) -> AssetScaffoldTemplate:
    return AssetScaffoldTemplate(
        asset_id=asset_id,
        kind=kind,
        summary=summary,
        detail="",
        methods=methods or [],
    )
