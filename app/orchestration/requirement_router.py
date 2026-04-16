from __future__ import annotations

from dataclasses import dataclass
import re

from app.models.requirement_intent import RequirementIntent


@dataclass(frozen=True)
class KeywordRules:
    app_keywords: tuple[str, ...] = (
        "app",
        "application",
        "system",
        "dashboard",
        "workflow",
        "审批",
        "系统",
        "应用",
        "平台",
        "流程",
    )
    skill_keywords: tuple[str, ...] = (
        "skill",
        "plugin",
        "tool",
        "adapter",
        "validator",
        "转换",
        "校验",
        "插件",
        "工具",
        "适配",
    )
    demonstration_keywords: tuple[str, ...] = (
        "demonstrate",
        "demo",
        "show you",
        "watch me",
        "click",
        "screen",
        "示范",
        "演示",
        "操作一遍",
        "照着做",
        "页面",
        "点击",
    )
    abstract_keywords: tuple[str, ...] = (
        "strategy",
        "vision",
        "roadmap",
        "architecture",
        "战略",
        "规划",
        "愿景",
        "架构",
        "长期",
    )


class RequirementRouter:
    def __init__(self, rules: KeywordRules | None = None) -> None:
        self.rules = rules or KeywordRules()

    def route(self, text: str) -> RequirementIntent:
        normalized = self._normalize(text)
        keywords = self._extract_keywords(normalized)
        requirement_type = self._classify_type(normalized)
        demo_decision, reason = self._decide_demonstration(normalized, requirement_type)

        return RequirementIntent(
            raw_text=text,
            normalized_text=normalized,
            requirement_type=requirement_type,
            demonstration_decision=demo_decision,
            reason=reason,
            extracted_keywords=keywords,
        )

    def _normalize(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text.strip().lower())
        return compact

    def _extract_keywords(self, text: str) -> list[str]:
        bag: list[str] = []
        for word in (
            *self.rules.app_keywords,
            *self.rules.skill_keywords,
            *self.rules.demonstration_keywords,
            *self.rules.abstract_keywords,
        ):
            if word in text:
                bag.append(word)
        return bag

    def _classify_type(self, text: str) -> str:
        has_app = any(word in text for word in self.rules.app_keywords)
        has_skill = any(word in text for word in self.rules.skill_keywords)

        if has_app and has_skill:
            return "hybrid"
        if has_app:
            return "app"
        if has_skill:
            return "skill"
        return "unclear"

    def _decide_demonstration(self, text: str, requirement_type: str) -> tuple[str, str]:
        if any(word in text for word in self.rules.abstract_keywords):
            return "clarify", "需求偏抽象，应该先补充目标、边界和约束，而不是直接要求示范。"

        if any(word in text for word in self.rules.demonstration_keywords):
            if requirement_type in {"app", "hybrid", "unclear"}:
                return "required", "需求包含可观察的操作流程，适合先让用户示范一遍再抽取步骤和规则。"
            return "optional", "需求更偏单点技能，但包含可观察步骤，示范可作为补充输入。"

        if requirement_type == "skill":
            return "not_needed", "需求更像可直接结构化生成的技能，优先直接定义输入输出与规则。"

        if requirement_type == "app":
            return "optional", "需求偏应用构建，可先直接生成草案；若流程细节不足，再请求示范。"

        if requirement_type == "hybrid":
            return "optional", "需求同时涉及应用与技能，可先规划结构，再按缺失部分决定是否示范。"

        return "clarify", "暂时无法判断应生成应用还是技能，先补充需求示例更合适。"
