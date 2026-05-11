from __future__ import annotations

import os
from pathlib import Path

from app.ai import model_router as model_router_module
from app.bootstrap.runtime import build_runtime


def build_runtime_for_bootstrap_tests(tmp_path: Path) -> dict:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        """
models:
  cheap:
    provider: openai_compatible
    base_url: https://example.com/v1
    model: cheap-model
    api_key_env: OPENAI_API_KEY
routing:
  callers:
    default:
      default_model: cheap
model:
  provider: openai_compatible
  base_url: https://example.com/v1
  model: cheap-model
  api_key_env: OPENAI_API_KEY
""".strip()
        + "\n",
        encoding="utf-8",
    )
    os.environ["AGENTSYSTEM_HOME"] = str(tmp_path / "agentsystem-home")
    os.environ["AGENTSYSTEM_CONFIG_DIR"] = str(config_dir)
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    model_router_module.DEFAULT_CONFIG_PATH = config_dir / "config.yaml"
    return build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
