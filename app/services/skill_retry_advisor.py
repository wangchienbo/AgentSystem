from __future__ import annotations

from app.models.skill_diagnostics import SkillDiagnostic, SkillRetryAdviceResponse


class SkillRetryAdvisorService:
    def build_retry_advice(self, diagnostic: SkillDiagnostic) -> SkillRetryAdviceResponse:
        suggested = dict(diagnostic.suggested_retry_request)
        rationale = diagnostic.hint or diagnostic.message

        if not suggested and diagnostic.kind == "invalid_request":
            details = diagnostic.details
            suggested = {
                "skill_id": details.get("skill_id", "skill.generated.retry"),
                "adapter_kind": details.get("adapter_kind", "script"),
            }
            if details.get("adapter_kind") == "script":
                suggested["command"] = ["python3", "path/to/generated_skill.py"]
            rationale = "Retry by filling the missing required request fields."

        if not suggested and diagnostic.kind == "callable_generation_error":
            details = diagnostic.details
            suggested = {
                "skill_id": details.get("skill_id", "skill.generated.retry"),
                "adapter_kind": "callable",
                "generation_operation": "normalize_object_keys",
            }
            rationale = "Retry with a supported callable generation operation."

        if not suggested and diagnostic.kind in {"install_error", "contract_violation", "execution_error"}:
            details = diagnostic.details
            failed_step = details.get("failed_step", {})
            suggested = {
                "workflow_id": details.get("workflow_id", "wf.generated"),
                "app_instance_id": details.get("app_instance_id", "generated-app"),
                "step_inputs": {
                    failed_step.get("step_id", "skill.1"): {
                        "text": "replace-with-valid-input"
                    }
                },
            }
            rationale = "Retry by correcting step inputs so they satisfy the generated skill contract."

        return SkillRetryAdviceResponse(
            retryable=diagnostic.retryable or bool(suggested),
            suggested_request=suggested,
            rationale=rationale,
        )
