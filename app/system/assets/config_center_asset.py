from __future__ import annotations

from typing import Any

from app.system.asset_center.models import AssetMethodSpec
from app.system.assets.base_asset import BaseAsset
from app.system.assets.descriptor_builder import build_asset_descriptor


class ConfigCenterAsset(BaseAsset):
    def __init__(self, service: Any) -> None:
        self._service = service

    def asset_id(self) -> str:
        return "asset:config_center:v1"

    def build_descriptor(self):
        return build_asset_descriptor(
            descriptor_version=1,
            asset_id=self.asset_id(),
            kind="system_asset",
            summary="Bootstrap configuration source",
            detail=(
                "Standard read-oriented asset for system skill config and app binding lookups. "
                "Descriptor and method contract are generated from one builder source."
            ),
            methods=[
                AssetMethodSpec(
                    name="get_config",
                    description="Read config center values for a skill or app binding scope",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "skill_id": {"type": "string"},
                            "app_id": {"type": "string"},
                        },
                    },
                )
            ],
            metadata={"asset_family": "system_config", "protocol": "v1"},
        )

    def build_method_mappings(self):
        return {
            "get_config": lambda skill_id=None, app_id=None: {
                "skill_config": (lambda cfg: cfg.__dict__ if cfg is not None else None)(self._service.get_skill_config(skill_id) if skill_id else None),
                "app_bindings": [b.__dict__ for b in self._service.get_app_bindings(app_id)] if app_id else [],
            },
        }

    def get_service_ref(self) -> Any:
        return self._service
