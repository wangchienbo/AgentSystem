"""Memory Skill — cross-session user memory and context persistence.

Provides the Interactive App with persistent user memory across sessions:
- User profiles and preferences
- Conversation history summaries
- Feedback and correction tracking
- App usage patterns
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MemorySkillError(ValueError):
    pass


class UserProfile:
    """Per-user persistent profile."""

    def __init__(
        self,
        user_id: str,
        created_at: str | None = None,
        preferences: dict[str, Any] | None = None,
        feedback_history: list[dict[str, Any]] | None = None,
        app_usage: dict[str, Any] | None = None,
        context_summary: str = "",
    ) -> None:
        self.user_id = user_id
        self.created_at = created_at or datetime.now(UTC).isoformat()
        self.preferences = preferences or {}
        self.feedback_history = feedback_history or []
        self.app_usage = app_usage or {}
        self.context_summary = context_summary
        self.updated_at = self.created_at

    def add_feedback(self, feedback: str, source: str = "chat") -> dict[str, Any]:
        entry = {
            "feedback": feedback,
            "source": source,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.feedback_history.append(entry)
        self.updated_at = entry["timestamp"]
        return entry

    def update_preference(self, key: str, value: Any) -> None:
        self.preferences[key] = value
        self.updated_at = datetime.now(UTC).isoformat()

    def record_app_usage(self, app_id: str, action: str, details: dict[str, Any] | None = None) -> None:
        if app_id not in self.app_usage:
            self.app_usage[app_id] = []
        self.app_usage[app_id].append({
            "action": action,
            "details": details or {},
            "timestamp": datetime.now(UTC).isoformat(),
        })
        self.updated_at = datetime.now(UTC).isoformat()

    def update_context_summary(self, summary: str) -> None:
        self.context_summary = summary
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "preferences": self.preferences,
            "feedback_history": self.feedback_history[-50:],  # Keep last 50
            "app_usage": self.app_usage,
            "context_summary": self.context_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=data["user_id"],
            created_at=data.get("created_at"),
            preferences=data.get("preferences", {}),
            feedback_history=data.get("feedback_history", []),
            app_usage=data.get("app_usage", {}),
            context_summary=data.get("context_summary", ""),
        )


class MemorySkillService:
    """Cross-session memory service for the Interactive App."""

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._memory_dir = Path(base) / "memory" / "users"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, UserProfile] = {}
        self._load_existing_profiles()

    def get_or_create_profile(self, user_id: str) -> UserProfile:
        if user_id not in self._profiles:
            profile = UserProfile(user_id=user_id)
            self._profiles[user_id] = profile
            self._persist_profile(profile)
        return self._profiles[user_id]

    def get_profile(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def add_feedback(self, user_id: str, feedback: str, source: str = "chat") -> dict[str, Any]:
        profile = self.get_or_create_profile(user_id)
        entry = profile.add_feedback(feedback, source)
        self._persist_profile(profile)
        return entry

    def update_preference(self, user_id: str, key: str, value: Any) -> None:
        profile = self.get_or_create_profile(user_id)
        profile.update_preference(key, value)
        self._persist_profile(profile)

    def get_recent_feedback(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        profile = self.get_profile(user_id)
        if not profile:
            return []
        return profile.feedback_history[-limit:]

    def get_context_summary(self, user_id: str) -> str:
        profile = self.get_profile(user_id)
        return profile.context_summary if profile else ""

    def update_context_summary(self, user_id: str, summary: str) -> None:
        profile = self.get_or_create_profile(user_id)
        profile.update_context_summary(summary)
        self._persist_profile(profile)

    def record_app_usage(self, user_id: str, app_id: str, action: str, details: dict[str, Any] | None = None) -> None:
        profile = self.get_or_create_profile(user_id)
        profile.record_app_usage(app_id, action, details)
        self._persist_profile(profile)

    def get_full_context(self, user_id: str) -> dict[str, Any]:
        """Get all memory context for a user (for loading into chat session)."""
        profile = self.get_profile(user_id)
        if not profile:
            return {"user_id": user_id, "initialized": False}
        return {
            "user_id": user_id,
            "initialized": True,
            "preferences": profile.preferences,
            "recent_feedback": profile.feedback_history[-10:],
            "context_summary": profile.context_summary,
            "active_apps": list(profile.app_usage.keys()),
        }

    def _persist_profile(self, profile: UserProfile) -> None:
        path = self._memory_dir / f"{profile.user_id}.json"
        try:
            path.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        except OSError as e:
            raise MemorySkillError(f"Failed to persist profile for {profile.user_id}: {e}")

    def _load_existing_profiles(self) -> None:
        for path in self._memory_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                profile = UserProfile.from_dict(data)
                self._profiles[profile.user_id] = profile
            except Exception:
                continue
