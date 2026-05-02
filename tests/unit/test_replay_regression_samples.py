from __future__ import annotations

import pytest

from app.models.governance_observation import ReplayRegressionSample
from app.system.replay_regression_samples import (
    ReplayRegressionSampleStoreError,
    ingest_curated_replay_samples,
    list_replay_regression_samples,
    load_replay_regression_sample,
    persist_replay_regression_sample,
    validate_replay_sample,
)


def _sample(sample_id: str, **metadata_overrides) -> ReplayRegressionSample:
    metadata = {
        "source_kind": "operator_curated",
        "message_count": 3,
        **metadata_overrides,
    }
    return ReplayRegressionSample(
        sample_id=sample_id,
        source_session_id="session-1",
        prompt_seed_id="seed-1",
        topic="api",
        user_input_excerpt="Please inspect the runtime routing path.",
        expected_outcome_summary="The system should identify the correct routing issue.",
        evidence_refs=["docs/design.md#phase-g1"],
        metadata=metadata,
    )


def test_validate_replay_sample_rejects_unsupported_source_kind() -> None:
    with pytest.raises(ReplayRegressionSampleStoreError):
        validate_replay_sample(_sample("bad-source", source_kind="raw_unfiltered_dump"))


def test_validate_replay_sample_rejects_invalid_message_count() -> None:
    with pytest.raises(ReplayRegressionSampleStoreError):
        validate_replay_sample(_sample("bad-count", message_count=0))


def test_persist_and_load_replay_sample(tmp_path) -> None:
    sample = _sample("sample-1")

    result = persist_replay_regression_sample(sample, store_dir=tmp_path)
    loaded = load_replay_regression_sample("sample-1", store_dir=tmp_path)

    assert result["created"] is True
    assert loaded is not None
    assert loaded.sample_id == "sample-1"
    assert loaded.metadata["source_kind"] == "operator_curated"


def test_list_replay_samples_returns_recent_first(tmp_path) -> None:
    persist_replay_regression_sample(_sample("sample-1"), store_dir=tmp_path)
    persist_replay_regression_sample(_sample("sample-2"), store_dir=tmp_path)

    listed = list_replay_regression_samples(store_dir=tmp_path)

    assert [item.sample_id for item in listed][:2] == ["sample-2", "sample-1"]


def test_ingest_curated_replay_samples_accepts_and_rejects_individually(tmp_path) -> None:
    accepted = _sample("sample-ok")
    rejected = _sample("sample-bad", source_kind="raw_export")

    result = ingest_curated_replay_samples([accepted, rejected], store_dir=tmp_path)

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["accepted_sample_ids"] == ["sample-ok"]
    assert result["rejections"][0]["sample_id"] == "sample-bad"
