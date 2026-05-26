"""Mao Zedong thinking framework as a built-in system skill for AgentSystem."""
from __future__ import annotations

from app.models.maoxuan_skill import MaoxuanSkillRequest
from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader, ModelConfigError


class MaoxuanSkillError(ValueError):
    pass


class MaoxuanSkillService:
    """Invokes the LLM with Mao Zedong thinking framework to analyze user problems."""

    SYSTEM_PROMPT = (
        "You are an AI assistant trained to analyze problems using Mao Zedong's thinking framework, "
        "as distilled from his writings in the Mao Zedong Selected Works (Mao Xuan). "
        "Core mental models: 矛盾分析法, 实践认识循环, 持久战略, 农村包围城市, "
        "统一战线, 群众路线, 纸老虎论. "
        "Decision heuristics: 没有调查就没有发言权, 抓主要矛盾, 战略上藐视战术上重视, "
        "团结一切可以团结的力量, 星星之火可以燎原, 实事求是, "
        "不打无准备之仗, 一分为二, 从群众中来到群众中去, 自力更生为主争取外援为辅. "
        "First activation must state: '我以毛泽东的思维框架和你讨论问题，基于《毛选》等公开著作提炼，供参考，非本人观点。' "
        "Then analyze the user's problem using these frameworks. "
        "Call the user '同志'. Use dialectical thinking. Be confident but grounded in investigation. "
        "Use concrete examples and metaphors. Avoid academic jargon. "
        "Apply the relevant mental models to the user's specific situation. "
        "If the user mentions activation keywords (毛选, 教员, 毛泽东, 用毛泽东的方式分析, 从毛选的角度, 教员怎么看), "
        "respond in character as the Mao Zedong thinking framework."
    )

    def __init__(self, loader: ModelConfigLoader | None = None, model_router=None) -> None:
        self._loader = loader or ModelConfigLoader()
        self._model_router = model_router

    def is_available(self) -> bool:
        try:
            config = self._loader.load()
            self._loader.resolve_api_key(config)
            return True
        except ModelConfigError:
            return False

    def execute(self, request: MaoxuanSkillRequest) -> dict:
        if not self.is_available():
            raise MaoxuanSkillError("Model not configured for Maoxuan skill")
        config = self._loader.load()
        api_key = self._loader.resolve_api_key(config)
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        prompt = self._build_prompt(request)
        response = client.probe(prompt)
        return self._extract_response(response)

    def _build_prompt(self, request: MaoxuanSkillRequest) -> str:
        parts = [self.SYSTEM_PROMPT, f"\nUser's problem or question: {request.query}"]
        if request.context:
            parts.append(f"Additional context: {request.context}")
        if request.models:
            parts.append(f"Preferred mental models to apply: {', '.join(request.models)}")
        return "\n".join(parts)

    def _extract_response(self, response: dict) -> dict:
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
        return {"analysis": text, "framework": "mao-zedong-perspective", "models_available": [
            "矛盾分析法", "实践认识循环", "持久战略", "农村包围城市",
            "统一战线", "群众路线", "纸老虎论",
        ]}
