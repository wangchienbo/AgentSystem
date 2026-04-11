from __future__ import annotations

import json
from typing import Any

from app.models.meta_app import (
    AppControlSkillManifest,
    AppControlSkillResult,
    SubordinateSkillSuggestion,
)
from app.models.meta_app_skill import MetaAppSkillRequest
from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader, ModelConfigError


class MetaAppModelClientError(Exception):
    pass


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


class MetaAppBootstrapService:
    """Generic app control skill generator powered by LLM.

    This is the LLM-facing layer for app creation/modification:
    1. Accept app description
    2. Call LLM to understand requirements, analyze structure, design control plan
    3. Produce structured app control skill output
    4. Hand off to deterministic layers (skill_factory, installer) for execution
    """

    def __init__(self, loader: ModelConfigLoader | None = None) -> None:
        self._loader = loader or ModelConfigLoader()

    def _is_model_available(self) -> bool:
        try:
            config = self._loader.load()
            self._loader.resolve_api_key(config)
            return True
        except ModelConfigError:
            return False

    def _build_prompt(self, request: MetaAppSkillRequest) -> str:
        scope_hint = json.dumps(request.scope, ensure_ascii=False) if request.scope else "none"
        context_hint = json.dumps(request.context, ensure_ascii=False) if request.context else "none"
        slug = _slug(request.app_name)
        parts = [
            "You are an app architecture designer for AgentSystem.",
            "Given an app description, produce a strict JSON object with these exact keys:",
            "app_slug, anchor_file, control_skill_name, control_skill_description,",
            "subordinate_skills (array of objects with keys: suggested_name, scope, responsibility, priority),",
            "decomposition_plan (array of strings),",
            "governance_notes (array of strings).",
            "Rules:",
            f"1. app_slug must be lowercase-kebab-case derived from app_name, e.g. '{slug}'.",
            f"2. anchor_file must be UPPERCASE slug + '_CONTROL.md', e.g. '{slug.upper()}_CONTROL.md'.",
            f"3. control_skill_name must be '{request.app_name} Control'.",
            "4. control_skill_description must explain this is an app-level control skill for governance, module decomposition, and subordinate lifecycle.",
            f"5. subordinate_skills must include at least one '{slug}-domain-models' for domain models and data contracts.",
            f"6. For complexity 'moderate' or 'complex', add '{slug}-services' for business logic.",
            f"7. For complexity 'complex', also add '{slug}-api' and '{slug}-tests'.",
            "8. decomposition_plan must be a step-by-step list starting with '1. Generate app control anchor' and ending with subordinate registration.",
            "9. governance_notes must state this is build-time/evolve-time only, not a runtime dependency.",
            f"App name: {request.app_name}.",
            f"Goal: {request.goal}.",
            f"Kind: {request.app_kind}.",
            f"Complexity: {request.complexity}.",
            f"Scope: {scope_hint}.",
            f"Context: {context_hint}.",
        ]
        return " ".join(parts)

    def _extract_json(self, response: dict) -> dict:
        text = ""
        output = response.get("output", [])
        for item in output:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    break
            if text:
                break
        if not text:
            raise MetaAppModelClientError("Model response did not contain output_text")
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise MetaAppModelClientError(f"Model output did not contain JSON: {text[:300]}")
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError as error:
            raise MetaAppModelClientError(f"Model output was not valid JSON: {text[start:start+300]}") from error

    def _infer_fallback(self, request: MetaAppSkillRequest) -> AppControlSkillResult:
        """Fallback when model is unavailable: rule-based inference."""
        slug = _slug(request.app_name)
        scopes: list[SubordinateSkillSuggestion] = [
            SubordinateSkillSuggestion(
                suggested_name=f"{slug}-domain-models",
                scope="domain models and data contracts",
                responsibility="manage app-specific domain models and data structures",
                priority="high",
            ),
        ]
        if request.complexity in ("moderate", "complex"):
            scopes.append(SubordinateSkillSuggestion(
                suggested_name=f"{slug}-services",
                scope="business logic and service layer",
                responsibility="manage app-specific service implementations",
                priority="high",
            ))
        if request.complexity == "complex":
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

        return AppControlSkillResult(
            app_name=request.app_name,
            app_slug=slug,
            anchor_file=f"{slug.upper()}_CONTROL.md",
            control_skill=AppControlSkillManifest(
                skill_id=f"{slug}-control",
                name=f"{request.app_name} Control",
                description=f"App-level control skill for {request.app_name}. Manages app-scoped governance, module decomposition, and subordinate skill lifecycle.",
                version="1.0.0",
                handler_entry=f"skills/generated/{slug}-control/handler",
                tags=[slug, "app-control", "generated"],
                capability_profile={
                    "intelligence_level": "L1_assisted",
                    "network_requirement": "N0_none",
                    "runtime_criticality": "C2_required_build",
                    "execution_locality": "local",
                    "invocation_default": "automatic",
                    "risk_level": "R1_local_write",
                },
            ),
            subordinate_suggestions=scopes,
            decomposition_plan=[
                f"1. Generate app control anchor for '{request.app_name}'",
                f"2. Create {len(scopes)} subordinate skill(s) based on complexity '{request.complexity}'",
                "3. Register subordinate skills in the app-level registry",
                "4. Establish control boundaries and escalation rules",
            ] + (["5. Plan further recursive decomposition for complex subordinates"] if request.complexity == "complex" else []),
            governance_notes=[
                "This app control skill is responsible for build-time and evolve-time governance only.",
                "It should NOT be invoked during mature runtime operations.",
            ],
        )

    def bootstrap(self, request: MetaAppSkillRequest) -> AppControlSkillResult:
        """Generate app control skill plan. Uses LLM when available, falls back to rule-based inference."""
        if not self._is_model_available():
            return self._infer_fallback(request)

        config = self._loader.load()
        api_key = self._loader.resolve_api_key(config)
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        prompt = self._build_prompt(request)
        response = client.probe(prompt)
        payload = self._extract_json(response)

        slug = payload.get("app_slug", _slug(request.app_name))
        control_skill_id = f"{slug}-control"

        subordinate_items = payload.get("subordinate_skills", [])
        subordinates = [
            SubordinateSkillSuggestion(
                suggested_name=item.get("suggested_name", f"{slug}-unknown"),
                scope=item.get("scope", ""),
                responsibility=item.get("responsibility", ""),
                priority=item.get("priority", "medium"),
            )
            for item in subordinate_items
        ]

        decomposition = payload.get("decomposition_plan", [])
        governance = payload.get("governance_notes", [])

        return AppControlSkillResult(
            app_name=request.app_name,
            app_slug=slug,
            anchor_file=payload.get("anchor_file", f"{slug.upper()}_CONTROL.md"),
            control_skill=AppControlSkillManifest(
                skill_id=control_skill_id,
                name=payload.get("control_skill_name", f"{request.app_name} Control"),
                description=payload.get("control_skill_description", f"App-level control skill for {request.app_name}."),
                version="1.0.0",
                handler_entry=f"skills/generated/{control_skill_id}/handler",
                tags=[slug, "app-control", "generated"],
                capability_profile={
                    "intelligence_level": "L1_assisted",
                    "network_requirement": "N2_required",
                    "runtime_criticality": "C2_required_build",
                    "execution_locality": "local",
                    "invocation_default": "automatic",
                    "risk_level": "R1_local_write",
                },
            ),
            subordinate_suggestions=subordinates,
            decomposition_plan=decomposition,
            governance_notes=governance,
        )
