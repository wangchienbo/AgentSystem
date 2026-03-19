from __future__ import annotations

from collections.abc import Callable

from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService

SkillHandler = Callable[[SkillExecutionRequest], SkillExecutionResult]


SYSTEM_SKILL_SPECS: dict[str, dict] = {
    "skill.echo": {
        "name": "Demo Echo Skill",
        "immutable_interface": False,
        "version": "1.0.0",
        "content": "demo echo handler",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="C1_optional_runtime",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R0_safe_read",
        ),
        "manifest": SkillManifest(
            skill_id="skill.echo",
            name="Demo Echo Skill",
            version="1.0.0",
            description="Simple deterministic echo skill",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.api.main:_demo_echo_skill"),
            contract=SkillContractRef(),
            tags=["demo", "deterministic"],
        ),
    },
    "system.app_config": {
        "name": "System App Config",
        "immutable_interface": True,
        "version": "1.0.0",
        "content": "system app config handler",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="C2_required_runtime",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R1_local_write",
        ),
        "manifest": SkillManifest(
            skill_id="system.app_config",
            name="System App Config",
            version="1.0.0",
            description="Deterministic per-app configuration access",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.api.main:_system_app_config_skill"),
            contract=SkillContractRef(
                input_schema_ref="schema://system.app_config/input",
                output_schema_ref="schema://system.app_config/output",
                error_schema_ref="schema://system.app_config/error",
            ),
            tags=["system", "config"],
        ),
    },
    "system.state": {
        "name": "System State",
        "immutable_interface": True,
        "version": "1.0.0",
        "content": "system state handler",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="C2_required_runtime",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R1_local_write",
        ),
        "manifest": SkillManifest(
            skill_id="system.state",
            name="System State",
            version="1.0.0",
            description="Deterministic runtime state access",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.api.main:_system_state_skill"),
            contract=SkillContractRef(),
            tags=["system", "state"],
        ),
    },
    "system.audit": {
        "name": "System Audit",
        "immutable_interface": True,
        "version": "1.0.0",
        "content": "system audit handler",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="C2_required_runtime",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R1_local_write",
        ),
        "manifest": SkillManifest(
            skill_id="system.audit",
            name="System Audit",
            version="1.0.0",
            description="Structured audit trail recording",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.api.main:_system_audit_skill"),
            contract=SkillContractRef(),
            tags=["system", "audit"],
        ),
    },
    "system.context": {
        "name": "System Context",
        "immutable_interface": True,
        "version": "1.0.0",
        "content": "system context handler",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="C2_required_runtime",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R1_local_write",
        ),
        "manifest": SkillManifest(
            skill_id="system.context",
            name="System Context",
            version="1.0.0",
            description="Deterministic shared context access",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.api.main:_system_context_skill"),
            contract=SkillContractRef(
                input_schema_ref="schema://system.context/input",
                output_schema_ref="schema://system.context/output",
                error_schema_ref="schema://system.context/error",
            ),
            tags=["system", "context"],
        ),
    },
    "core.skill.control": {
        "name": "Human Skill Control Interface",
        "immutable_interface": True,
        "version": "1.0.0",
        "content": "protected control surface",
        "capability_profile": SkillCapabilityProfile(
            intelligence_level="L0_deterministic",
            network_requirement="N0_none",
            runtime_criticality="build_and_runtime_governance",
            execution_locality="local",
            invocation_default="automatic",
            risk_level="R1_local_write",
        ),
        "manifest": SkillManifest(
            skill_id="core.skill.control",
            name="Human Skill Control Interface",
            version="1.0.0",
            description="Protected control surface for skill lifecycle",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.services.skill_control:SkillControlService"),
            contract=SkillContractRef(),
            tags=["system", "governance"],
        ),
    },
}


def build_registry_entry(skill_id: str) -> SkillRegistryEntry:
    spec = SYSTEM_SKILL_SPECS[skill_id]
    return SkillRegistryEntry(
        skill_id=skill_id,
        name=spec["name"],
        immutable_interface=spec["immutable_interface"],
        active_version=spec["version"],
        versions=[SkillVersion(version=spec["version"], content=spec["content"])],
        dependencies=[],
        capability_profile=spec["capability_profile"],
        runtime_adapter=spec["manifest"].runtime_adapter,
        manifest=spec["manifest"],
    )


def register_builtin_skills(skill_control: SkillControlService) -> None:
    for skill_id in SYSTEM_SKILL_SPECS:
        skill_control.register(build_registry_entry(skill_id))


def register_builtin_handlers(skill_runtime: SkillRuntimeService, handlers: dict[str, SkillHandler], skill_control: SkillControlService) -> None:
    for skill_id, handler in handlers.items():
        entry = skill_control.get_skill(skill_id) if skill_id in SYSTEM_SKILL_SPECS else None
        skill_runtime.register_handler(skill_id, handler, entry=entry)
