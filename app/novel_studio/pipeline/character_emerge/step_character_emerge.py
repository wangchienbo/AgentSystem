"""Step: Character Emerge — 角色涌现

每章 narrative 完成后、memory_update 之前执行。
职责（全部由 LLM 驱动，零硬编码）：
1. 阅读最新生成的章节
2. 判断是否出现了值得立传的新角色
3. 自动生成角色 profile 并写入 characters
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt

logger = logging.getLogger(__name__)

CHARACTER_EMERGE_SYSTEM = load_prompt("character_emerge", "character_emerge.md")


class CharacterEmergeModule(BaseModule):
    """角色涌现 — 从章节中自动发现并创建新角色"""

    @property
    def name(self) -> str:
        return "character_emerge"

    @property
    def description(self) -> str:
        return "👤 角色涌现（自动发现新角色）"

    @property
    def modifies_storage(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            logger.warning("角色涌现跳过：无小说数据")
            return ctx

        # 获取最新章节
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            logger.warning("角色涌现跳过：无章节")
            return ctx

        latest_chapter = chapters[-1]
        chapter_content = getattr(latest_chapter, "content", "") or ""
        chapter_number = getattr(latest_chapter, "number", 0) or 0

        if not chapter_content or len(chapter_content) < 100:
            logger.warning("角色涌现跳过：章节内容太短")
            return ctx

        # 构建已有角色列表
        chars = getattr(novel, "characters", None) or {}
        existing_names = []
        for c in (chars.values() if isinstance(chars, dict) else chars):
            name = getattr(c, "name", "") if hasattr(c, "name") else c.get("name", "")
            if name:
                existing_names.append(name)

        existing_chars_text = "\n".join(f"- {n}" for n in existing_names) if existing_names else "（尚无角色）"

        # LLM 判断
        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM客户端不可用，跳过角色涌现")
            ctx.set_output(self.name, {"has_new_characters": False, "new_characters": []})
            return ctx

        prompt = CHARACTER_EMERGE_SYSTEM.replace(
            "{existing_characters}", existing_chars_text
        ).replace(
            "{chapter_content}", chapter_content[:8000]  # 截断，避免超长
        )

        try:
            text, _ = client.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.3,
                stream=False,
            )
            result = self._parse_result(text)
        except Exception as e:
            logger.error("角色涌现 LLM 调用失败: %s", e)
            ctx.set_output(self.name, {"has_new_characters": False, "new_characters": [], "error": str(e)})
            return ctx

        if not result.get("has_new_characters"):
            logger.info("👤 角色涌现：本章无新角色")
            ctx.set_output(self.name, {"has_new_characters": False, "new_characters": []})
            return ctx

        new_chars = result.get("new_characters", [])
        if not new_chars:
            ctx.set_output(self.name, {"has_new_characters": False, "new_characters": []})
            return ctx

        # 写入 characters
        from app.novel_studio.models import Character, CharacterWorldview, CharacterArchetype

        added = []
        for nc in new_chars:
            name = nc.get("name", "").strip()
            if not name:
                continue
            if name in existing_names:
                logger.info("角色 '%s' 已存在，跳过", name)
                continue

            archetype_str = nc.get("archetype", "配角")
            try:
                archetype = CharacterArchetype(archetype_str)
            except ValueError:
                archetype = CharacterArchetype.SUPPORTING

            wv_data = nc.get("worldview", {})
            worldview = CharacterWorldview(
                known_facts=wv_data.get("known_facts", []),
                beliefs=wv_data.get("beliefs", []),
                knowledge_gaps=wv_data.get("knowledge_gaps", []),
                last_updated_chapter=wv_data.get("last_updated_chapter", chapter_number),
            )

            new_char = Character(
                name=name,
                archetype=archetype,
                personality=nc.get("personality", []),
                background=nc.get("background", ""),
                motivation=nc.get("motivation", ""),
                early_life=nc.get("early_life", []),
                debut_chapter=nc.get("debut_chapter", chapter_number),
                worldview=worldview,
                relationships=nc.get("relationships", {}),
            )

            # 写入 novel.characters
            if isinstance(chars, dict):
                chars[new_char.id] = new_char
            else:
                chars.append(new_char)

            added.append(name)
            logger.info("👤 新角色涌现: %s (%s)", name, archetype_str)

        # 保存
        try:
            ctx._storage.save_novel(novel)
        except Exception as e:
            logger.error("保存新角色失败: %s", e)

        ctx.set_output(self.name, {
            "has_new_characters": True,
            "new_characters": [{"name": n, "archetype": nc.get("archetype")} for n, nc in zip(added, new_chars) if n in added],
        })

        if added:
            logger.info("👤 角色涌现完成：新增 %d 个角色 — %s", len(added), ", ".join(added))

        return ctx

    def _parse_result(self, text: str) -> dict:
        """解析 LLM 返回的 JSON"""
        # 尝试提取 JSON 块
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
            # 尝试找第一个 { 到最后一个 }
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                logger.warning("无法解析角色涌现结果: %s", text[:200])
                return {"has_new_characters": False, "new_characters": []}
