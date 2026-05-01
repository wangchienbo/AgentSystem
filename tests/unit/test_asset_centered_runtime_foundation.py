from __future__ import annotations

from pathlib import Path

import pytest

from app.system.model_runtime.model_pool_loader import ModelPoolConfigError, ModelPoolLoader
from app.system.startup.system_bootstrap_loader import SystemBootstrapConfigError, SystemBootstrapConfigLoader


def test_system_bootstrap_loader_reads_minimal_config(tmp_path: Path) -> None:
    config_path = tmp_path / "system_bootstrap.yaml"
    config_path.write_text(
        """
version: 1
asset_center:
  asset_id: asset:asset_center:v1
  bootstrap_module: app.system.asset_center.bootstrap
model_runtime:
  config_path: /root/.config/agentsystem/model_pool.yaml
startup:
  order: [asset_center, model_runtime, system_assets, interaction_runtime, external_entrypoints]
  required_assets: [asset:asset_center:v1, asset:self_iteration_center:v1]
""".strip(),
        encoding="utf-8",
    )

    payload = SystemBootstrapConfigLoader(config_path).load()

    assert payload["asset_center"]["asset_id"] == "asset:asset_center:v1"
    assert payload["startup"]["order"][0] == "asset_center"


def test_system_bootstrap_loader_rejects_missing_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "system_bootstrap.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    with pytest.raises(SystemBootstrapConfigError):
        SystemBootstrapConfigLoader(config_path).load()


def test_model_pool_loader_reads_minimal_model_pool(tmp_path: Path) -> None:
    config_path = tmp_path / "model_pool.yaml"
    config_path.write_text(
        """
version: 1
default_model: gpt-5.4
fallback_model: gpt-4.1
models:
  - model_id: gpt-5.4
    provider: OpenAICompatible
    base_url: https://example.invalid/v1
    api_key_env: OPENAI_API_KEY
    enabled: true
  - model_id: gpt-4.1
    provider: OpenAICompatible
    base_url: https://example.invalid/v1
    api_key_env: OPENAI_API_KEY
    enabled: true
""".strip(),
        encoding="utf-8",
    )

    payload = ModelPoolLoader(config_path).load()

    assert payload["default_model"] == "gpt-5.4"
    assert len(payload["models"]) == 2


def test_model_pool_loader_rejects_unknown_fallback(tmp_path: Path) -> None:
    config_path = tmp_path / "model_pool.yaml"
    config_path.write_text(
        """
version: 1
default_model: gpt-5.4
fallback_model: gpt-4.1
models:
  - model_id: gpt-5.4
    provider: OpenAICompatible
    base_url: https://example.invalid/v1
    api_key_env: OPENAI_API_KEY
    enabled: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ModelPoolConfigError):
        ModelPoolLoader(config_path).load()
