from __future__ import annotations

import json

from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.services.model_client import OpenAIResponsesClient, ModelClientError
from app.services.model_config_loader import ModelConfigError, ModelConfigLoader


class ModelSkillSuggester:
    def __init__(self, loader: ModelConfigLoader | None = None) -> None:
        self._loader = loader or ModelConfigLoader()

    def suggest(self, experience: ExperienceRecord, fallback_skill_id: str) -> SkillBlueprint:
        config = self._loader.load()
        api_key = self._loader.resolve_api_key(config)
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        prompt = self._build_prompt(experience=experience, fallback_skill_id=fallback_skill_id)
        response = client.probe(prompt)
        payload = self._extract_json_payload(response)
        return SkillBlueprint(
            skill_id=payload.get("skill_id") or fallback_skill_id,
            name=payload["name"],
            goal=payload["goal"],
            inputs=payload.get("inputs", ["context", "runtime_event", "app_data_record"]),
            outputs=payload.get("outputs", ["action_plan", "structured_result"]),
            steps=payload["steps"],
            related_experience_ids=[experience.experience_id],
        )

    def is_available(self) -> bool:
        try:
            config = self._loader.load()
            self._loader.resolve_api_key(config)
            return True
        except ModelConfigError:
            return False

    def _build_prompt(self, experience: ExperienceRecord, fallback_skill_id: str) -> str:
        return (
            "You generate a reusable skill blueprint from runtime experience. "
            "Return strict JSON with keys: skill_id, name, goal, inputs, outputs, steps. "
            f"Use this fallback skill_id if needed: {fallback_skill_id}. "
            f"Experience title: {experience.title}. "
            f"Experience summary: {experience.summary}. "
            f"Experience tags: {', '.join(experience.tags)}."
        )

    def _extract_json_payload(self, response: dict) -> dict:
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
            raise ModelClientError("Model response did not contain output_text")
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise ModelClientError(f"Model output was not valid JSON: {text[:300]}") from error
