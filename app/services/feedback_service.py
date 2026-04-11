from __future__ import annotations

from app.models.telemetry import FeedbackRecord
from app.services.runtime_state_store import RuntimeStateStore


class FeedbackService:
    """Dedicated service for submitting, querying, and summarising user feedback."""

    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store
        self._records: dict[str, FeedbackRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def submit_feedback(self, record: FeedbackRecord) -> FeedbackRecord:
        self._records[record.feedback_id] = record
        self._persist()
        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_feedback(
        self,
        *,
        app_id: str | None = None,
        skill_id: str | None = None,
        limit: int = 20,
    ) -> list[FeedbackRecord]:
        items = list(self._records.values())
        if app_id is not None:
            items = [r for r in items if r.scope_type == "app" and r.scope_id == app_id]
        if skill_id is not None:
            items = [r for r in items if r.scope_type == "skill" and r.scope_id == skill_id]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    def get_feedback_summary(self, app_id: str) -> dict:
        items = [r for r in self._records.values() if r.scope_type == "app" and r.scope_id == app_id]
        total = len(items)
        scores = [r.score for r in items if r.score is not None]
        avg_score = sum(scores) / len(scores) if scores else None
        kind_counts: dict[str, int] = {}
        label_counts: dict[str, int] = {}
        for r in items:
            kind_counts[r.feedback_kind] = kind_counts.get(r.feedback_kind, 0) + 1
            for label in r.labels:
                label_counts[label] = label_counts.get(label, 0) + 1
        return {
            "app_id": app_id,
            "total_feedback": total,
            "average_score": round(avg_score, 2) if avg_score is not None else None,
            "score_count": len(scores),
            "kind_distribution": kind_counts,
            "top_labels": dict(sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("feedback_records", self._records)

    def _load(self) -> None:
        if self._store is None:
            return
        raw = self._store.load_json("feedback_records", {})
        self._records = {
            key: FeedbackRecord.model_validate(value)
            for key, value in raw.items()
        }
