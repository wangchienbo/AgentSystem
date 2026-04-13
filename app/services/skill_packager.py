"""Skill Packager — turn remote MD docs into RPC-callable Workers.

Network skills are Markdown documents describing capabilities. This
module downloads, parses, merges with config center, and produces
MultiActionLlmWorker instances.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SkillPackager:
    """Wraps remote skill MD documents into callable Workers.

    Workflow:
    1. Download MD from URL
    2. Parse fields (model, prompts, input/output, actions)
    3. Merge with SkillConfigCenter (center > MD > defaults)
    4. Build MultiActionLlmWorker
    """

    def __init__(
        self,
        model_router: Any,
        config_center: Any,
    ) -> None:
        self._model_router = model_router
        self._config_center = config_center

    async def package_from_md(self, skill_id: str, md_source: str) -> Any:
        """Package a skill from Markdown content (already downloaded).

        Args:
            skill_id: Unique skill identifier
            md_source: Raw Markdown content

        Returns:
            MultiActionLlmWorker instance
        """
        parsed = self._parse_markdown(md_source)
        center_config = self._config_center.get(skill_id) or {}
        merged = self._merge_config(parsed, center_config)

        from app.core.multi_action_llm_worker import MultiActionLlmWorker
        return MultiActionLlmWorker(
            worker_id=f"skill.{skill_id}",
            model_router=self._model_router,
            model_config=merged["model"],
            actions=merged["actions"],
            description=merged.get("description", ""),
        )

    def _parse_markdown(self, md: str) -> dict[str, Any]:
        """Parse Markdown skill document into structured config."""
        result: dict[str, Any] = {}

        # Title → name
        title = re.search(r"^#\s+(.+)", md, re.MULTILINE)
        if title:
            result["name"] = title.group(1).strip()

        # Sections
        result["description"] = self._extract_section(md, "Description") or ""
        result["system_prompt"] = self._extract_section(md, "System Prompt") or ""
        result["user_prompt_template"] = self._extract_section(md, "User Prompt Template") or ""

        # Model section
        model_text = self._extract_section(md, "Model")
        result["model"] = self._parse_key_value_block(model_text) if model_text else {}

        # Input/Output fields
        input_text = self._extract_section(md, "Input")
        result["input_fields"] = self._parse_field_list(input_text) if input_text else []

        output_text = self._extract_section(md, "Output")
        result["output_fields"] = self._parse_field_list(output_text) if output_text else []

        # Actions
        actions_text = self._extract_section(md, "Actions")
        if actions_text:
            result["action_names"] = self._parse_action_names(actions_text)
        else:
            result["action_names"] = ["execute"]

        return result

    def _merge_config(self, parsed: dict, center: dict) -> dict:
        """Merge MD-parsed config with center config.

        Priority: center > MD > defaults
        """
        md_model = parsed.get("model", {})
        center_model = center.get("model", {})

        model = {
            "provider": center_model.get("provider", md_model.get("provider", "openai")),
            "model": center_model.get("model", md_model.get("model", "gpt-4o")),
            "temperature": center_model.get("temperature", md_model.get("temperature", 0.7)),
            "max_tokens": center_model.get("max_tokens", md_model.get("max_tokens", 4096)),
        }

        # Actions: center action definitions override MD
        center_actions = center.get("actions", {})
        if center_actions:
            actions = center_actions
        else:
            # Build actions from MD
            sys_prompt = center.get("system_prompt", parsed.get("system_prompt", ""))
            user_prompt = center.get("user_prompt_template", parsed.get("user_prompt_template", ""))
            actions = {
                name: {
                    "system_prompt": sys_prompt,
                    "user_prompt": user_prompt,
                }
                for name in parsed.get("action_names", ["execute"])
            }

        return {
            "name": center.get("name", parsed.get("name", "Unknown")),
            "description": center.get("description", parsed.get("description", "")),
            "model": model,
            "actions": actions,
        }

    # -- Markdown parsing helpers ---------------------------------------------

    def _extract_section(self, md: str, section_name: str) -> str | None:
        pattern = rf"^##\s+{re.escape(section_name)}\s*\n(.*?)(?=^##\s+|$)"
        match = re.search(pattern, md, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _parse_key_value_block(self, text: str) -> dict:
        result: dict = {}
        for line in text.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                try:
                    if "." in value:
                        result[key] = float(value)
                    else:
                        result[key] = int(value)
                except ValueError:
                    result[key] = value
        return result

    def _parse_field_list(self, text: str) -> list[dict]:
        fields = []
        for line in text.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if ":" in line:
                name, desc = line.split(":", 1)
                fields.append({"name": name.strip(), "description": desc.strip()})
            elif line:
                fields.append({"name": line, "description": ""})
        return fields

    def _parse_action_names(self, text: str) -> list[str]:
        names = []
        for line in text.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if ":" in line:
                names.append(line.split(":")[0].strip())
            elif line:
                names.append(line)
        return names
