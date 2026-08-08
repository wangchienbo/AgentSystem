"""Step: Chapter Plan — 章节规划

根据大纲（三幕结构 + 章节规划）确定本章的主题、目标、
关键事件和应该参与的角色。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

logger = logging.getLogger(__name__)


class ChapterPlanModule(BaseModule):
    """① 章节规划：从大纲查本章目标"""

    @property
    def name(self) -> str:
        return "chapter_plan"

    @property
    def description(self) -> str:
        return "📋 章节规划"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            raise ValueError("小说不存在")

        next_chapter_number = len(novel.chapters) + 1

        # ── 检查大纲中是否有这一章的规划 ──
        plan = _find_chapter_plan(novel, next_chapter_number)
        if plan:
            logger.info("大纲已有第%d章规划: %s", next_chapter_number, plan.get("title", ""))
            ctx.set_output(self.name, {
                "chapter_number": next_chapter_number,
                "title": plan.get("title", f"第{next_chapter_number}章"),
                "summary": plan.get("summary", ""),
                "key_events": plan.get("key_events", []),
                "suggested_chars": plan.get("characters", []),
                "purpose": plan.get("purpose", ""),
                "source": "outline",  # 来自大纲
                "is_prediction": True,  # ⚠️ 大纲也是预测不是剧本
            })
            return ctx

        # ── 大纲没有细化到章节，让 LLM 生成规划 ──
        client = ctx.get_llm_client("novel_writer")
        if not client:
            raise RuntimeError("LLM 客户端未配置")

        # 构建大纲上下文
        outline_text = _build_outline_context(novel)
        existing_chapters = _build_chapters_summary(novel.chapters)

        prompt = f"""你是一位资深小说规划师。请为小说《{novel.title}》的第{next_chapter_number}章做规划。

## 已有章节
{existing_chapters or "（尚无已写章节）"}

## 故事大纲
{outline_text or "（尚无详细大纲）"}

## 主要角色
{_build_chars_summary(novel.characters)}

## 小说核心设定
{build_novel_context(novel)}

请根据以上信息，规划第{next_chapter_number}章的内容。输出 JSON 格式（不要其他文字）：
{{
  "title": "本章标题（注意：只写标题本身，不要加「第N章：」前缀）",
  "summary": "本章概要（一两句话）",
  "key_events": ["事件1", "事件2"],
  "characters": ["参与的角色名列表"],
  "purpose": "本章在整体故事中的作用"
}}"""

        # 第1章特殊约束
        first_chapter_rules = ""
        if next_chapter_number == 1:
            first_chapter_rules = (
                f"\n\n【第1章特殊约束——建立，不解决】"
                f"\n第1章的核心任务是让读者认识这个世界和角色，不是推进剧情。"
                f"\n- 本章不解决任何核心矛盾（生存危机、权力斗争等）"
                f"\n- 本章只做三件事：① 建立世界观（时代、环境、氛围）② 角色初现（主角+1-2个关键角色登场，通过行动展示性格）③ 埋下伏笔（暗示后续冲突，但不展开）"
                f"\n- key_events 必须是\"建立型\"事件：初次见面、环境探索、日常挣扎、小冲突（非生死）"
                f"\n- 禁止的事件类型：生死决斗、权力夺位、大规模冲突、核心矛盾爆发"
                f"\n- purpose 应该类似：\"建立世界观和角色关系，让读者感受这个世界的氛围\""
                f"\n\n【第1章必须有足够多的场景来展示过渡】"
                f"\n- key_events 至少5个，确保有足够场景展示：醒来→困惑→观察→适应→初步接触"
                f"\n- 每个 key_event 应该是一个独立的、缓慢展开的过程，不是快速解决"
            )

        system_prompt = (
            f"你正在为小说《{novel.title}》规划第{next_chapter_number}章。"
            f"只输出 JSON，不要其他内容。注意：规划的事件必须符合常识逻辑"
            f"——角色做某件事必须有合理的动机和可预期的结果，不能出现"
            f"\"画在沙子上别人付钱\"这类不合逻辑的桥段。每个事件在现实中都能自圆其说。"
            f"\n\n【重要】这只是一个**预测**，不是剧本。你的任务是预判角色可能做什么，"
            f"而不是命令他们做什么。角色进入场景后将自由决策，你的预测可能会被自然推翻。"
            f"好的预测是合乎逻辑的猜测，而不是规定的剧情。"
            f"{first_chapter_rules}"
        )

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7,
        )
        text = text or ""

        # 解析 JSON
        plan_data = _parse_json_output(text)
        if not plan_data:
            plan_data = {
                "title": f"第{next_chapter_number}章",
                "summary": text[:200],
                "key_events": [],
                "characters": list(novel.characters.keys())[:3] if novel.characters else [],
                "purpose": "",
            }

        logger.info("LLM 规划第%d章: %s", next_chapter_number, plan_data.get("title", ""))
        ctx.set_output(self.name, {
            "chapter_number": next_chapter_number,
            "title": plan_data.get("title", f"第{next_chapter_number}章"),
            "summary": plan_data.get("summary", ""),
            "key_events": plan_data.get("key_events", []),
            "suggested_chars": plan_data.get("characters", []),
            "purpose": plan_data.get("purpose", ""),
            "source": "llm",
            "is_prediction": True,  # ⚠️ 这是预测，不是剧本
        })
        return ctx


def _find_chapter_plan(novel, chapter_number: int) -> dict | None:
    """在大纲中查找章节规划"""
    outline = getattr(novel, "outline", None)
    if not outline:
        return None
    for ch in getattr(outline, "chapters", []):
        if getattr(ch, "number", None) == chapter_number:
            return {
                "title": getattr(ch, "title", ""),
                "summary": getattr(ch, "summary", ""),
                "key_events": getattr(ch, "key_events", []),
                "characters": getattr(ch, "characters", []),
                "purpose": getattr(ch, "purpose", ""),
            }
    return None


def _build_outline_context(novel) -> str:
    outline = getattr(novel, "outline", None)
    if not outline:
        return ""
    parts = []
    if getattr(outline, "summary", None):
        parts.append(f"梗概：{outline.summary}")
    ta = getattr(outline, "three_act", None)
    if ta:
        if getattr(ta, "act1", None): parts.append(f"第一幕：{ta.act1}")
        if getattr(ta, "act2", None): parts.append(f"第二幕：{ta.act2}")
        if getattr(ta, "act3", None): parts.append(f"第三幕：{ta.act3}")
    if getattr(outline, "chapters", None):
        for ch in outline.chapters:
            parts.append(f"  第{ch.number}章 {ch.title}：{getattr(ch, 'summary', '')}")
    return "\n".join(parts)


def _build_chapters_summary(chapters) -> str:
    if not chapters:
        return ""
    lines = []
    for ch in chapters[-5:]:  # 最近5章
        content = getattr(ch, "content", "") or ""
        lines.append(f"  第{ch.number}章 {ch.title}（{len(content)}字）")
    return "\n".join(lines)


def _build_chars_summary(characters) -> str:
    if not characters:
        return "（尚无角色）"
    lines = []
    for c in characters.values():
        personality = "、".join(getattr(c, "personality", []) or [])
        lines.append(f"  {c.name}（{getattr(c, 'archetype', '?')}）{personality}")
    return "\n".join(lines)


def _parse_json_output(text: str) -> dict | None:
    """尝试从 LLM 输出中提取 JSON"""
    import re
    # 尝试 ```json ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 尝试 {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None
