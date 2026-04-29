from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from app.services.refinement_memory import RefinementMemoryStore
from uuid import uuid4


FIXED_PROMPT_MATRIX: dict[str, str] = {
    "api": "请梳理 API handler 和 request/response 流程",
    "validation": "请检查校验器和 guard 规则",
    "telemetry": "请检查日志埋点和观测记录",
    "storage": "请检查 storage backend 和读写路径",
}

REGRESSION_LOG_DIR = Path("/root/project/AgentSystem/data/chat_regression")


@dataclass
class RegressionProbeResult:
    topic: str
    prompt: str
    success: bool
    latency_ms: int
    response: str
    answer_mode: str
    verification_mode: str
    fallback_like: bool
    overreach_risk: bool


@dataclass
class RegressionRunSummary:
    run_id: str
    started_at: str
    topic_count: int
    success_count: int
    avg_latency_ms: int
    fallback_count: int
    overreach_risk_count: int
    answer_mode_counts: dict[str, int]
    verification_mode_counts: dict[str, int]


def summarize_probe_payload(topic: str, payload: dict[str, Any]) -> RegressionProbeResult:
    structured = payload.get("structured_answer") or {}
    self_model = structured.get("self_model") or {}
    response = str(payload.get("response") or "")
    answer_mode = str(self_model.get("answer_mode") or "direct")
    verification_mode = str(self_model.get("verification_mode") or "none")
    latency_ms = int(payload.get("latency_ms") or 0)

    fallback_markers = (
        "[Reached max turns",
        "需要进一步验证",
        "仍需进一步验证",
        "建议做轻量验证",
        "当前还不能直接下结论",
    )
    fallback_like = any(marker in response for marker in fallback_markers) or answer_mode in {"verification_required", "clarification_required"}
    overreach_risk = answer_mode in {"verification_required", "clarification_required"}

    return RegressionProbeResult(
        topic=topic,
        prompt=FIXED_PROMPT_MATRIX[topic],
        success=bool(payload.get("success")),
        latency_ms=latency_ms,
        response=response,
        answer_mode=answer_mode,
        verification_mode=verification_mode,
        fallback_like=fallback_like,
        overreach_risk=overreach_risk,
    )


def run_fixed_prompt_matrix(
    post_json: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    path: str = "/api/chat",
) -> list[RegressionProbeResult]:
    results: list[RegressionProbeResult] = []
    for topic, prompt in FIXED_PROMPT_MATRIX.items():
        payload = post_json(path, {"message": prompt})
        results.append(summarize_probe_payload(topic, payload))
    return results


def make_testclient_poster(client: Any) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = client.post(path, json=payload)
        return dict(response.json())

    return _post


def build_run_summary(results: list[RegressionProbeResult], *, run_id: str | None = None, started_at: str | None = None) -> RegressionRunSummary:
    rid = run_id or f"chat-regression-{uuid4().hex[:12]}"
    ts = started_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    answer_mode_counts: dict[str, int] = {}
    verification_mode_counts: dict[str, int] = {}
    for item in results:
        answer_mode_counts[item.answer_mode] = answer_mode_counts.get(item.answer_mode, 0) + 1
        verification_mode_counts[item.verification_mode] = verification_mode_counts.get(item.verification_mode, 0) + 1
    avg_latency_ms = int(sum(item.latency_ms for item in results) / len(results)) if results else 0
    return RegressionRunSummary(
        run_id=rid,
        started_at=ts,
        topic_count=len(results),
        success_count=sum(1 for item in results if item.success),
        avg_latency_ms=avg_latency_ms,
        fallback_count=sum(1 for item in results if item.fallback_like),
        overreach_risk_count=sum(1 for item in results if item.overreach_risk),
        answer_mode_counts=answer_mode_counts,
        verification_mode_counts=verification_mode_counts,
    )


def persist_run_results(results: list[RegressionProbeResult], summary: RegressionRunSummary, *, log_dir: Path | None = None) -> Path:
    target_dir = log_dir or REGRESSION_LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{summary.run_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "summary", **asdict(summary)}, ensure_ascii=False) + "\n")
        for item in results:
            f.write(json.dumps({"kind": "probe", "run_id": summary.run_id, **asdict(item)}, ensure_ascii=False) + "\n")
    return out


