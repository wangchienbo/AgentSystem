"""Step: Chapter Plan — 章节规划

根据大纲（三幕结构 + 章节规划）确定本章的主题、目标、
关键事件和应该参与的角色。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext

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

        max_ch = max((c.number for c in novel.chapters), default=0)
        next_chapter_number = max_ch + 1

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

请根据以上信息，规划第{next_chapter_number}章的内容。输出 JSON 格式（不要其他文字）：
{{
  "title": "本章标题",
  "summary": "本章概要（一两句话）",
  "key_events": ["事件1", "事件2"],
  "characters": ["参与的角色名列表"],
  "purpose": "本章在整体故事中的作用"
}}"""

        system_prompt = f"你正在为小说《{novel.title}》规划第{next_chapter_number}章。只输出 JSON，不要其他内容。"

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
