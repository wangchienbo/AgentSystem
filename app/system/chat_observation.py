from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.governance_observation import GovernanceEvidenceDigest
from app.system.regression_governance_observation import build_governance_evidence_digest, classify_failure_stage, classify_signal


CHAT_OBSERVATION_LOG_DIR = Path("/root/project/AgentSystem/data/chat_observation")


def _classify_topic(message: str) -> str:
    text = message.lower()
    if any(token in message for token in ("接口", "api", "路由", "handler")):
        return "api"
    if any(token in message for token in ("校验", "guard", "schema")):
        return "validation"
    if "验证" in message:
        if any(token in text for token in ("证据", "依据", "确认", "prove", "evidence")):
            return "validation"
        return "live_chat"
    if any(token in message for token in ("日志", "观测", "埋点", "telemetry")):
        return "telemetry"
    if any(token in message for token in ("存储", "数据库", "backend", "读写", "storage")):
        return "storage"
    return "live_chat"


def build_chat_observation_probe(*, request: str, response: str | None, success: bool, latency_ms: int, session_id: str, structured_answer: dict[str, Any] | None = None, error_type: str | None = None) -> dict[str, Any]:
    structured_answer = structured_answer or {}
    self_model = structured_answer.get("self_model") or {}
    answer_mode = str(self_model.get("answer_mode") or ("direct" if success else "verification_required"))
    verification_mode = str(self_model.get("verification_mode") or ("none" if success else "evidence_required"))
    route_selected = self_model.get("route_selected") or structured_answer.get("route_selected")
    tool_name = self_model.get("tool_name") or structured_answer.get("tool_name")
    tool_result = structured_answer.get("tool_result")
    user_feedback = structured_answer.get("user_feedback")
    response_text = str(response or error_type or "")
    fallback_markers = (
        "需要进一步验证",
        "仍需进一步验证",
        "不能直接下结论",
        "建议做轻量验证",
        "请先澄清",
    )
    fallback_like = (not success) or any(marker in response_text for marker in fallback_markers) or answer_mode in {"verification_required", "clarification_required"}
    overreach_risk = answer_mode in {"verification_required", "clarification_required"}
    routing_error = bool(self_model.get("routing_error"))
    tool_error = bool(error_type) or bool(self_model.get("tool_error"))

    probe = {
        "topic": _classify_topic(request),
        "prompt": request[:240],
        "request": request[:240],
        "success": success,
        "latency_ms": latency_ms,
        "response": response_text[:240],
        "answer_mode": answer_mode,
        "verification_mode": verification_mode,
        "fallback_like": fallback_like,
        "overreach_risk": overreach_risk,
        "source": "live_chat_request",
        "scope": "live_chat",
        "session_id": session_id,
        "error_type": error_type,
        "route_selected": route_selected,
        "routing_error": routing_error,
        "tool_name": tool_name,
        "tool_result": tool_result,
        "tool_error": tool_error,
        "user_feedback": user_feedback,
    }
    probe["failure_stage"] = classify_failure_stage(probe)
    probe["signal"] = classify_signal(probe, probe["failure_stage"])
    return probe


def persist_chat_observation(*, probe: dict[str, Any], log_dir: Path | None = None, run_id: str | None = None) -> dict[str, Any]:
    target_dir = log_dir or CHAT_OBSERVATION_LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    observation_run_id = run_id or f"chat-observation-{uuid4().hex[:12]}"
    record = {
        "kind": "probe",
        "run_id": observation_run_id,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **probe,
    }
    out = target_dir / f"{probe.get('session_id') or 'unknown-session'}.jsonl"
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_chat_observation_records(*, session_id: str, log_dir: Path | None = None, limit: int = 20) -> list[dict[str, Any]]:
    target_dir = log_dir or CHAT_OBSERVATION_LOG_DIR
    path = target_dir / f"{session_id}.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    parsed = [json.loads(line) for line in lines]
    return parsed[-limit:]


def build_chat_observation_digest(*, session_id: str, log_dir: Path | None = None, limit: int = 20) -> GovernanceEvidenceDigest:
    records = read_chat_observation_records(session_id=session_id, log_dir=log_dir, limit=limit)
    if not records:
        return GovernanceEvidenceDigest()
    run_detail = {
        "summary": {"run_id": f"live-chat-{session_id}"},
        "probes": records,
    }
    return build_governance_evidence_digest(run_detail)
