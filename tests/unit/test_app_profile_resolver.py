from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.skill_control import SkillControlService


def register_skill(service: SkillControlService, skill_id: str, *, intelligence: str, network: str, criticality: str, locality: str, invocation: str) -> None:
    service.register(
        SkillRegistryEntry(
            skill_id=skill_id,
            name=skill_id,
            active_version="1.0.0",
            versions=[SkillVersion(version="1.0.0", content=skill_id)],
            dependencies=[],
            capability_profile=SkillCapabilityProfile(
                intelligence_level=intelligence,
                network_requirement=network,
                runtime_criticality=criticality,
                execution_locality=locality,
                invocation_default=invocation,
                risk_level="R0_safe_read",
            ),
            runtime_adapter="callable",
        )
    )


def test_app_profile_resolver_ignores_build_only_skill_for_runtime_posture() -> None:
    service = SkillControlService()
    register_skill(service, "system.app_config", intelligence="L0_deterministic", network="N0_none", criticality="C2_required_runtime", locality="local", invocation="automatic")
    register_skill(service, "builder.plan", intelligence="L3_autonomous", network="N2_required", criticality="C0_build_only", locality="remote", invocation="explicit_only")

    resolver = AppProfileResolverService(skill_control=service)
    profile = resolver.resolve(["system.app_config", "builder.plan"])

    assert profile.runtime_intelligence_level == "L0_deterministic"
    assert profile.runtime_network_requirement == "N0_none"
    assert profile.offline_capable is True
    assert profile.direct_start_supported is True


def test_app_profile_resolver_ignores_unregistered_skills_for_backward_compatibility() -> None:
    service = SkillControlService()
    register_skill(service, "system.app_config", intelligence="L0_deterministic", network="N0_none", criticality="C2_required_runtime", locality="local", invocation="automatic")

    resolver = AppProfileResolverService(skill_control=service)
    profile = resolver.resolve(["system.app_config", "requirement.clarify"])

    assert profile.runtime_intelligence_level == "L0_deterministic"
    assert profile.runtime_network_requirement == "N0_none"
    assert profile.offline_capable is True


def test_app_profile_resolver_detects_required_network_and_intelligence() -> None:
    service = SkillControlService()
    register_skill(service, "system.app_config", intelligence="L0_deterministic", network="N0_none", criticality="C2_required_runtime", locality="local", invocation="automatic")
    register_skill(service, "semantic.review", intelligence="L2_semantic", network="N2_required", criticality="C2_required_runtime", locality="remote", invocation="ask_user")

    resolver = AppProfileResolverService(skill_control=service)
    profile = resolver.resolve(["system.app_config", "semantic.review"])

    assert profile.runtime_intelligence_level == "L2_semantic"
    assert profile.runtime_network_requirement == "N2_required"
    assert profile.offline_capable is False
    assert profile.direct_start_supported is False
    assert profile.invocation_posture == "ask_user"
