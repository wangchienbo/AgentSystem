"""Novel Studio — 小说创作引擎（主控层）

整合大纲、剧情、世界观、角色 Agent、存储模块，
对外提供统一的创作接口。
"""
from __future__ import annotations

import json
import random
from datetime import datetime, UTC
from typing import Any

from app.novel_studio.models import (
    Novel, Character, Chapter, Outline, ChapterOutline,
    WorldSetting, SceneSetting, POVConstraint,
    CharacterArchetype, CharacterPersonality,
    StorySegment, GenerationRequest, GenerationResult,
)
from app.novel_studio.storage import NovelStorage
from app.novel_studio.character_agent import CharacterAgentRegistry, CharacterAgent


# ─── 预设角色模板 ───

DEFAULT_CHARACTER_ARCHETYPES = {
    "hero": {
        "name": "主角",
        "archetype": CharacterArchetype.HERO,
        "personality": ["勇敢", "正义", "坚定"],
        "speech_style": "语气坚定有力，用词简洁直接，有领导气质",
    },
    "heroine": {
        "name": "女主角",
        "archetype": CharacterArchetype.HEROINE,
        "personality": ["温柔", "聪慧", "坚强"],
        "speech_style": "语气温和但有力，言辞细腻，善于观察",
    },
    "villain": {
        "name": "反派",
        "archetype": CharacterArchetype.VILLAIN,
        "personality": ["狡诈", "冷酷", "深沉"],
        "speech_style": "语气阴冷，用词华丽但暗藏威胁，喜欢用隐喻",
    },
    "mentor": {
        "name": "导师",
        "archetype": CharacterArchetype.MENTOR,
        "personality": ["睿智", "沉稳", "神秘"],
        "speech_style": "语气平和，语言精炼，常用哲理和隐喻",
    },
}


