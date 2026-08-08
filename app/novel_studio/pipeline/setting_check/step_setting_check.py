"""Step: Setting Check — 设定一致性交叉比对

在叙事合成之后、读者体验评审之前执行。
独立 LLM 调用：提取 custom_prompt 中的可验证规则 → 逐条与正文交叉比对 → 输出违规清单。

与 editorial_review 的区别：
- setting_check：规则逐条比对，判定「是否违反设定」
- editorial_review：读者视角评分，判定「是否好看」
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt, build_novel_context

logger = logging.getLogger(__name__)

SETTING_CHECK_SYSTEM = load_prompt("setting_check", "setting_check.md")


class SettingCheckModule(BaseModule):
    """设定一致性交叉比对 — 独立 step，可触发重生成"""

    @property
    def name(self) -> str:
        return "setting_check"

    @property
    def description(self) -> str:
        return "🔍 设定一致性交叉比对"

    @property
    def modifies_storage(self) -> bool:
        return False  # 只做检查，不修改数据

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        narrative_out = ctx.get_output("narrative", {})
        content = narrative_out.get("content", "")

        if not content:
            logger.warning("设定检查跳过：叙事输出为空")
            return ctx

        chapter_number = narrative_out.get("chapter_number", 0)
        title = narrative_out.get("title", "")
        logger.info("开始设定一致性检查 第%d章「%s」", chapter_number, title)

        # 获取小说专属设定
        novel = ctx.novel
        custom_prompt = getattr(novel, "custom_prompt", "") if novel else ""
        world_rules = []
        if novel and hasattr(novel, "world"):
            world = novel.world
            if hasattr(world, "rules"):
                world_rules = world.rules or []

        if not custom_prompt and not world_rules:
            logger.info("设定检查跳过：无专属设定规则")
            ctx.set_output(self.name, {"is_consistent": True, "violations": []})
            return ctx

        # 构建设定文本
        setting_text = self._build_setting_text(novel, custom_prompt, world_rules)

        # LLM 逐条交叉比对
        result = await self._llm_check(ctx, setting_text, content, chapter_number, title)

        # 判定
        violations = result.get("violations", [])
        is_consistent = result.get("is_consistent", True)
        high_violations = [v for v in violations if v.get("severity") == "high"]

        # 强制输出违规详情（用于调试）
        if violations:
            print(f"[setting_check] violations={json.dumps(violations, ensure_ascii=False)[:2000]}", flush=True)

        if len(high_violations) >= 2:
            logger.warning(
                "❌ 设定检查未通过: %d 个高严重度违规 — %s",
                len(high_violations),
                [v.get("violation", "")[:60] for v in high_violations],
            )
            ctx.needs_regeneration = True
            ctx.regeneration_feedback = self._format_feedback(violations)
        elif violations:
            logger.warning(
                "⚠️ 设定检查发现 %d 个问题（非高严重度），继续",
                len(violations),
            )
        else:
            logger.info("✅ 设定检查通过：无违规")

        output = {
            "is_consistent": is_consistent,
            "violations": violations,
            "high_count": len(high_violations),
            "total_count": len(violations),
        }
        ctx.set_output(self.name, output)
        return ctx

    # ─── 构建设定文本 ────────────────────────────────────────

    def _build_setting_text(self, novel, custom_prompt: str, world_rules: list) -> str:
        """构建注入 LLM 的设定文本，自动剥离 AI 行为指令"""
        parts = []

        if novel:
            parts.append(f"【小说】{getattr(novel, 'title', '')}")
            genre = getattr(novel, "genre", "")
            if genre:
                parts.append(f"【类型】{genre}")

        if world_rules:
            parts.append("【世界规则】")
            for r in world_rules:
                parts.append(f"  - {r}")

        if custom_prompt:
            # 剥离 AI 行为指令——这些是给生成 AI 的约束，不是故事设定
            story_only = self._strip_ai_instructions(custom_prompt)
            if story_only:
                parts.append(f"【小说专属设定】\n{story_only}")

        return "\n".join(parts)

    def _strip_ai_instructions(self, text: str) -> str:
        """移除 custom_prompt 中的 AI 行为指令行，只保留故事设定"""
        ai_keywords = [
            '不反问', '不举例', '不鼓励', '不解释', '不闲聊', '不吐槽',
            '不能扫描', '不能替', '不能给', '不能控制',
            '禁止', '不要', '不给多余', '问什么答什么',
            '直接给答案', '直接给结论', '不列步骤', '不给尺寸',
            '不说比例', '不展开', '不教学',
        ]
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                lines.append(line)
                continue
            # 跳过纯 AI 行为指令行
            if any(kw in stripped for kw in ai_keywords):
                continue
            lines.append(line)
        return '\n'.join(lines)

    # ─── LLM 调用 ────────────────────────────────────────────

    async def _llm_check(
        self,
        ctx: PipelineContext,
        setting_text: str,
        content: str,
        chapter_number: int,
        chapter_title: str,
    ) -> dict:
        """LLM 逐条规则交叉比对"""
        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM客户端不可用，跳过设定检查")
            return {"is_consistent": True, "violations": []}

        user_prompt = f"""## 小说专属设定

{setting_text}

## 第{chapter_number}章「{chapter_title}」正文

{content}

请逐条比对上述设定与正文，找出所有矛盾。"""

        try:
            response, _ = client.chat(
                [
                    {"role": "system", "content": SETTING_CHECK_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2000,
                temperature=0.1,
            )
            return self._parse_response(response or "")
        except Exception as e:
            logger.error("设定检查 LLM 调用失败: %s", e)
            return {"is_consistent": True, "violations": []}

    def _parse_response(self, response: str) -> dict:
        """解析 LLM 返回的 JSON"""
        # 尝试提取 JSON 块
        text = response.strip()
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 { ... } 块
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("无法解析设定检查结果: %s", text[:200])
            return {"is_consistent": True, "violations": []}

    # ─── 反馈格式化 ──────────────────────────────────────────

    def _format_feedback(self, violations: list[dict]) -> str:
        """将违规清单格式化为叙事层可理解的反馈"""
        lines = ["## 设定一致性检查发现以下问题，请在重写时修正：", ""]
        for i, v in enumerate(violations, 1):
            lines.append(f"{i}. **规则**: {v.get('rule', '')}")
            lines.append(f"   **违规**: {v.get('violation', '')}")
            lines.append(f"   **严重度**: {v.get('severity', 'unknown')}")
            explanation = v.get("explanation", "")
            if explanation:
                lines.append(f"   **说明**: {explanation}")
            lines.append("")
        return "\n".join(lines)
