from __future__ import annotations

from app.models.meta_app import (
    AppControlSkillManifest,
    AppControlSkillResult,
    SubordinateSkillSuggestion,
)
from app.models.meta_app_skill import MetaAppSkillRequest


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def _infer_subordinate_scopes(app_name: str, goal: str, app_kind: str, complexity: str) -> list[SubordinateSkillSuggestion]:
    """Infer a reasonable initial subordinate skill set based on app metadata."""
    slug = _slug(app_name)
    scopes: list[SubordinateSkillSuggestion] = []

    # Every app gets at least a domain-models subordinate
    scopes.append(SubordinateSkillSuggestion(
        suggested_name=f"{slug}-domain-models",
        scope="domain models and data contracts",
        responsibility="manage app-specific domain models and data structures",
        priority="high",
    ))

    # Complex apps get more decomposition
    if complexity in ("moderate", "complex"):
        scopes.append(SubordinateSkillSuggestion(
            suggested_name=f"{slug}-services",
            scope="business logic and service layer",
            responsibility="manage app-specific service implementations",
            priority="high",
        ))

    if complexity == "complex":
        scopes.append(SubordinateSkillSuggestion(
            suggested_name=f"{slug}-api",
            scope="api surface and external interfaces",
            responsibility="manage app-specific API endpoints and integrations",
            priority="medium",
        ))
        scopes.append(SubordinateSkillSuggestion(
            suggested_name=f"{slug}-tests",
            scope="tests and fixtures",
            responsibility="manage app-specific test suites and fixtures",
            priority="medium",
        ))

    return scopes


def _build_decomposition_plan(app_name: str, complexity: str, scopes: list[SubordinateSkillSuggestion]) -> list[str]:
    """Build a step-by-step decomposition plan."""
    plan = [
        f"1. Generate app control anchor for '{app_name}'",
        f"2. Create {len(scopes)} subordinate skill(s) based on complexity '{complexity}'",
        "3. Register subordinate skills in the app-level registry",
        "4. Establish control boundaries and escalation rules",
    ]
    if complexity == "complex":
        plan.append("5. Plan further recursive decomposition for complex subordinates")
    return plan


class MetaAppBootstrapService:
    """Generic app control skill generator.

    This service acts as a meta-skill: given app metadata, it produces
    an app-level control skill (anchor + manifest + subordinate plan).
    It does NOT handle runtime, blueprint building, or installation.
    """

    def bootstrap(self, request: MetaAppSkillRequest) -> AppControlSkillResult:
        slug = _slug(request.app_name)
        control_skill_id = f"{slug}-control"

        scopes = _infer_subordinate_scopes(
            request.app_name,
            request.goal,
            request.app_kind,
            request.complexity,
        )

        decomposition = _build_decomposition_plan(
            request.app_name,
            request.complexity,
            scopes,
        )

        control_skill = AppControlSkillManifest(
            skill_id=control_skill_id,
            name=f"{request.app_name} Control",
            description=f"App-level control skill for {request.app_name}. Manages app-scoped governance, module decomposition, and subordinate skill lifecycle.",
            version="1.0.0",
            handler_entry=f"skills/generated/{control_skill_id}/handler",
            tags=[slug, "app-control", "generated"],
            capability_profile={
                "intelligence_level": "L1_assisted",
                "network_requirement": "N0_none",
                "runtime_criticality": "C2_required_build",
                "execution_locality": "local",
                "invocation_default": "automatic",
                "risk_level": "R1_local_write",
            },
        )

        governance_notes = [
            "This app control skill is responsible for build-time and evolve-time governance only.",
            "It should NOT be invoked during mature runtime operations.",
            "Subordinate skills should escalate to this control skill for cross-module changes.",
            "The control skill itself is generated and should be reviewed before first use.",
        ]

        return AppControlSkillResult(
            app_name=request.app_name,
            app_slug=slug,
            anchor_file=f"{slug.upper()}_CONTROL.md",
            control_skill=control_skill,
            subordinate_suggestions=scopes,
            decomposition_plan=decomposition,
            governance_notes=governance_notes,
        )
