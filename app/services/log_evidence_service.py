from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from app.models.log_evidence import (
    DraftSummary,
    EvidencePage,
    PromotedEvidence,
    RawLogRef,
    RetrievalIndexEntry,
    SuspiciousSignal,
)
from app.models.operator_contracts import OperatorPageMeta
from app.services.runtime_state_store import RuntimeStateStore


class LogEvidenceService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store
        self._raw_refs: dict[str, RawLogRef] = {}
        self._drafts: dict[str, DraftSummary] = {}
        self._signals: dict[str, SuspiciousSignal] = {}
        self._evidence: dict[str, PromotedEvidence] = {}
        self._index: dict[str, RetrievalIndexEntry] = {}
        if self._store is not None:
            self._load()

    def ingest_workflow_failure(
        self,
        *,
        app_instance_id: str,
        workflow_id: str,
        failed_step_ids: list[str],
        execution_id: str,
        status: str,
    ) -> SuspiciousSignal | None:
        ref = self._add_raw_ref(
            source_type="workflow_execution",
            source_id=execution_id,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            payload={"failed_step_ids": failed_step_ids, "status": status},
        )
        scope_key = f"workflow:{app_instance_id}:{workflow_id}"
        draft = self._upsert_draft(
            category="workflow_failure",
            scope_key=scope_key,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            summary=f"workflow {workflow_id} has failure activity",
            ref_id=ref.ref_id,
        )
        if draft.event_count < 2:
            return None
        signal = self._upsert_signal(
            category="workflow_failure",
            scope_key=scope_key,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            reason=f"workflow {workflow_id} failed repeatedly",
            severity="high" if draft.event_count >= 3 else "medium",
            supporting_ref_ids=draft.supporting_ref_ids,
            frequency=draft.event_count,
            metadata={"failed_step_ids": failed_step_ids},
        )
        if signal.frequency >= 3:
            self._promote_signal(signal, recommended_action="inspect_workflow_failure")
        self._persist()
        return signal

    def ingest_policy_event(
        self,
        *,
        skill_id: str,
        event_type: str,
        reason: str,
        scope: str,
    ) -> SuspiciousSignal | None:
        ref = self._add_raw_ref(
            source_type="skill_risk_event",
            source_id=f"{skill_id}:{event_type}:{datetime.now(UTC).isoformat()}",
            skill_id=skill_id,
            payload={"event_type": event_type, "reason": reason, "scope": scope},
        )
        scope_key = f"skill:{skill_id}:{scope}"
        draft = self._upsert_draft(
            category="policy_pressure",
            scope_key=scope_key,
            skill_id=skill_id,
            summary=f"skill {skill_id} is under policy pressure",
            ref_id=ref.ref_id,
        )
        if draft.event_count < 2:
            return None
        signal = self._upsert_signal(
            category="policy_pressure",
            scope_key=scope_key,
            skill_id=skill_id,
            reason=f"skill {skill_id} hit repeated policy events",
            severity="high" if draft.event_count >= 3 else "medium",
            supporting_ref_ids=draft.supporting_ref_ids,
            frequency=draft.event_count,
            metadata={"scope": scope, "latest_reason": reason},
        )
        if signal.frequency >= 3:
            self._promote_signal(signal, recommended_action="review_policy_override")
        self._persist()
        return signal

    def ingest_clarify_unresolved(
        self,
        *,
        request_text: str,
        requirement_type: str,
        readiness: str,
        missing_fields: list[str],
    ) -> SuspiciousSignal | None:
        if readiness not in {"needs_clarification", "conflicting_constraints"}:
            return None
        scope_key = f"clarify:{requirement_type}:{'-'.join(sorted(missing_fields)) or 'none'}"
        ref = self._add_raw_ref(
            source_type="requirement_clarify",
            source_id=f"clarify:{datetime.now(UTC).isoformat()}",
            payload={
                "request_text": request_text,
                "requirement_type": requirement_type,
                "readiness": readiness,
                "missing_fields": missing_fields,
            },
        )
        draft = self._upsert_draft(
            category="clarify_unresolved",
            scope_key=scope_key,
            summary=f"requirement intake remained unresolved for {requirement_type}",
            ref_id=ref.ref_id,
        )
        if draft.event_count < 2:
            return None
        signal = self._upsert_signal(
            category="clarify_unresolved",
            scope_key=scope_key,
            reason="similar requirement clarify loops remain unresolved repeatedly",
            severity="medium",
            supporting_ref_ids=draft.supporting_ref_ids,
            frequency=draft.event_count,
            metadata={"missing_fields": missing_fields, "readiness": readiness},
        )
        if signal.frequency >= 3:
            self._promote_signal(signal, recommended_action="improve_requirement_intake")
        self._persist()
        return signal

    def list_drafts(self, limit: int | None = None) -> EvidencePage:
        items = sorted(self._drafts.values(), key=lambda item: item.updated_at, reverse=True)
        return self._page(items, limit=limit)

    def list_signals(self, limit: int | None = None) -> EvidencePage:
        items = sorted(self._signals.values(), key=lambda item: item.last_seen_at, reverse=True)
        return self._page(items, limit=limit)

    def list_promoted_evidence(self, limit: int | None = None) -> EvidencePage:
        items = sorted(self._evidence.values(), key=lambda item: item.created_at, reverse=True)
        return self._page(items, limit=limit)

    def list_index_entries(self, limit: int | None = None, app_instance_id: str | None = None) -> EvidencePage:
        items = sorted(self._index.values(), key=lambda item: item.freshness_ts, reverse=True)
        if app_instance_id is not None:
            items = [item for item in items if item.app_instance_id == app_instance_id]
        return self._page(items, limit=limit)

    def build_context_evidence_summary(self, app_instance_id: str, limit: int = 3) -> dict:
        index_page = self.list_index_entries(limit=limit, app_instance_id=app_instance_id)
        return {
            "count": len(index_page.items),
            "top_items": [
                {
                    "topic": item.topic,
                    "summary": item.short_summary,
                    "priority": item.priority,
                    "scope_key": item.scope_key,
                }
                for item in index_page.items
            ],
        }

    def get_stats_summary(self) -> dict:
        signals = list(self._signals.values())
        evidence = list(self._evidence.values())
        drafts = list(self._drafts.values())
        index_entries = list(self._index.values())
        return {
            "draft_count": len(drafts),
            "signal_count": len(signals),
            "promoted_evidence_count": len(evidence),
            "index_entry_count": len(index_entries),
            "signals_by_category": dict(Counter(item.category for item in signals)),
            "evidence_by_category": dict(Counter(item.category for item in evidence)),
            "latest_signal_at": max((item.last_seen_at for item in signals), default=None),
            "latest_evidence_at": max((item.created_at for item in evidence), default=None),
        }

    def _add_raw_ref(
        self,
        *,
        source_type: str,
        source_id: str,
        app_instance_id: str | None = None,
        workflow_id: str | None = None,
        skill_id: str | None = None,
        payload: dict | None = None,
    ) -> RawLogRef:
        ref = RawLogRef(
            source_type=source_type,
            source_id=source_id,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            skill_id=skill_id,
            payload=payload or {},
        )
        self._raw_refs[ref.ref_id] = ref
        return ref

    def _upsert_draft(
        self,
        *,
        category: str,
        scope_key: str,
        summary: str,
        ref_id: str,
        app_instance_id: str | None = None,
        workflow_id: str | None = None,
        skill_id: str | None = None,
    ) -> DraftSummary:
        key = f"{category}:{scope_key}"
        for item in self._drafts.values():
            if item.category == category and item.scope_key == scope_key:
                if ref_id not in item.supporting_ref_ids:
                    item.supporting_ref_ids.append(ref_id)
                    item.event_count += 1
                item.updated_at = datetime.now(UTC)
                return item
        draft = DraftSummary(
            category=category,
            scope_key=scope_key,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            skill_id=skill_id,
            summary=summary,
            event_count=1,
            supporting_ref_ids=[ref_id],
        )
        self._drafts[draft.draft_id] = draft
        return draft

    def _upsert_signal(
        self,
        *,
        category: str,
        scope_key: str,
        reason: str,
        severity: str,
        supporting_ref_ids: list[str],
        frequency: int,
        app_instance_id: str | None = None,
        workflow_id: str | None = None,
        skill_id: str | None = None,
        metadata: dict | None = None,
    ) -> SuspiciousSignal:
        for item in self._signals.values():
            if item.category == category and item.scope_key == scope_key:
                item.reason = reason
                item.severity = severity
                item.supporting_ref_ids = list(dict.fromkeys(supporting_ref_ids))
                item.frequency = frequency
                item.last_seen_at = datetime.now(UTC)
                item.metadata = metadata or {}
                self._index_signal(item)
                return item
        signal = SuspiciousSignal(
            category=category,
            severity=severity,
            scope_key=scope_key,
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            skill_id=skill_id,
            reason=reason,
            supporting_ref_ids=list(dict.fromkeys(supporting_ref_ids)),
            frequency=frequency,
            metadata=metadata or {},
        )
        self._signals[signal.signal_id] = signal
        self._index_signal(signal)
        return signal

    def _promote_signal(self, signal: SuspiciousSignal, *, recommended_action: str) -> PromotedEvidence:
        signal.status = "promoted"
        for item in self._evidence.values():
            if item.source_signal_id == signal.signal_id:
                self._index_evidence(item)
                return item
        evidence = PromotedEvidence(
            category=signal.category,
            source_signal_id=signal.signal_id,
            scope_key=signal.scope_key,
            app_instance_id=signal.app_instance_id,
            workflow_id=signal.workflow_id,
            skill_id=signal.skill_id,
            summary=signal.reason,
            recommended_action=recommended_action,
            supporting_ref_ids=signal.supporting_ref_ids,
            confidence=0.9 if signal.severity == "high" else 0.8,
        )
        self._evidence[evidence.evidence_id] = evidence
        self._index_evidence(evidence)
        return evidence

    def _index_signal(self, signal: SuspiciousSignal) -> None:
        entry = RetrievalIndexEntry(
            source_type="signal",
            source_id=signal.signal_id,
            topic=signal.category,
            scope_key=signal.scope_key,
            app_instance_id=signal.app_instance_id,
            workflow_id=signal.workflow_id,
            skill_id=signal.skill_id,
            short_summary=signal.reason,
            keywords=[signal.category, signal.scope_key, signal.severity],
            priority=3 if signal.severity == "high" else 2,
        )
        self._index[entry.index_id] = entry

    def _index_evidence(self, evidence: PromotedEvidence) -> None:
        entry = RetrievalIndexEntry(
            source_type="evidence",
            source_id=evidence.evidence_id,
            topic=evidence.category,
            scope_key=evidence.scope_key,
            app_instance_id=evidence.app_instance_id,
            workflow_id=evidence.workflow_id,
            skill_id=evidence.skill_id,
            short_summary=evidence.summary,
            keywords=[evidence.category, evidence.scope_key, evidence.impact_area],
            priority=5,
        )
        self._index[entry.index_id] = entry

    def _page(self, items: list, *, limit: int | None = None) -> EvidencePage:
        filtered = items[:limit] if limit is not None else items
        return EvidencePage(
            items=filtered,
            meta=OperatorPageMeta(
                returned_count=len(filtered),
                total_count=len(items),
                filtered_count=len(items),
                has_more=limit is not None and len(items) > limit,
            ),
        )

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("log_evidence_raw_refs", self._raw_refs)
        self._store.save_mapping("log_evidence_drafts", self._drafts)
        self._store.save_mapping("log_evidence_signals", self._signals)
        self._store.save_mapping("log_evidence_promoted", self._evidence)
        self._store.save_mapping("log_evidence_index", self._index)

    def _load(self) -> None:
        self._raw_refs = {
            key: RawLogRef.model_validate(value)
            for key, value in self._store.load_json("log_evidence_raw_refs", {}).items()
        }
        self._drafts = {
            key: DraftSummary.model_validate(value)
            for key, value in self._store.load_json("log_evidence_drafts", {}).items()
        }
        self._signals = {
            key: SuspiciousSignal.model_validate(value)
            for key, value in self._store.load_json("log_evidence_signals", {}).items()
        }
        self._evidence = {
            key: PromotedEvidence.model_validate(value)
            for key, value in self._store.load_json("log_evidence_promoted", {}).items()
        }
        self._index = {
            key: RetrievalIndexEntry.model_validate(value)
            for key, value in self._store.load_json("log_evidence_index", {}).items()
        }
