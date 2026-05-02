from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.governance_observation import (
    EvidenceEnvelope,
    GovernanceEvidenceDigest,
    ObservationRecord,
    ReplayRegressionSample,
)


def test_evidence_envelope_normalizes_refs() -> None:
    envelope = EvidenceEnvelope(
        kind="routing",
        summary="router chose fallback path",
        source="regression-run",
        refs=["  docs/design.md#router  ", "", "docs/testing.md#matrix"],
    )

    assert envelope.refs == ["docs/design.md#router", "docs/testing.md#matrix"]
    assert envelope.grade == "derived"
    assert envelope.confidence == 0.5


def test_observation_record_requires_failure_stage_on_failure() -> None:
    with pytest.raises(ValidationError):
        ObservationRecord(
            observation_id="obs-1",
            topic="api",
            run_id="run-1",
            source="fixed-regression",
            success=False,
        )


def test_observation_record_rejects_failure_stage_on_success() -> None:
    with pytest.raises(ValidationError):
        ObservationRecord(
            observation_id="obs-2",
            topic="api",
            run_id="run-1",
            source="fixed-regression",
            success=True,
            failure_stage="routing",
        )


def test_observation_record_accepts_extended_phase_g1_fields() -> None:
    record = ObservationRecord(
        observation_id="obs-3",
        topic="governance",
        run_id="run-2",
        session_id="sess-1",
        trace_id="trace-1",
        source="nightly-cycle",
        scope="nightly_governance",
        domain="regression_quality",
        subdomain="evidence_governance_risk",
        signal="missing_evidence",
        success=False,
        failure_stage="evidence",
        evidence=[
            EvidenceEnvelope(
                kind="output",
                summary="answer lacked evidence citation",
                source="dashboard",
                refs=["docs/testing.md#suite"],
                grade="excerpt",
                confidence=0.8,
            )
        ],
        tags=["  nightly  ", "nightly", "governance"],
    )

    assert record.scope == "nightly_governance"
    assert record.tags == ["nightly", "governance"]
    assert record.evidence[0].grade == "excerpt"
    assert record.evidence[0].confidence == 0.8


def test_governance_evidence_digest_supports_dominant_fields() -> None:
    digest = GovernanceEvidenceDigest(
        total_observations=2,
        dominant_failure_stage="execution",
        dominant_evidence_kind="tool_selection",
        failure_stage_counts={"execution": 2},
        evidence_kind_counts={"tool_selection": 2},
    )

    assert digest.dominant_failure_stage == "execution"
    assert digest.evidence_kind_counts["tool_selection"] == 2


def test_replay_regression_sample_normalizes_refs() -> None:
    sample = ReplayRegressionSample(
        sample_id="sample-1",
        source_session_id="session-123",
        prompt_seed_id="seed-1",
        topic="api",
        user_input_excerpt="please diagnose the routing result",
        expected_outcome_summary="should identify routing error cleanly",
        evidence_refs=["  logs/run-1  ", "", "docs/testing-detail.md#3.12.1"],
    )

    assert sample.evidence_refs == ["logs/run-1", "docs/testing-detail.md#3.12.1"]
