from pathlib import Path

from app.services.model_config_loader import DEFAULT_MODEL_ENV_PATH, ModelConfigLoader


def test_model_config_loader_from_local_file(tmp_path: Path) -> None:
    config_path = tmp_path / "model.local.json"
    config_path.write_text(
        '{"base_url":"https://crs.ruinique.com","wire_api":"openai-responses","model":"gpt-5.4","api_key_env":"OPENAI_API_KEY"}',
        encoding="utf-8",
    )
    loader = ModelConfigLoader(local_config_path=str(config_path))
    config = loader.load()

    assert config.base_url == "https://crs.ruinique.com"
    assert config.wire_api == "openai-responses"
    assert config.model == "gpt-5.4"


def test_model_config_loader_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://crs.ruinique.com")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    loader = ModelConfigLoader(local_config_path="/nonexistent/model.local.json")
    config = loader.load()

    assert config.base_url == "https://crs.ruinique.com"
    assert config.model == "gpt-5.4"


def test_model_config_loader_resolves_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://crs.ruinique.com")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    loader = ModelConfigLoader(local_config_path="/nonexistent/model.local.json")
    config = loader.load()

    assert loader.resolve_api_key(config) == "sk-test"


def test_model_config_loader_loads_private_env_file(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / "model.local.env"
    env_path.write_text("OPENAI_API_KEY=sk-file\nOPENAI_BASE_URL=https://crs.ruinique.com\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr("app.services.model_config_loader.DEFAULT_MODEL_ENV_PATH", env_path)
    loader = ModelConfigLoader(local_config_path="/nonexistent/model.local.json")
    config = loader.load()

    assert config.base_url == "https://crs.ruinique.com"
    assert loader.resolve_api_key(config) == "sk-file"
