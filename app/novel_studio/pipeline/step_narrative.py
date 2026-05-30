"""Step: Narrative Synthesis — 叙事合成

将角色的独立决策 + 场景描述合成为一章完整的叙事内容。
使用第三人称有限视角（由章节决定的 POV 角色）。
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class NarrativeModule(BaseModule):
    """⑤ 叙事合成：角色行为 + 场景 → 完整章节"""

    @property
    def name(self) -> str:
        return "narrative"

    @property
    def description(self) -> str:
        return "✍️ 叙事合成"

    @property
    def modifies_storage(self) -> bool:
        return True  # 会创建新章节保存到 storage

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")
        scene = ctx.get_output("scene_build")
        actions = ctx.get_output("character_action", {}).get("actions", [])

        if not plan:
            raise ValueError("缺少章节规划")
        if not scene:
            raise ValueError("缺少场景定义")

        client = ctx.get_llm_client("novel_writer")
        if not client:
            raise RuntimeError("LLM 客户端未配置")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)
        prev_chapters = novel.chapters[-3:] if novel.chapters else []

        # 构建上下文字符串
        prompt = self._build_prompt(novel, plan, scene, actions, prev_chapters)
        system_prompt = (
            f"你是一位中国古典小说风格的作家，正在创作小说《{novel.title}》。"
            f"请将角色行为合成流畅的叙事章节。"
            f"使用中文写作。"
        )

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7,
        )
        text = text or ""

        # 保存章节
        text = self._clean_output(text)

        from app.novel_studio.models import Chapter
        new_chapter = Chapter(
            number=chapter_number,
            title=plan.get("title", f"第{chapter_number}章"),
            content=text,
        )

        # 保存到 storage
        try:
            ctx._storage.add_chapter(ctx.novel_id, new_chapter)
            logger.info("第%d章已保存: %s (%d字)", chapter_number, new_chapter.title, len(text))
        except Exception as e:
            logger.error("保存章节失败: %s", e)
            # 如果 add_chapter 不存在，保存到 novel.chapters
            if hasattr(novel, 'chapters') and novel.chapters is not None:
                novel.chapters.append(new_chapter)
            else:
                novel.chapters = [new_chapter]

        ctx.set_output(self.name, {
            "chapter_number": chapter_number,
            "title": plan.get("title", f"第{chapter_number}章"),
            "content": text,
            "word_count": len(text),
        })
        return ctx

    def _build_prompt(
        self,
        novel,
        plan: dict,
        scene: dict,
        actions: list[dict],
        prev_chapters: list,
    ) -> str:
        lines = [f"请根据以下信息创作第{plan.get('chapter_number','?')}章「{plan.get('title','')}」。"]

        # 本章概要
        lines.append(f"\n## 本章概要")
        lines.append(plan.get("summary", "") or "")
        if plan.get("purpose"):
            lines.append(f"故事作用：{plan['purpose']}")
        if plan.get("key_events"):
            lines.append(f"关键事件：")
            for ev in plan["key_events"]:
                lines.append(f"  • {ev}")

        # 场景
        lines.append(f"\n## 场景")
        lines.append(f"地点：{scene.get('name','')}（{scene.get('location','')}）")
        lines.append(f"氛围：{scene.get('atmosphere','')}")
        lines.append(f"天气：{scene.get('weather','')}，时间：{scene.get('time_period','')}")
        if scene.get("description"):
            lines.append(f"描述：{scene['description']}")

        # 角色行为
        lines.append(f"\n## 角色行为")
        for action in actions:
            char = action.get("character", "?")
            perception = action.get("感知", "")
            act = action.get("action", "")
            diag = action.get("dialogue", "")
            inner = action.get("inner", "")
            lines.append(f"\n### {char}")
            if perception:
                lines.append(f"感受到：{perception}")
            if act:
                lines.append(f"行动：{act}")
            if diag and diag != "沉默":
                lines.append(f"说：「{diag}」")
            if inner:
                lines.append(f"内心：{inner}")

        # 前文摘要（避免重复开头）
        if prev_chapters:
            lines.append(f"\n## 前文回顾")
            for ch in prev_chapters[-3:]:
                lines.append(f"  第{ch.number}章 {ch.title}（摘要：{getattr(ch,'content','')[:100]}）")

        lines.append(f"""
## 写作要求
- 使用第三人称有限视角，以场景主导角色的视角为准
- 继承前文的语言风格和叙事节奏
- 角色的对话必须使用中文引号「」
- 角色说话风格必须与角色设定一致
- 叙事要有画面感和沉浸感
- 不要直接写出"角色感受到"、"角色看到"这样的说明
- 直接写他看到的是什么、感受到了什么
- 输出完整的章节正文（不含标题和元信息）""")

        return "\n".join(lines)

    def _clean_output(self, text: str) -> str:
        """清理 LLM 输出中的多余标记"""
        import re
        # 去掉 markdown 代码块
        text = re.sub(r"```(?:markdown|text|plain)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        # 去掉"第X章"之类的标题行（如果 LLM 自己加了）
        text = text.strip()
        # 如果以"第"开头且第二字是"章"，去掉这一行
        text = re.sub(r"^第[一二三四五六七八九十\d]+章[：:．\.\s].*\n?", "", text)
        return text.strip()
