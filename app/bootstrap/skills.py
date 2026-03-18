from __future__ import annotations

from app.models.app_config import AppConfigRequest
from app.models.context_skill import ContextSkillRequest
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.system_skill import SystemAuditRequest, SystemStateRequest
from app.services.skill_runtime import SkillRuntimeService
from app.services.system_skill_registry import register_builtin_handlers, register_builtin_skills


def build_builtin_skill_handlers(services: dict[str, object]) -> dict[str, callable]:
    app_config_service = services["app_config_service"]
    system_state_service = services["system_state_service"]
    system_audit_service = services["system_audit_service"]
    context_skill_service = services["context_skill_service"]

    def demo_echo_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        payload = request.config.get("payload", request.inputs)
        return SkillExecutionResult(
            skill_id=request.skill_id,
            status="completed",
            output={"echo": payload, "inputs": request.inputs, "step_id": request.step_id},
        )

    def system_app_config_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        config_request = AppConfigRequest(**request.inputs)
        result = app_config_service.execute(request.app_instance_id, config_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_state_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        state_request = SystemStateRequest(**request.inputs)
        result = system_state_service.execute(request.app_instance_id, state_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_audit_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        audit_request = SystemAuditRequest(**request.inputs)
        result = system_audit_service.record(request.app_instance_id, audit_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_context_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        context_request = ContextSkillRequest(**request.inputs)
        result = context_skill_service.execute(request.app_instance_id, context_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result)

    return {
        "skill.echo": demo_echo_skill,
        "system.app_config": system_app_config_skill,
        "system.state": system_state_skill,
        "system.audit": system_audit_skill,
        "system.context": system_context_skill,
    }


def bootstrap_builtin_skills(skill_runtime: SkillRuntimeService, services: dict[str, object]) -> None:
    skill_control = services["skill_control"]
    register_builtin_skills(skill_control)
    register_builtin_handlers(skill_runtime, build_builtin_skill_handlers(services), skill_control)
