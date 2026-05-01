from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SystemBootstrapConfigError(ValueError):
    pass


class SystemBootstrapConfigLoader:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            raise SystemBootstrapConfigError(f"Bootstrap config not found: {self._path}")
        payload = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise SystemBootstrapConfigError("Bootstrap config must be a mapping")
        self._validate(payload)
        return payload

    def _validate(self, payload: dict[str, Any]) -> None:
        if payload.get("version") != 1:
            raise SystemBootstrapConfigError("Bootstrap config version must be 1")
        asset_center = payload.get("asset_center")
        model_runtime = payload.get("model_runtime")
        startup = payload.get("startup")
        if not isinstance(asset_center, dict):
            raise SystemBootstrapConfigError("asset_center section is required")
        if not isinstance(model_runtime, dict):
            raise SystemBootstrapConfigError("model_runtime section is required")
        if not isinstance(startup, dict):
            raise SystemBootstrapConfigError("startup section is required")
        if not asset_center.get("asset_id"):
            raise SystemBootstrapConfigError("asset_center.asset_id is required")
        if not asset_center.get("bootstrap_module"):
            raise SystemBootstrapConfigError("asset_center.bootstrap_module is required")
        if not model_runtime.get("config_path"):
            raise SystemBootstrapConfigError("model_runtime.config_path is required")
        order = startup.get("order")
        if not isinstance(order, list) or not order:
            raise SystemBootstrapConfigError("startup.order must be a non-empty list")
        required_assets = startup.get("required_assets")
        if not isinstance(required_assets, list) or not required_assets:
            raise SystemBootstrapConfigError("startup.required_assets must be a non-empty list")