class NovelStudioEngine:
    """小说创作引擎——核心控制器"""

    def __init__(
        self,
        storage: NovelStorage | None = None,
        agent_registry: CharacterAgentRegistry | None = None,
        model_router=None,
        llm_client=None,
    ):
        self._storage = storage or NovelStorage()
        self._agent_registry = agent_registry or CharacterAgentRegistry(model_router)
        self._model_router = model_router
        self._llm_client = llm_client
        self._current_novel_id: str | None = None

    # ──── 小说创建与管理 ────

    def create_novel(self, title: str, genre: str = "", author: str = "") -> Novel:
        """创建新小说"""
        novel = Novel(title=title, genre=genre, author=author)
        self._storage.save_novel(novel)
        self._current_novel_id = novel.id
        return novel

    def load_novel(self, novel_id: str) -> Novel | None:
        novel = self._storage.get_novel(novel_id)
        if novel:
            self._current_novel_id = novel_id
        return novel

    def list_novels(self) -> list[dict[str, Any]]:
        return self._storage.list_novels()

    def get_current_novel(self) -> Novel | None:
        if not self._current_novel_id:
            return None
        return self._storage.get_novel(self._current_novel_id)

    def get_novel(self, novel_id: str) -> Novel | None:
        return self._storage.get_novel(novel_id)

    # ──── 大纲模块 ────

    def create_outline(
        self,
        novel_id: str,
        title: str,
        summary: str = "",
        logline: str = "",
        three_act: dict | None = None,
    ) -> Outline | None:
        outline = Outline(title=title, summary=summary, logline=logline)
        if three_act:
            outline.three_act = three_act
        novel = self._storage.set_outline(novel_id, outline)
        return novel.outline if novel else None

    def add_chapter_outline(
        self, novel_id: str, number: int, title: str,
        summary: str = "", key_events: list[str] | None = None,
        characters: list[str] | None = None,
    ) -> ChapterOutline | None:
        ch = ChapterOutline(
            number=number, title=title, summary=summary,
            key_events=key_events or [],
            characters_involved=characters or [],
        )
        result = self._storage.add_chapter_outline(novel_id, ch)
        if result and result.outline:
            return result.outline.chapters[-1]
        return None

    # ──── 角色模块 ────

    def add_character(
        self, novel_id: str, name: str, archetype: CharacterArchetype = CharacterArchetype.SUPPORTING,
        personality: list[str] | None = None, background: str = "",
        speech_style: str = "", goal: str = "", flaw: str = "",
    ) -> Character | None:
        char = Character(
            name=name, archetype=archetype,
            personality=personality or [],
            background=background, speech_style=speech_style,
            goal=goal, flaw=flaw,
        )
        novel = self._storage.add_character(novel_id, char)
        if novel:
            # 注册到 Agent 中心
            self._agent_registry.register(char, client=self._llm_client)
            return char
        return None

    def add_default_characters(self, novel_id: str) -> list[Character]:
        """为小说添加默认角色模板"""
        chars = []
        for key, tmpl in DEFAULT_CHARACTER_ARCHETYPES.items():
            char = Character(
                name=tmpl["name"],
                archetype=tmpl["archetype"],
                personality=list(tmpl["personality"]),
                speech_style=tmpl["speech_style"],
            )
            novel = self._storage.add_character(novel_id, char)
            if novel:
                self._agent_registry.register(char, client=self._llm_client)
                chars.append(char)
        return chars

    # ──── 世界观模块 ────

    def create_world(
        self, novel_id: str, name: str, overview: str = "",
        rules: list[str] | None = None,
    ) -> WorldSetting | None:
        world = WorldSetting(name=name, overview=overview, rules=rules or [])
        novel = self._storage.set_world(novel_id, world)
        return novel.world if novel else None

    def add_scene(
        self, novel_id: str, name: str, location: str = "",
        description: str = "", atmosphere: str = "",
        lighting: str = "", temperature: str = "",
        sights: list[str] | None = None,
        sounds: list[str] | None = None,
        smells: list[str] | None = None,
        textures: list[str] | None = None,
        pov_character_id: str = "",
        pov_character_name: str = "",
        known_facts: list[str] | None = None,
        visible_objects: list[str] | None = None,
        hidden_objects: list[str] | None = None,
    ) -> SceneSetting | None:
        scene = SceneSetting(
            name=name, location=location,
            description=description, atmosphere=atmosphere,
            lighting=lighting, temperature=temperature,
            sights=sights or [],
            sounds=sounds or [],
            smells=smells or [],
            textures=textures or [],
            visible_objects=visible_objects or [],
            hidden_objects=hidden_objects or [],
            pov=POVConstraint(
                character_id=pov_character_id,
                character_name=pov_character_name,
                known_facts=known_facts or [],
            ),
        )
        novel = self._storage.add_scene(novel_id, scene)
        if novel and novel.world:
            return novel.world.scenes.get(scene.id)
        return None

    # ──── 剧情生成模块 ────

    async def generate_content(
        self,
        novel_id: str,
        instruction: str,
        chapter_number: int | None = None,
        style: str = "narration",
        scene_id: str = "",
    ) -> GenerationResult:
        """根据指令生成小说内容，支持场景视角约束"""
        novel = self._storage.get_novel(novel_id)
        if not novel:
            return GenerationResult(content="[小说未找到]")

        # ── 构建上下文 ──
        context_parts = [f"# {novel.title}\n"]

        # 场景驱动：如果指定了 scene_id，走有限视角
        scene = None
        if scene_id and novel.world and novel.world.scenes:
            scene = novel.world.scenes.get(scene_id)

        if scene:
            # ── 有限视角模式：只给 POV 角色能看到/知道的信息 ──
            pov = scene.pov
            pov_char = novel.characters.get(pov.character_id) if pov.character_id else None
            
            context_parts.append("## 场景（POV 有限视角）")
            context_parts.append(f"地点：{scene.location}")
            context_parts.append(f"光线：{scene.lighting}")
            context_parts.append(f"温度：{scene.temperature}")
            context_parts.append(f"天气：{scene.weather}")
            context_parts.append(f"氛围：{scene.atmosphere}")
            
            if scene.sights:
                context_parts.append(f"看到的：{'、'.join(scene.sights)}")
            if scene.sounds:
                context_parts.append(f"听到的：{'、'.join(scene.sounds)}")
            if scene.smells:
                context_parts.append(f"闻到的：{'、'.join(scene.smells)}")
            if scene.textures:
                context_parts.append(f"触摸到的：{'、'.join(scene.textures)}")
            if scene.visible_objects:
                context_parts.append(f"场景中的物品：{'、'.join(scene.visible_objects)}")

            # POV 角色信息
            if pov_char:
                context_parts.append(f"\n## POV 角色：{pov_char.name}")
                context_parts.append(f"性格：{'、'.join(pov_char.personality)}")
                context_parts.append(f"当前目标：{pov_char.goal}")
                context_parts.append(f"性格缺陷：{pov_char.flaw}")
                if pov_char.background:
                    context_parts.append(f"背景（角色自己记得的）：{pov_char.background[:200]}")
            
            if pov.known_facts:
                context_parts.append(f"\n角色当前知道的信息：")
                for fact in pov.known_facts:
                    context_parts.append(f"- {fact}")

            # 已有章节摘要（只取该角色在场的章节）
            if novel.chapters:
                context_parts.append("\n## 已有章节（该角色经历过的）")
                for ch in novel.chapters[-3:]:
                    context_parts.append(f"第{ch.number}章 {ch.title}: {ch.content[:200]}...")

        else:
            # ── 全知模式：传统的完整上下文 ──
            if novel.outline:
                context_parts.append(f"## 故事梗概\n{novel.outline.summary}\n")
            if novel.world:
                context_parts.append(f"## 世界观\n{novel.world.name}: {novel.world.overview}\n")

            # 已有章节摘要
            if novel.chapters:
                context_parts.append("## 已有章节摘要")
                for ch in novel.chapters[-5:]:
                    context_parts.append(f"第{ch.number}章 {ch.title}: {ch.content[:100]}...")

            # 角色信息
            if novel.characters:
                context_parts.append("## 角色")
                for c in novel.characters.values():
                    context_parts.append(f"- {c.name} ({c.archetype.value}): {'、'.join(c.personality)}")
                    if c.goal:
                        context_parts.append(f"  目标: {c.goal}")

        full_context = "\n".join(context_parts)

        # 构建 POV 约束规则
        pov_rules = ""
        if scene and scene.pov.character_id:
            pov_rules = f"""
## POV 写作纪律（必须遵守）
- 本场景视角锁定在「{scene.pov.character_name or scene.pov.character_id}」
- **只写这个角色能看到、听到、闻到、触摸到、感受到的**
- **不展示这个角色看不到的事物**（包括其他地方的动静、其他人的内心想法）
- **不解释这个角色不知道的信息**（不上背景课、不交代他不知道的历史）
- 角色对事物的理解有限——他可能误解、猜错、没注意到
- 通过他的五感和内心活动来呈现世界，而不是叙述者旁白"""

        system_prompt = f"""你是一位专业的小说创作助手。当前正在创作小说《{novel.title}》。

创作风格：{style}

规则：
1. 根据上下文和指令生成连贯的叙事内容
2. 保持角色性格一致
3. 注意情节逻辑
4. 语言优美但不浮夸{pov_rules}
5. 生成内容后返回格式为 JSON：
   {{"content": "生成的内容", "segments": [{{"type": "narration|dialogue|description", "content": "...", "pov_character": ""}}]}}
"""

        user_prompt = f"## 当前上下文\n{full_context}\n\n## 创作指令\n{instruction}"

        try:
            if self._llm_client:
                text, _ = self._llm_client.chat(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model=self._llm_client._config.model,
                    max_tokens=2000,
                    temperature=0.8,
                    stream=False,
                )
            elif self._model_router:
                client = self._model_router.get_client("architect", "complex")
                text, _ = client.chat(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model=client._config.model,
                    max_tokens=2000,
                    temperature=0.8,
                    stream=False,
                )
            else:
                return GenerationResult(content="[请配置 LLM 客户端]")

            content_text = text or ""

            # 尝试解析 JSON（如果 LLM 返回了 JSON 包裹的内容）
            segments = []
            try:
                import re
                json_match = re.search(r'\{.*"content".*\}', content_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if "content" in parsed:
                        content_text = parsed["content"]
                    for seg in parsed.get("segments", []):
                        segments.append(StorySegment(**seg))
            except (json.JSONDecodeError, Exception):
                pass

            return GenerationResult(content=content_text or "[生成失败]", segments=segments)

        except Exception as e:
            return GenerationResult(content=f"[生成出错: {str(e)}]")

    async def character_dialogue(
        self, novel_id: str, char1_name: str, char2_name: str,
        topic: str, setting: str = "",
    ) -> str:
        """生成两个角色之间的对话"""
        agent1 = self._agent_registry.get_by_name(char1_name)
        agent2 = self._agent_registry.get_by_name(char2_name)

        if not agent1 or not agent2:
            return f"[找不到角色: {char1_name if not agent1 else char2_name}]"

        context = f"你们正在{setting}。" if setting else ""
        context += f"话题：{topic}\n"
        context += "请根据你的性格自然地对话。先由你开始。"

        reply1 = await agent1.speak(context, target_audience=char2_name)
        agent2.add_to_history("user", f"{char1_name}说：{reply1}")
        reply2 = await agent2.speak(f"{char1_name}对你说：{reply1}", target_audience=char1_name)

        return f"**【{char1_name}】** {reply1}\n\n**【{char2_name}】** {reply2}"

    async def write_chapter(
        self, novel_id: str, chapter_number: int,
        style: str = "narration",
    ) -> Chapter | None:
        """生成指定章节的完整内容"""
        novel = self._storage.get_novel(novel_id)
        if not novel or not novel.outline:
            return None

        # 找到对应的大纲
        ch_outline = None
        for co in novel.outline.chapters:
            if co.number == chapter_number:
                ch_outline = co
                break
        if not ch_outline:
            return None

        # 构建指令
        instruction = f"请写第{chapter_number}章「{ch_outline.title}」\n"
        instruction += f"概要：{ch_outline.summary}\n"
        if ch_outline.key_events:
            instruction += f"关键事件：{'、'.join(ch_outline.key_events)}\n"
        if ch_outline.characters_involved:
            char_descs = []
            for cn in ch_outline.characters_involved:
                c = next((c for c in novel.characters.values() if c.name == cn), None)
                if c:
                    char_descs.append(f"{c.name}({'、'.join(c.personality)})")
            instruction += f"涉及角色：{'、'.join(char_descs)}\n"
        if ch_outline.pov_character:
            instruction += f"视角：{ch_outline.pov_character}\n"

        instruction += f"\n要求：写出一章完整的叙事内容，约{ch_outline.word_count_estimate}字。有场景描写、对话、动作。保持角色性格。结尾要让人想读下一章。"

        result = await self.generate_content(novel_id, instruction, chapter_number, style)

        chapter = Chapter(
            number=chapter_number,
            title=ch_outline.title,
            content=result.content,
            word_count=len(result.content),
            status="draft",
            outline_id=ch_outline.id,
        )

        self._storage.add_chapter(novel_id, chapter)
        return chapter

    # ──── 获取统计 ────

    def get_stats(self, novel_id: str) -> dict[str, Any]:
        return self._storage.get_stats(novel_id)

    def get_novel_full_report(self, novel_id: str) -> str:
        """生成小说完整状态报告"""
        novel = self._storage.get_novel(novel_id)
        if not novel:
            return "小说未找到"
        stats = self.get_stats(novel_id)
        lines = [
            f"📖 《{novel.title}》",
            f"类型：{novel.genre or '未设置'}",
            f"状态：{novel.status}",
            f"角色数：{stats['characters']}",
            f"计划章节：{stats['chapters_planned']}",
            f"已写章节：{stats['chapters_draft'] + stats['chapters_written']}",
            f"总字数：{stats['total_words']}",
            "=" * 30,
        ]
        if novel.characters:
            lines.append("\n角色列表：")
            for c in novel.characters.values():
                lines.append(f"  • {c.name}（{c.archetype.value}）—— {'、'.join(c.personality)}")
        if novel.world:
            lines.append(f"\n世界观：{novel.world.name}")
            lines.append(f"  概述：{novel.world.overview}")
            if novel.world.scenes:
                lines.append(f"  场景数：{len(novel.world.scenes)}")
        if novel.outline and novel.outline.chapters:
            lines.append("\n章节大纲：")
            for co in novel.outline.chapters:
                status_mark = "✅" if co.status == "done" else "📝"
                lines.append(f"  {status_mark} 第{co.number}章 {co.title}")
        return "\n".join(lines)
