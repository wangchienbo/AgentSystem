"""App-specific intent analyzer — uses cheap model for cost efficiency."""
from __future__ import annotations

import json
from typing import Any

from app.models.app_design import AppIntentResult
from app.services.model_router import ModelRouter


class AppIntentAnalyzerError(ValueError):
    pass


class AppIntentAnalyzer:
    """App creation intent analyzer.

    Analyzes user input to extract structured app creation intent.
    Uses cheap model by default (configurable via ModelRouter).
    """

    SYSTEM_PROMPT = (
        "You are an App Creation Intent Analyzer for AgentSystem. "
        "Analyze the user's request and output a structured JSON object.\n\n"
        "Output format:\n"
        "{\n"
        '  "app_name": "suggested app name",\n'
        '  "goal": "one-sentence core objective",\n'
        '  "kind": "interactive|service|scheduled|monitoring",\n'
        '  "complexity": "simple|moderate|complex",\n'
        '  "constraints": ["constraint1", ...],\n'
        '  "needs_clarification": false,\n'
        '  "clarification_questions": ["question1", ...],\n'
        '  "confidence": 0.8\n'
        "}\n\n"
        "Rules:\n"
        "1. If the request is vague or missing key info, set needs_clarification=true\n"
        "2. confidence should reflect how clear the request is (0.0-1.0)\n"
        "3. Only return JSON, no other text.\n"
    )

    def __init__(self, model_router: ModelRouter) -> None:
        self._router = model_router

    def analyze(self, user_input: str, context: dict[str, Any] | None = None) -> AppIntentResult:
        """Analyze user input for app creation intent.

        Args:
            user_input: User's natural language request
            context: Additional context (optional)

        Returns:
            AppIntentResult with structured intent
        """
        client = self._router.get_client("intent_analyzer", "simple")

        user_message = user_input
        if context:
            user_message += f"\n\nAdditional context: {json.dumps(context, ensure_ascii=False)}"

        try:
            response, _usage = client.generate_response(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=500,
                temperature=0.1,
            )
            return self._parse_response(response)
        except Exception as exc:
            # Fallback: minimal intent from user input
            return AppIntentResult(
                app_name=user_input[:50],
                goal=user_input,
                complexity="moderate",
                needs_clarification=True,
                clarification_questions=["请详细描述你想要的 App 功能"],
                confidence=0.0,
            )

    def _parse_response(self, response: str) -> AppIntentResult:
        """Parse LLM response into AppIntentResult."""
        text = response.strip()
        # Extract JSON from code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        # Find JSON in text
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise AppIntentAnalyzerError(f"No JSON found in response: {text[:200]}")

        data = json.loads(text[start:end + 1])
        return AppIntentResult(
            app_name=data.get("app_name", ""),
            goal=data.get("goal", ""),
            kind=data.get("kind", "service"),
            complexity=data.get("complexity", "moderate"),
            constraints=data.get("constraints", []),
            needs_clarification=data.get("needs_clarification", False),
            clarification_questions=data.get("clarification_questions", []),
            confidence=data.get("confidence", 0.0),
        )
