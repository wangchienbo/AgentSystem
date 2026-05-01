"""Model selection / fallback unit tests for Phase 9.1.

Focus: ModelSelector resolution logic covering preferred, fallback,
minimum requirements, and failure paths.
"""
from __future__ import annotations

import pytest

from app.system.model_runtime.model_client_registry import ModelRuntimeRecord
from app.system.model_runtime.model_selector import ModelSelectionError, ModelSelector


def _record(
    model_id: str,
    *,
    enabled: bool = True,
    healthy: bool = True,
    metadata: dict | None = None,
) -> ModelRuntimeRecord:
    return ModelRuntimeRecord(
        model_id=model_id,
        provider="test",
        base_url="https://test.invalid/v1",
        api_key_env="TEST_KEY",
        wire_api="openai-chat",
        enabled=enabled,
        healthy=healthy,
        metadata=metadata or {},
    )


class TestModelSelectorPreferredModel:
    def test_selects_healthy_preferred(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[_record("gpt-5"), _record("gpt-4")],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
        )
        assert result.model_id == "gpt-5"
        assert result.reason == "preferred"

    def test_selects_healthy_preferred_with_requirements(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[
                _record("gpt-5", metadata={"structured_output": True}),
                _record("gpt-4"),
            ],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
            minimum_requirements={"structured_output": True},
        )
        assert result.model_id == "gpt-5"


class TestModelSelectorFallback:
    def test_falls_back_when_preferred_unhealthy(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[
                _record("gpt-5", healthy=False),
                _record("gpt-4", healthy=True),
            ],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
        )
        assert result.model_id == "gpt-4"
        assert result.reason == "fallback"

    def test_falls_back_when_preferred_missing(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[_record("gpt-4")],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
        )
        assert result.model_id == "gpt-4"
        assert result.reason == "fallback"

    def test_fallback_with_requirements(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[
                _record("gpt-5", metadata={"tool_use": True}),
                _record("gpt-4", metadata={"tool_use": True}),
            ],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
            minimum_requirements={"tool_use": True},
        )
        assert result.model_id == "gpt-5"

    def test_fallback_used_when_preferred_fails_requirements(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[
                _record("gpt-5", metadata={"structured_output": False}),
                _record("gpt-4", metadata={"structured_output": True}),
            ],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
            minimum_requirements={"structured_output": True},
        )
        assert result.model_id == "gpt-4"
        assert result.reason == "fallback"


class TestModelSelectorFailure:
    def test_raises_when_no_healthy_models(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[
                    _record("gpt-5", healthy=False),
                    _record("gpt-4", healthy=False),
                ],
                preferred_model="gpt-5",
                fallback_model="gpt-4",
            )

    def test_raises_when_fallback_fails_requirements(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[
                    _record("gpt-5", metadata={"structured_output": False}),
                    _record("gpt-4", metadata={"structured_output": False}),
                ],
                preferred_model="gpt-5",
                fallback_model="gpt-4",
                minimum_requirements={"structured_output": True},
            )

    def test_raises_when_preferred_disabled(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[
                    _record("gpt-5", enabled=False),
                ],
                preferred_model="gpt-5",
                fallback_model="gpt-4",
            )


class TestModelSelectorEdgeCases:
    def test_empty_model_records(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[],
                preferred_model="gpt-5",
                fallback_model="gpt-4",
            )

    def test_no_preferred_or_fallback(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[_record("gpt-5")],
                preferred_model=None,
                fallback_model=None,
            )

    def test_same_model_as_preferred_and_fallback(self) -> None:
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[_record("gpt-5")],
            preferred_model="gpt-5",
            fallback_model="gpt-5",
        )
        assert result.model_id == "gpt-5"
        assert result.reason == "preferred"

    def test_no_requirements_check(self) -> None:
        """No minimum_requirements means any healthy model is acceptable."""
        selector = ModelSelector()
        result = selector.resolve(
            model_records=[_record("gpt-5", metadata={})],
            preferred_model="gpt-5",
            fallback_model="gpt-4",
        )
        assert result.model_id == "gpt-5"

    def test_preferred_unhealthy_fallback_unhealthy(self) -> None:
        selector = ModelSelector()
        with pytest.raises(ModelSelectionError):
            selector.resolve(
                model_records=[
                    _record("gpt-5", healthy=False),
                    _record("gpt-4", healthy=False),
                ],
                preferred_model="gpt-5",
                fallback_model="gpt-4",
                minimum_requirements={},
            )
