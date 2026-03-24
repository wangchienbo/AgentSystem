import os
from unittest.mock import patch

from app.bootstrap.runtime import build_runtime
from app.services.model_self_refiner import ModelSelfRefiner


def test_runtime_does_not_wire_model_refiner_by_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AGENTSYSTEM_ENABLE_MODEL_REFINER", None)
        runtime = build_runtime()
        service = runtime["self_refinement"]
        assert getattr(service, "_model_self_refiner") is None


def test_runtime_wires_model_refiner_when_explicitly_enabled() -> None:
    with patch.dict(os.environ, {"AGENTSYSTEM_ENABLE_MODEL_REFINER": "1"}, clear=False):
        runtime = build_runtime()
        service = runtime["self_refinement"]
        assert isinstance(getattr(service, "_model_self_refiner"), ModelSelfRefiner)
