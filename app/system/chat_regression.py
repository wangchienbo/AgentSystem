from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


FIXED_PROMPT_MATRIX: dict[str, str] = {
    "api": "请梳理 API handler 和 request/response 流程",
    "validation": "请检查校验器和 guard 规则",
    "telemetry": "请检查日志埋点和观测记录",
    "storage": "请检查 storage backend 和读写路径",
}


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
