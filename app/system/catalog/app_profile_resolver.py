from __future__ import annotations

from app.models.app_profile import AppRuntimeProfile
from app.services.skill_control import SkillControlError, SkillControlService


_INTELLIGENCE_ORDER = {
    "L0_deterministic": 0,
    "L1_assisted": 1,
    "L2_semantic": 2,
    "L3_autonomous": 3,
}
_NETWORK_ORDER = {
    "N0_none": 0,
    "N1_optional": 1,
    "N2_required": 2,
}
_INVOCATION_ORDER = {
    "automatic": 0,
    "ask_user": 1,
    "explicit_only": 2,
}


class AppProfileResolverService:
    def __init__(self, skill_control: SkillControlService) -> None:
        self._skill_control = skill_control

    def resolve(self, skill_ids: list[str]) -> AppRuntimeProfile:
        runtime_skills = []
        intelligence = "L0_deterministic"
        network = "N0_none"
        invocation = "automatic"
        offline_capable = True
        direct_start_supported = True

        for skill_id in skill_ids:
            try:
                entry = self._skill_control.get_skill(skill_id)
            except SkillControlError:
                continue
            profile = entry.capability_profile
            if profile.runtime_criticality == "C0_build_only":
                continue
            runtime_skills.append(skill_id)
            if _INTELLIGENCE_ORDER[profile.intelligence_level] > _INTELLIGENCE_ORDER[intelligence]:
                intelligence = profile.intelligence_level
            if _NETWORK_ORDER[profile.network_requirement] > _NETWORK_ORDER[network]:
                network = profile.network_requirement
            if _INVOCATION_ORDER[profile.invocation_default] > _INVOCATION_ORDER[invocation]:
                invocation = profile.invocation_default
            if profile.network_requirement == "N2_required" or profile.execution_locality == "remote":
                offline_capable = False
            if profile.intelligence_level in {"L2_semantic", "L3_autonomous"} and profile.runtime_criticality == "C2_required_runtime":
                direct_start_supported = False

        return AppRuntimeProfile(
            runtime_intelligence_level=intelligence,
            runtime_network_requirement=network,
            offline_capable=offline_capable,
            direct_start_supported=direct_start_supported,
            invocation_posture=invocation,
            runtime_skills=runtime_skills,
        )
