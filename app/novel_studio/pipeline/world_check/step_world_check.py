"""Step: World Check — 世界观完整性门禁

在 chapter_plan 之前执行，作为 pipeline 第一道门禁。
LLM 驱动：检查世界观完整性、角色认知合理性、演进需求、矛盾。

与 setting_check 的区别：
- world_check：生成前门禁，检查「世界观定义是否完整」
- setting_check：生成后审核，检查「章节是否违反设定」

不通过 → pipeline error（不浪费后续 LLM 调用）
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt

logger = logging.getLogger(__name__)

WORLD_CHECK_SYSTEM = load_prompt("world_check", "world_check.md")


class WorldCheckModule(BaseModule):
    """世界观完整性门禁 — 独立 step，不通过则阻断 pipeline"""

    @property
    def name(self) -> str:
        return "world_check"

    @property
    def description(self) -> str:
        return "🌍 世界观完整性检查"

    @property
    def modifies_storage(self) -> bool:
        return False

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            logger.warning("世界观检查跳过：无小说数据")
            return ctx

        chapter_number = self._get_next_chapter_number(ctx)
        logger.info("开始世界观检查 — 第%d章生成前", chapter_number)

        # 构建检查输入
        world_text = self._build_world_text(novel)
        characters_text = self._build_characters_text(novel)
        custom_prompt = getattr(novel, "custom_prompt", "") or ""
        story_progress = self._build_progress_text(novel, chapter_number)

        # LLM 审查
        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM客户端不可用，跳过世界观检查")
            ctx.set_output(self.name, {"is_complete": True, "issues": []})
            return ctx

        result = await self._llm_check(
            client, world_text, characters_text, custom_prompt, story_progress
        )

        issues = result.get("issues", [])
        high_issues = [i for i in issues if i.get("severity") == "high"]
        is_complete = result.get("is_complete", True)

        if high_issues:
            logger.warning(
                "❌ 世界观检查未通过: %d 个高严重度问题 — %s",
                len(high_issues),
                [i.get("description", "")[:60] for i in high_issues],
            )
            # 阻断 pipeline
            error_msg = "世界观不完整，请先完善以下设定：\n" + "\n".join(
                f"  - [{i.get('dimension', '')}] {i.get('description', '')}"
                for i in high_issues
            )
            ctx.set_output(self.name, {
                "is_complete": False,
                "issues": issues,
                "worldview_updates": result.get("worldview_updates", {}),
                "world_supplements": result.get("world_supplements", {}),
                "error": error_msg,
            })
            raise ValueError(error_msg)
        elif issues:
            logger.info(
                "⚠️ 世界观检查发现 %d 个建议项（非阻断）",
                len(issues),
            )
        else:
            logger.info("✅ 世界观检查通过")

        ctx.set_output(self.name, {
            "is_complete": is_complete,
            "issues": issues,
            "worldview_updates": result.get("worldview_updates", {}),
            "world_supplements": result.get("world_supplements", {}),
        })
        return ctx

    # ─── 输入构建 ────────────────────────────────────────────

    def _get_next_chapter_number(self, ctx: PipelineContext) -> int:
        """获取即将生成的章节号"""
        plan = ctx.get_output("chapter_plan", {})
        if plan and plan.get("chapter_number"):
            return plan["chapter_number"]
        novel = ctx.novel
        if novel and hasattr(novel, "chapters"):
            return len(novel.chapters) + 1
        return 1

    def _build_world_text(self, novel) -> str:
        """构建客观世界资料文本"""
        world = getattr(novel, "world", None)
        if not world:
            return "（无世界设定）"

        parts = [f"【世界名称】{getattr(world, 'name', '')}"]
        overview = getattr(world, "overview", "")
        if overview:
            parts.append(f"【概述】{overview}")

        rules = getattr(world, "rules", None) or []
        if rules:
            parts.append("【世界规则】")
            for r in rules:
                parts.append(f"  - {r}")

        for field, label in [
            ("magic_system", "修炼/力量体系"),
            ("factions", "势力结构"),
            ("geography", "地理"),
            ("history", "历史"),
            ("culture", "文化/社会规则"),
            ("technology_level", "科技水平"),
        ]:
            val = getattr(world, field, "") or ""
            if isinstance(val, list):
                val = "\n".join(str(v) for v in val)
            parts.append(f"【{label}】{val if val else '（未定义）'}")

        return "\n\n".join(parts)

    def _build_characters_text(self, novel) -> str:
        """构建角色世界观文本"""
        chars = getattr(novel, "characters", None) or {}
        if not chars:
            return "（无角色）"

        parts = []
        for cid, c in (chars.items() if isinstance(chars, dict) else {}):
            name = getattr(c, "name", cid) if hasattr(c, "name") else c.get("name", cid)
            archetype = getattr(c, "archetype", "") if hasattr(c, "archetype") else c.get("archetype", "")
            background = getattr(c, "background", "") if hasattr(c, "background") else c.get("background", "")
            goal = getattr(c, "goal", "") if hasattr(c, "goal") else c.get("goal", "")
            early_life = getattr(c, "early_life", []) if hasattr(c, "early_life") else c.get("early_life", [])
            debut = getattr(c, "debut_chapter", 0) if hasattr(c, "debut_chapter") else c.get("debut_chapter", 0)

            # 角色世界观
            wv = getattr(c, "worldview", None)
            if wv is None:
                wv = {}

            block = [f"### {name}（{archetype}）"]
            if background:
                block.append(f"背景：{background}")
            if goal:
                block.append(f"目标：{goal}")
            if early_life:
                block.append(f"生平：{'；'.join(early_life)}")
            block.append(f"登场章节：第{debut}章" if debut else "登场章节：未登场")

            known = getattr(wv, "known_facts", []) if hasattr(wv, "known_facts") else wv.get("known_facts", [])
            beliefs = getattr(wv, "beliefs", []) if hasattr(wv, "beliefs") else wv.get("beliefs", [])
            gaps = getattr(wv, "knowledge_gaps", []) if hasattr(wv, "knowledge_gaps") else wv.get("knowledge_gaps", [])

            if known:
                block.append(f"已知事实：{'；'.join(known)}")
            if beliefs:
                block.append(f"主观认知：{'；'.join(beliefs)}")
            if gaps:
                block.append(f"认知空白：{'；'.join(gaps)}")

            parts.append("\n".join(block))

        return "\n\n".join(parts)

    def _build_progress_text(self, novel, chapter_number: int) -> str:
        """构建故事进度文本"""
        chapters = getattr(novel, "chapters", None) or []
        if not chapters:
            return f"故事尚未开始，即将生成第{chapter_number}章"

        lines = [f"已生成 {len(chapters)} 章，即将生成第{chapter_number}章"]
        for ch in chapters[-3:]:  # 最近3章
            num = getattr(ch, "number", "?") if hasattr(ch, "number") else ch.get("number", "?")
            title = getattr(ch, "title", "") if hasattr(ch, "title") else ch.get("title", "")
            lines.append(f"  第{num}章「{title}」")
        return "\n".join(lines)

    # ─── LLM 调用 ────────────────────────────────────────────

    async def _llm_check(
        self,
        client,
        world_text: str,
        characters_text: str,
        custom_prompt: str,
        story_progress: str,
    ) -> dict:
        """LLM 世界观审查"""
        user_prompt = f"""## 客观世界资料

{world_text}

## 角色设定与世界观

{characters_text}

## 作者意图

{custom_prompt if custom_prompt else '（未定义）'}

## 故事进度

{story_progress}

请逐项审查世界观完整性、角色认知合理性、演进需求和矛盾。"""

        try:
            text, _ = client.chat(
                [
                    {"role": "system", "content": WORLD_CHECK_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=3000,
                temperature=0.2,
            )
            return self._parse_response(text or "")
        except Exception as e:
            logger.error("世界观检查 LLM 调用失败: %s", e)
            return {"is_complete": True, "issues": []}

    def _parse_response(self, text: str) -> dict:
        """解析 LLM 返回的 JSON"""
        text = text.strip()
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
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("无法解析世界观检查结果: %s", text[:200])
            return {"is_complete": True, "issues": []}
