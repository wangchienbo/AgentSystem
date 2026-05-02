from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app.models.governance_observation import ReplayRegressionSample


REPLAY_SAMPLE_STORE_DIR = Path("/root/project/AgentSystem/data/replay_regression_samples")
ALLOWED_REPLAY_SOURCES = {"accepted_chat", "accepted_regression", "operator_curated", "production_trace_excerpt"}


class ReplayRegressionSampleStoreError(ValueError):
    pass


def _ensure_store_dir(store_dir: Path | None = None) -> Path:
    target = store_dir or REPLAY_SAMPLE_STORE_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sample_path(sample_id: str, store_dir: Path | None = None) -> Path:
    return _ensure_store_dir(store_dir) / f"{sample_id}.json"


def validate_replay_sample(sample: ReplayRegressionSample) -> None:
    source_kind = str(sample.metadata.get("source_kind") or "")
    if source_kind not in ALLOWED_REPLAY_SOURCES:
        raise ReplayRegressionSampleStoreError(f"unsupported source_kind: {source_kind or 'missing'}")
    message_count = int(sample.metadata.get("message_count") or 0)
    if message_count <= 0 or message_count > 20:
        raise ReplayRegressionSampleStoreError("message_count must be between 1 and 20")
    excerpt_length = len(sample.user_input_excerpt) + len(sample.expected_outcome_summary)
    if excerpt_length > 3000:
        raise ReplayRegressionSampleStoreError("combined excerpt payload too large")


def persist_replay_regression_sample(sample: ReplayRegressionSample, *, store_dir: Path | None = None) -> dict[str, object]:
    validate_replay_sample(sample)
    path = _sample_path(sample.sample_id, store_dir)
    created = not path.exists()
    payload = sample.model_dump(mode="json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sample_id": sample.sample_id, "path": str(path), "created": created}


def load_replay_regression_sample(sample_id: str, *, store_dir: Path | None = None) -> ReplayRegressionSample | None:
    path = _sample_path(sample_id, store_dir)
    if not path.exists():
        return None
    return ReplayRegressionSample.model_validate_json(path.read_text(encoding="utf-8"))


def list_replay_regression_samples(*, store_dir: Path | None = None, limit: int = 20) -> list[ReplayRegressionSample]:
    target = _ensure_store_dir(store_dir)
    records: list[ReplayRegressionSample] = []
    for path in target.glob("*.json"):
        records.append(ReplayRegressionSample.model_validate_json(path.read_text(encoding="utf-8")))
    records.sort(key=lambda item: item.created_at, reverse=True)
    return records[:limit]


def ingest_curated_replay_samples(samples: Iterable[ReplayRegressionSample], *, store_dir: Path | None = None) -> dict[str, object]:
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    for sample in samples:
        try:
            persist_replay_regression_sample(sample, store_dir=store_dir)
            accepted.append(sample.sample_id)
        except ReplayRegressionSampleStoreError as exc:
            rejected.append({"sample_id": sample.sample_id, "reason": str(exc)})
    return {
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_sample_ids": accepted,
        "rejections": rejected,
    }
