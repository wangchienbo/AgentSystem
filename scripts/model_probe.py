from __future__ import annotations

from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader


if __name__ == "__main__":
    loader = ModelConfigLoader()
    config = loader.load()
    api_key = loader.resolve_api_key(config)
    client = OpenAIResponsesClient(config=config, api_key=api_key)
    result = client.probe("Return only: MODEL_PROBE_OK")
    print(result)
