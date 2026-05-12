from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.services.light_brain_memory import LightBrainMemory
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.system.gateway.light_brain_interpreter import LightBrainInterpreter


def test_light_brain_gateway_identity_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    gateway = LightBrainGateway(memory=LightBrainMemory(), interpreter=LightBrainInterpreter())

    assert gateway._name
    identity_path = resolve_runtime_paths().data_dir / "lightbrain" / "identity.json"
    assert identity_path.exists()
