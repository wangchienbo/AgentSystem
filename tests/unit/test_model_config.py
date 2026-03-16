from pathlib import Path

from app.services.model_config_loader import ModelConfigLoader


def test_model_config_loader_from_yaml_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model:\n  base_url: https://crs.ruinique.com\n  wire_api: openai-responses\n  model: gpt-5.4\n  api_key_env: OPENAI_API_KEY\n",
        encoding="utf-8",
    )
    loader = ModelConfigLoader(local_config_path=str(config_path))
    config = loader.load()

    assert config.base_url == "https://crs.ruinique.com"
    assert config.wire_api == "openai-responses"
    assert config.model == "gpt-5.4"


def test_model_config_loader_injects_api_key_from_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model:\n  base_url: https://crs.ruinique.com\n  model: gpt-5.4\n  api_key: sk-yaml\n  api_key_env: OPENAI_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    loader = ModelConfigLoader(local_config_path=str(config_path))
    config = loader.load()

    assert loader.resolve_api_key(config) == "sk-yaml"


def test_model_config_loader_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://crs.ruinique.com")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    loader = ModelConfigLoader(local_config_path="/nonexistent/config.yaml")
    config = loader.load()

    assert config.base_url == "https://crs.ruinique.com"
    assert config.model == "gpt-5.4"
