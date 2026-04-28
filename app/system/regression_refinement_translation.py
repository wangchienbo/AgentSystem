from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.models.refinement_loop import RefinementHypothesis, RolloutQueueItem, VerificationResult
from app.services.refinement_memory import RefinementMemoryStore
from app.system.regression_governance_policy import classify_signal_domain

APP_INSTANCE_ID = "agent_system"


def build_refinement_payload_from_trigger(trigger: dict[str, Any]) -> dict[str, str]:
    signal = trigger["signal"]
    domain = trigger.get("domain") or classify_signal_domain(signal)
    action = trigger["recommended_action"]
    detail = trigger["detail"]
    level = trigger["level"]

    if domain == "automation_control_plane":
        return {
            "contradiction": f"automation_control_plane: {signal}",
            "hypothesis": f"Stabilize automation control plane via {action}",
            "expected_change": f"Reduce nightly automation instability: {detail}",
            "novelty_note": "Automation control-plane risk should follow a recovery/stability path, not a prompt-quality path.",
            "queue_note": f"automation_control_plane::{action}",
            "verification_summary": f"Automation control-plane attention recorded for {signal}",
            "verification_outcome": "failed" if level == "warning" else "inconclusive",
        }
    return {
        "contradiction": f"regression_quality: {signal}",
        "hypothesis": f"Address regression quality signal {signal} through {action}",
        "expected_change": detail,
        "novelty_note": "Regression-quality risk should remain in the model/tool/evidence refinement lane.",
        "queue_note": f"regression_quality::{action}",
        "verification_summary": detail,
        "verification_outcome": "failed" if level == "warning" else "inconclusive",
    }


def persist_trigger_payloads(
    memory: RefinementMemoryStore,
    triggers: list[dict[str, Any]],
) -> dict[str, Any]:
    created_hypotheses = []
    created_queue_items = []
    created_verifications = []

    for trigger in triggers:
        signal = trigger["signal"]
        payload = build_refinement_payload_from_trigger(trigger)
        hypothesis = memory.add_hypothesis(
            RefinementHypothesis(
                hypothesis_id=f"reg-hyp-{uuid4().hex[:12]}",
                app_instance_id=APP_INSTANCE_ID,
                proposal_id=trigger["trigger_id"],
                experience_id=trigger["trigger_id"],
                contradiction=payload["contradiction"],
                hypothesis=payload["hypothesis"],
                expected_change=payload["expected_change"],
                evidence=[trigger["detail"]],
                repeat_risk="medium" if trigger["level"] == "warning" else "low",
                novelty_note=payload["novelty_note"],
            )
        )
        verification = memory.add_verification(
            VerificationResult(
                verification_id=f"reg-ver-{uuid4().hex[:12]}",
                hypothesis_id=hypothesis.hypothesis_id,
                app_instance_id=APP_INSTANCE_ID,
                outcome=payload["verification_outcome"],
                summary=payload["verification_summary"],
                failed_checks=[signal] if trigger["level"] == "warning" else [],
                execution_reference=trigger["trigger_id"],
                failure_aware=True,
                gating_reason=trigger["recommended_action"],
            )
        )
        queue_item = memory.add_queue_item(
            RolloutQueueItem(
                queue_id=f"reg-queue-{uuid4().hex[:12]}",
                hypothesis_id=hypothesis.hypothesis_id,
                proposal_id=trigger["trigger_id"],
                app_instance_id=APP_INSTANCE_ID,
                status="queued",
                note=payload["queue_note"],
            )
        )
        created_hypotheses.append(hypothesis.model_dump(mode="json"))
        created_verifications.append(verification.model_dump(mode="json"))
        created_queue_items.append(queue_item.model_dump(mode="json"))

    return {
        "trigger_count": len(triggers),
        "created_hypotheses": created_hypotheses,
        "created_verifications": created_verifications,
        "created_queue_items": created_queue_items,
    }
