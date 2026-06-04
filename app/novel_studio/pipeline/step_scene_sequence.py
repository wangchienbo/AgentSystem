"""Step: Scene Sequence — 场景序列生成

根据章节规划和 4 原则（非主角在场场景/重要事件/主角线/重要时间点）
生成一章内多个场景的序列。每个场景知道与前后场景的衔接关系。

场景序列的输出被 scene_build 和 narrative 使用。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class SceneSequenceModule(BaseModule):
    """② 场景序列：按 4 原则生成多场景序列"""

    @property
    def name(self) -> str:
        return "scene_sequence"

    @property
    def description(self) -> str:
        return "🎬 场景序列（4原则多场景）"

    @property
    def modifies_storage(self) -> bool:
        return False

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")
        if not plan:
            raise ValueError("缺少章节规划，请先执行 chapter_plan 模块")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # 获取上一章的最后场景信息（用于连续性）
        prev_chapter_ending = self._get_prev_chapter_ending(novel)

        # 获取角色列表
        chars_text = self._build_chars_context(novel.characters)

        client = ctx.get_llm_client("novel_writer")
        if not client:
            # 降级：生成一个默认场景
            ctx.set_output(self.name, {
                "scenes": [{
                    "name": f"第{chapter_number}章场景",
                    "location": "",
                    "description": plan.get("summary", ""),
                    "participants": plan.get("suggested_chars", []),
                    "time_period": "",
                    "purpose": plan.get("purpose", ""),
                    "scene_type": "主角线",
                    "key_events": plan.get("key_events", []),
                }],
                "chapter_number": chapter_number,
            })
            return ctx

        prompt = self._build_prompt(novel, plan, chapter_number, prev_chapter_ending, chars_text)
        system_prompt = (
            f"你是一位小说场景序列设计师。为小说《{novel.title}》的第{chapter_number}章设计场景序列。"
            f"只输出 JSON，不要其他文字。"
        )

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        text = text or ""

        scenes = self._parse_scenes(text, plan)
        logger.info("场景序列生成: %d 个场景", len(scenes))

        ctx.set_output(self.name, {
            "scenes": scenes,
            "chapter_number": chapter_number,
        })
        return ctx

    def _get_prev_chapter_ending(self, novel) -> str:
        """获取上一章最后的场景和时间线"""
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            return "（尚无已写章节）"

        prev = chapters[-1]
        content = getattr(prev, "content", "") or ""
        if not content:
            return "（上一章无内容）"

        # 取最后 1500 字作为上下文
        ending = content[-1500:] if len(content) > 1500 else content
        return (
            f"上一章《{getattr(prev, 'title', '')}》结尾：\n"
            f"{ending}"
        )

    def _build_chars_context(self, characters) -> str:
        if not characters:
            return "（尚无角色）"
        lines = []
        for c in characters.values():
            name = getattr(c, "name", "?")
            arch = getattr(c, "archetype", "?")
            personality = "、".join(getattr(c, "personality", []) or [])
            bg = getattr(c, "background", "") or ""
            lines.append(f"  - {name}（{arch}）{personality}")
            if bg:
                lines.append(f"    背景：{bg[:100]}")
        return "\n".join(lines)

    def _build_prompt(
        self,
        novel,
        plan: dict,
        chapter_number: int,
        prev_chapter_ending: str,
        chars_text: str,
    ) -> str:
        # 从世界观提取已有场景
        world = getattr(novel, "world", None)
        existing_scenes_text = ""
        if world:
            scenes = getattr(world, "scenes", {}) or {}
            if scenes:
                scene_list = []
                for sid, s in list(scenes.items())[:5]:
                    scene_list.append(f"  {getattr(s, 'name', '?')}：{getattr(s, 'location', '')}")
                existing_scenes_text = "\n".join(scene_list)

        # 关键事件
        key_events = plan.get("key_events", [])
        events_text = "\n".join(f"  {i+1}. {ev}" for i, ev in enumerate(key_events))

        return f"""为小说《{novel.title}》的第{chapter_number}章设计场景序列。

## 本章规划
标题：{plan.get("title", "")}
概要：{plan.get("summary", "")}
故事作用：{plan.get("purpose", "")}
关键事件：
{events_text}

## 上一章结尾（必须从此处接续）
{prev_chapter_ending}

## 已有场景
{existing_scenes_text or "尚无场景"}

## 角色
{chars_text}

## 场景设计原则
请按以下 4 条原则设计 2-4 个场景：

1️⃣ **主角线** — 主角（沈逸之）在场的场景，推动主角的故事线
2️⃣ **非主角在场场景** — 其他角色单独行动的副线场景（张献忠、李定国等在没有主角时做什么）
3️⃣ **重要事件** — 剧情关键节点必须有对应的场景
4️⃣ **重要时间点** — 时间变化标志（晨/午/昏/夜，或日期推进）

### 场景衔接要求
- 第1个场景必须从上一章结尾处直接开始（时间连续、地点连续）
- 每个场景之间要有自然的过渡（时间流逝或空间转移）
- 场景顺序必须合理（不能出现时间倒流）

### 每个场景的参与者
- 写清楚谁在这个场景中
- 不在场的人不能参与场景
- 一个角色可以出现在多个场景中

输出 JSON 数组（只输出 JSON，不要其他文字）：
[
  {{
    "name": "场景名称（如'破庙避雨'）",
    "location": "具体地点",
    "description": "场景的详细描述（50-100字）",
    "participants": ["参与的角色名数组"],
    "time_period": "时间（如'黄昏'）",
    "purpose": "这个场景要达成什么叙事目的",
    "scene_type": "主角线/非主角场/重要事件/重要时间点",
    "transition_from_prev": "如何从上一场景/上一章过渡到此场景",
    "key_events_done": ["此场景中完成的关键事件索引"]
  }}
]"""

    def _parse_scenes(self, text: str, plan: dict) -> list[dict]:
        """从 LLM 输出解析场景序列"""
        import re

        # 尝试提取 JSON
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                scenes = json.loads(m.group())
                if isinstance(scenes, list):
                    return scenes
            except (json.JSONDecodeError, ValueError):
                pass

        # 如果解析失败，用 LLM 生成的文本再试
        try:
            scenes = json.loads(text)
            if isinstance(scenes, list):
                return scenes
        except (json.JSONDecodeError, ValueError):
            pass

        # 降级：生成一个默认场景
        logger.warning("场景序列 JSON 解析失败，使用降级方案")
        return [{
            "name": f"第{plan.get('chapter_number', '?')}章场景",
            "location": "",
            "description": plan.get("summary", "") or text[:200],
            "participants": plan.get("suggested_chars", []),
            "time_period": "",
            "purpose": plan.get("purpose", ""),
            "scene_type": "主角线",
            "transition_from_prev": "",
            "key_events_done": [],
        }]
