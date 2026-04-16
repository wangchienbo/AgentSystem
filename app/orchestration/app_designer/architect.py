"""App architect — designs app architecture with skill composition awareness.

Key difference from old meta_app bootstrap:
- Injects existing skill registry into prompt
- LLM prioritizes reusing existing skills over creating new ones
- Uses strong model for complex design decisions
"""
from __future__ import annotations

import json
from typing import Any

from app.models.app_design import AppDesignResult, AppIntentResult, SubordinateSkillDesign
from app.services.model_router import ModelRouter


class AppArchitectError(ValueError):
    pass


class AppArchitect:
    """App architecture designer with skill composition awareness.

    Given a structured intent and the existing skill registry,
    designs the app architecture prioritizing reuse of existing skills.
    """

    SYSTEM_PROMPT = (
        "You are an App Architecture Designer for AgentSystem. "
        "Your job is to design app architectures by COMPOSING existing skills "
        "and creating new ones only when necessary.\n\n"
        "Output format (strict JSON):\n"
        "{\n"
        '  "app_name": "app name",\n'
        '  "app_slug": "lowercase-kebab-case",\n'
        '  "control_skill_name": "App Control",\n'
        '  "control_skill_description": "description of the control skill",\n'
        '  "subordinate_skills": [\n'
        '    {"suggested_name": "skill-id", "scope": "what it handles", "responsibility": "what it does", "priority": "high|medium|low", "reuse_existing": "existing-skill-id or null"},\n'
        '    ...\n'
        '  ],\n'
        '  "reused_skills": ["skill-id-1", ...],\n'
        '  "new_skills": ["skill-id-2", ...],\n'
        '  "decomposition_plan": ["step 1", "step 2", ...],\n'
        '  "governance_notes": ["note 1", ...],\n'
        '  "design_notes": "brief explanation of design choices"\n'
        "}\n\n"
        "RULES:\n"
        "1. ALWAYS check existing skills first — reuse whenever possible\n"
        "2. Only create new skills when existing ones don't cover the need\n"
        "3. Every app needs at least a control skill\n"
        "4. Control skill handles governance, module decomposition, and lifecycle\n"
        "5. Set reuse_existing to the skill ID if reusing, null if creating new\n"
        "6. app_slug must be lowercase-kebab-case\n"
        "7. Only return JSON, no other text."
    )

    def __init__(
        self,
        model_router: ModelRouter,
        skill_registry: Any = None,
    ) -> None:
        self._router = model_router
        self._skill_registry = skill_registry

    def design(self, intent: AppIntentResult) -> AppDesignResult:
        """Design app architecture based on intent and existing skills.

        Args:
            intent: Structured app creation intent

        Returns:
            AppDesignResult with architecture plan
        """
        client = self._router.get_client("architect", intent.complexity)

        # Gather existing skills
        existing_skills = self._gather_existing_skills()

        # Build prompt with skill registry
        prompt = self._build_prompt(intent, existing_skills)

        try:
            response, _usage = client.generate_response(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=prompt,
                max_tokens=4096,
                temperature=0.5,
            )
            return self._parse_response(response)
        except Exception as exc:
            raise AppArchitectError(f"Architecture design failed: {exc}")

    def _gather_existing_skills(self) -> list[dict[str, str]]:
        """Gather existing skills from registry."""
        if not self._skill_registry:
            return []

        skills: list[dict[str, str]] = []
        try:
            # Try different registry access patterns
            if hasattr(self._skill_registry, '_handlers'):
                for skill_id, handler in self._skill_registry._handlers.items():
                    skills.append({
                        "id": skill_id,
                        "name": getattr(handler, '__name__', skill_id),
                        "capability": "callable handler",
                    })
            if hasattr(self._skill_registry, '_entries'):
                for skill_id, entry in self._skill_registry._entries.items():
                    if not any(s["id"] == skill_id for s in skills):
                        skills.append({
                            "id": skill_id,
                            "name": entry.name,
                            "capability": entry.capability_profile.intelligence_level if hasattr(entry, 'capability_profile') else "unknown",
                        })
        except Exception:
            pass

        # Also try skill_control service
        try:
            if hasattr(self._skill_registry, 'list_skills'):
                registered = self._skill_registry.list_skills()
                if isinstance(registered, list):
                    for item in registered:
                        skill_id = item.get("id") or item.get("skill_id") if isinstance(item, dict) else None
                        if skill_id and not any(s["id"] == skill_id for s in skills):
                            skills.append({
                                "id": skill_id,
                                "name": item.get("name", skill_id) if isinstance(item, dict) else skill_id,
                                "capability": item.get("capability", "unknown") if isinstance(item, dict) else "unknown",
                            })
        except Exception:
            pass

        return skills

    def _build_prompt(self, intent: AppIntentResult, existing_skills: list[dict[str, str]]) -> str:
        """Build design prompt with existing skill context."""
        parts = [
            f"Design an app with the following requirements:\n",
            f"- Name: {intent.app_name}",
            f"- Goal: {intent.goal}",
            f"- Kind: {intent.kind}",
            f"- Complexity: {intent.complexity}",
        ]

        if intent.constraints:
            parts.append(f"- Constraints: {', '.join(intent.constraints)}")

        # Inject existing skills
        if existing_skills:
            skills_json = json.dumps(existing_skills, ensure_ascii=False, indent=2)
            parts.append(f"\n## Existing Skill Library (PRIORITIZE REUSE!)\n{skills_json}")
        else:
            parts.append("\n## Existing Skill Library\n(No existing skills found — design from scratch)")

        return "\n".join(parts)

    def _parse_response(self, response: str) -> AppDesignResult:
        """Parse LLM response into AppDesignResult."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise AppArchitectError(f"No JSON found in response: {text[:200]}")

        data = json.loads(text[start:end + 1])

        subordinates = []
        for item in data.get("subordinate_skills", []):
            subordinates.append(SubordinateSkillDesign(
                suggested_name=item.get("suggested_name", "unknown"),
                scope=item.get("scope", ""),
                responsibility=item.get("responsibility", ""),
                priority=item.get("priority", "medium"),
                reuse_existing=item.get("reuse_existing"),
            ))

        return AppDesignResult(
            app_name=data.get("app_name", ""),
            app_slug=data.get("app_slug", ""),
            control_skill_name=data.get("control_skill_name", ""),
            control_skill_description=data.get("control_skill_description", ""),
            subordinate_skills=subordinates,
            reused_skills=data.get("reused_skills", []),
            new_skills=data.get("new_skills", []),
            decomposition_plan=data.get("decomposition_plan", []),
            governance_notes=data.get("governance_notes", []),
            design_notes=data.get("design_notes", ""),
        )
