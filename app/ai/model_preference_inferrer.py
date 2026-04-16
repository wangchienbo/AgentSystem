"""Auto-infer model_preference for skills based on type/category.

Provides a centralized, configurable mapping from skill type to cost tier.
Used during:
1. Skill creation (when model_preference is not explicitly set)
2. App startup (to ensure all bound skills have a model_preference)
"""

from __future__ import annotations

import re
from typing import Any

# ============================================================
# Configurable type → model_preference mapping
# ============================================================

DEFAULT_TYPE_MODEL_MAP: dict[str, str] = {
    # Domain models / data analysis → cheap (gpt-4o-mini)
    "domain-models": "cheap",
    "data": "cheap",
    "analytics": "cheap",
    "summarizer": "cheap",
    # Services / business logic → balanced (gpt-4.1)
    "services": "balanced",
    "workflow": "balanced",
    "notification": "balanced",
    "translator": "balanced",
    # Control / architecture → strong (gpt-5.4)
    "control": "strong",
    "architect": "strong",
    "orchestrator": "strong",
    "refiner": "strong",
}

# Default when no pattern matches
DEFAULT_FALLBACK_MODEL = "strong"

# ============================================================
# Inference engine
# ============================================================


def infer_model_preference(
    skill_id: str,
    name: str = "",
    tags: list[str] | None = None,
    type_map: dict[str, str] | None = None,
) -> str | None:
    """Infer model_preference from skill_id, name, and tags.

    Priority:
    1. Explicit model_preference (already set) → return as-is
    2. Match skill_id patterns (e.g., "novel-domain-models" → cheap)
    3. Match name patterns
    4. Match tags
    5. Fallback → None (caller decides: use default or skip)

    Returns:
        Cost tier string ("cheap" / "balanced" / "strong") or None if no match.
    """
    mapping = type_map or DEFAULT_TYPE_MODEL_MAP
    text = f"{skill_id} {name} {' '.join(tags or [])}".lower()

    for type_key, model_tier in mapping.items():
        if type_key in text:
            return model_tier

    return None


def ensure_skill_model_preference(
    capability_profile: dict[str, Any] | None,
    skill_id: str,
    name: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Ensure capability_profile has a model_preference.

    If already set (non-None), return unchanged.
    Otherwise, infer from skill_id/name/tags and inject.

    Returns updated capability_profile dict.
    """
    if capability_profile is None:
        capability_profile = {}

    existing = capability_profile.get("model_preference")
    if existing:
        return capability_profile

    inferred = infer_model_preference(skill_id, name, tags)
    if inferred:
        capability_profile["model_preference"] = inferred

    return capability_profile


def validate_app_skills_model_preferences(
    skill_ids: list[str],
    skill_control: Any,
) -> list[dict[str, str]]:
    """Validate and auto-fix model_preference for all skills bound to an App.

    Returns list of skills that were auto-fixed:
        [{"skill_id": "...", "from": None, "to": "cheap"}, ...]
    """
    fixed = []
    for skill_id in skill_ids:
        try:
            entry = skill_control.get_skill(skill_id)
            profile = entry.capability_profile
            current = getattr(profile, "model_preference", None)
            if not current:
                inferred = infer_model_preference(skill_id, getattr(profile, "name", ""))
                if inferred:
                    # Update the skill's capability_profile
                    profile.model_preference = inferred
                    fixed.append({
                        "skill_id": skill_id,
                        "from": None,
                        "to": inferred,
                    })
        except Exception:
            pass
    return fixed
