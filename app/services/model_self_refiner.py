from __future__ import annotations

import json

from app.models.app_blueprint import AppBlueprint
from app.models.experience import ExperienceRecord
from app.models.patch_proposal import PatchProposal
from app.services.model_client import OpenAIResponsesClient, ModelClientError
from app.services.model_config_loader import ModelConfigError, ModelConfigLoader


class ModelSelfRefiner:
    def __init__(self, loader: ModelConfigLoader | None = None) -> None:
        self._loader = loader or ModelConfigLoader()

    def is_available(self) -> bool:
        try:
            config = self._loader.load()
            self._loader.resolve_api_key(config)
            return True
        except ModelConfigError:
            return False

    def propose(self, app_instance_id: str, blueprint: AppBlueprint, experience: ExperienceRecord) -> list[PatchProposal]:
        config = self._loader.load()
        api_key = self._loader.resolve_api_key(config)
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        response = client.probe(self._build_prompt(app_instance_id, blueprint, experience))
        payload = self._extract_json_payload(response)
        proposals = payload.get("proposals", [])
        if not isinstance(proposals, list) or not proposals:
            raise ModelClientError("Model self refinement returned no proposals")
        return [
            PatchProposal(
                proposal_id=item["proposal_id"],
                app_instance_id=app_instance_id,
                target_type=item["target_type"],
                title=item["title"],
                summary=item["summary"],
                evidence=item.get("evidence", [experience.summary]),
                expected_benefit=item["expected_benefit"],
                risk_level=item.get("risk_level", "medium"),
                auto_apply_allowed=item.get("auto_apply_allowed", False),
                validation_checklist=item.get("validation_checklist", []),
                rollback_target=item["rollback_target"],
                patch=item.get("patch", {}),
            )
            for item in proposals
        ]

    def _build_prompt(self, app_instance_id: str, blueprint: AppBlueprint, experience: ExperienceRecord) -> str:
        return (
            "You synthesize constrained self-refinement proposals for an app runtime. "
            "Return strict JSON with a top-level key 'proposals'. "
            "Each proposal must contain: proposal_id, target_type, title, summary, expected_benefit, risk_level, "
            "auto_apply_allowed, validation_checklist, rollback_target, patch. "
            "Allowed target_type values: runtime_policy, workflow. Prefer at most 2 proposals. "
            f"App instance id: {app_instance_id}. "
            f"Blueprint runtime policy: {blueprint.runtime_policy.model_dump(mode='json')}. "
            f"Workflow count: {len(blueprint.workflows)}. "
            f"Experience title: {experience.title}. "
            f"Experience summary: {experience.summary}."
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