def list_saved_runs(*, log_dir: Path | None = None, limit: int = 10) -> list[dict[str, Any]]:
    target_dir = log_dir or REGRESSION_LOG_DIR
    if not target_dir.exists():
        return []
    files = sorted(target_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    rows: list[dict[str, Any]] = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        summary = json.loads(lines[0])
        rows.append({"path": str(path), "summary": summary})
    return rows


def read_run_details(run_id: str, *, log_dir: Path | None = None) -> dict[str, Any] | None:
    target_dir = log_dir or REGRESSION_LOG_DIR
    path = target_dir / f"{run_id}.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    parsed = [json.loads(line) for line in lines]
    summary = parsed[0]
    probes = parsed[1:]
    return {"path": str(path), "summary": summary, "probes": probes}


def build_multi_run_comparison(*, log_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    runs = list_saved_runs(log_dir=log_dir, limit=limit)
    summaries = [row.get("summary", {}) for row in runs]
    if not summaries:
        return {
            "run_count": 0,
            "avg_latency_ms": 0,
            "avg_fallback_count": 0,
            "avg_overreach_risk_count": 0,
            "answer_mode_totals": {},
            "verification_mode_totals": {},
            "runs": [],
        }

    answer_mode_totals: dict[str, int] = {}
    verification_mode_totals: dict[str, int] = {}
    for summary in summaries:
        for key, value in (summary.get("answer_mode_counts") or {}).items():
            answer_mode_totals[key] = answer_mode_totals.get(key, 0) + int(value)
        for key, value in (summary.get("verification_mode_counts") or {}).items():
            verification_mode_totals[key] = verification_mode_totals.get(key, 0) + int(value)

    return {
        "run_count": len(summaries),
        "avg_latency_ms": int(sum(int(s.get("avg_latency_ms", 0)) for s in summaries) / len(summaries)),
        "avg_fallback_count": sum(int(s.get("fallback_count", 0)) for s in summaries) / len(summaries),
        "avg_overreach_risk_count": sum(int(s.get("overreach_risk_count", 0)) for s in summaries) / len(summaries),
        "answer_mode_totals": answer_mode_totals,
        "verification_mode_totals": verification_mode_totals,
        "runs": runs,
    }


def build_topic_trends(*, log_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    """Build per-topic trend data across multiple saved regression runs.

    Reads recent runs and extracts each topic's probe across runs,
    producing per-topic latency/fallback/overreach/mode trends.
    """
    from collections import defaultdict

    runs = list_saved_runs(log_dir=log_dir, limit=limit)
    run_ids = [row["summary"]["run_id"] for row in runs]

    # Collect per-topic probe data across runs
    topics_data: dict[str, list[dict]] = defaultdict(list)
    for run_id in run_ids:
        detail = read_run_details(run_id, log_dir=log_dir)
        if detail is None:
            continue
        for probe in detail.get("probes", []):
            topic = probe.get("topic", "")
            if topic:
                topics_data[topic].append({
                    "run_id": run_id,
                    **probe,
                })

    if not topics_data:
        return {"topics": {}, "run_count": 0}

    # Compute per-topic trends
    trend_result: dict[str, Any] = {}
    for topic, data_points in sorted(topics_data.items()):
        latencies = [p.get("latency_ms", 0) for p in data_points]
        fallbacks = [1 if p.get("fallback_like") else 0 for p in data_points]
        overreaches = [1 if p.get("overreach_risk") else 0 for p in data_points]
        answer_modes: dict[str, int] = {}
        verification_modes: dict[str, int] = {}
        for p in data_points:
            am = p.get("answer_mode", "unknown")
            vm = p.get("verification_mode", "unknown")
            answer_modes[am] = answer_modes.get(am, 0) + 1
            verification_modes[vm] = verification_modes.get(vm, 0) + 1

        trend_result[topic] = {
            "run_count": len(data_points),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "avg_fallback": sum(fallbacks) / len(fallbacks) if fallbacks else 0.0,
            "avg_overreach": sum(overreaches) / len(overreaches) if overreaches else 0.0,
            "answer_mode_counts": answer_modes,
            "verification_mode_counts": verification_modes,
            "data_points": data_points,
        }

    return {"topics": trend_result, "run_count": len(run_ids)}


def run_regression_governance_cycle(
    post_json: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    persist_results_fn: Callable[[list[RegressionProbeResult], RegressionRunSummary], Path] = persist_run_results,
    promote_evidence_fn: Callable[..., dict[str, Any]] | None = None,
    apply_triggers_fn: Callable[..., dict[str, Any]] | None = None,
    memory: RefinementMemoryStore | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute a full one-shot regression governance cycle.

    Runs the fixed prompt matrix, persists the run, promotes evidence, and optionally
    writes regression triggers into refinement memory.
    """
    from app.system.regression_evidence_bridge import promote_regression_evidence
    from app.system.regression_dashboard import apply_regression_triggers_to_refinement

    promote_evidence_fn = promote_evidence_fn or promote_regression_evidence
    apply_triggers_fn = apply_triggers_fn or apply_regression_triggers_to_refinement

    results = run_fixed_prompt_matrix(post_json)
    summary = build_run_summary(results)
    out = persist_results_fn(results, summary)
    evidence_result = promote_evidence_fn(comparison=build_multi_run_comparison(limit=5))
    trigger_result = {"trigger_count": 0, "created_hypotheses": [], "created_verifications": [], "created_queue_items": []}
    if memory is not None:
        if session_id is not None:
            try:
                trigger_result = apply_triggers_fn(memory, replay_session_id=session_id)
            except TypeError:
                trigger_result = apply_triggers_fn(memory)
        else:
            trigger_result = apply_triggers_fn(memory)

    return {
        "run_id": summary.run_id,
        "summary": summary.__dict__,
        "path": str(out),
        "evidence": evidence_result,
        "trigger_application": trigger_result,
    }
