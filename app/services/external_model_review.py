from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.model_router import ModelRouter


@dataclass
class ExternalModelReviewResult:
    action: str
    model: str
    source: str
    content: str
    raw: dict[str, Any]


class ExternalModelReviewService:
    """受控外模型评审服务。"""

    def __init__(self, model_router: ModelRouter, default_caller: str = "external_review") -> None:
        self._model_router = model_router
        self._default_caller = default_caller

    def review(
        self,
        *,
        action: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        model_preference: str | None = None,
    ) -> ExternalModelReviewResult:
        caller = self._default_caller if not model_preference else model_preference
        client = self._model_router.get_client(caller)
        route = self._model_router.resolve(caller)
        full_prompt = self._build_prompt(action=action, prompt=prompt, context=context or {})
        response = client.complete(full_prompt)
        content = self._extract_text(response)
        return ExternalModelReviewResult(
            action=action,
            model=route.model_name,
            source=route.source,
            content=content,
            raw=response if isinstance(response, dict) else {"response": str(response)},
        )

    def review_plan(self, prompt: str, context: dict[str, Any] | None = None) -> ExternalModelReviewResult:
        return self.review(action="review_plan", prompt=prompt, context=context)

    def review_code(self, prompt: str, context: dict[str, Any] | None = None) -> ExternalModelReviewResult:
        return self.review(
            action="review_code",
            prompt=prompt,
            context=context,
            model_preference="external_review_strong",
        )

    def _build_prompt(self, *, action: str, prompt: str, context: dict[str, Any]) -> str:
        return (
            "你是一个受控外部评审模型。你的任务不是替代主控决策，而是提供评审信号。\n"
            f"评审动作: {action}\n"
            "请输出：结论、主要优点、主要风险、推荐下一步。\n\n"
            f"需求/方案:\n{prompt}\n\n"
            f"上下文(JSON):\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            if isinstance(response.get("output_text"), str):
                return response["output_text"]
            if isinstance(response.get("content"), str):
                return response["content"]
        return str(response)


class ExternalModelReviewWorker:
    """MasterControl 可调用的外模型评审 Worker。"""

    def __init__(self, review_service: ExternalModelReviewService) -> None:
        self._review_service = review_service

    def review_plan(self, target: str = "", params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = params or {}
        prompt = payload.get("prompt") or target
        context = payload.get("context")
        result = self._review_service.review_plan(prompt=prompt, context=context)
        return {
            "status": "success",
            "message": "方案评审完成",
            "data": {
                "action": result.action,
                "model": result.model,
                "source": result.source,
                "content": result.content,
            },
        }

    def review_code(self, target: str = "", params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = params or {}
        prompt = payload.get("prompt") or target
        context = payload.get("context")
        result = self._review_service.review_code(prompt=prompt, context=context)
        return {
            "status": "success",
            "message": "代码评审完成",
            "data": {
                "action": result.action,
                "model": result.model,
                "source": result.source,
                "content": result.content,
            },
        }
