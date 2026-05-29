"""Novel Studio — 小说创作引擎（主控层）

整合大纲、剧情、世界观、角色 Agent、存储模块，
对外提供统一的创作接口。
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, UTC
from typing import Any

from app.novel_studio.models import (
    Novel, Character, Chapter, Outline, ChapterOutline,
    WorldSetting, SceneSetting, POVConstraint,
    CharacterArchetype, CharacterPersonality,
    StorySegment, GenerationRequest, GenerationResult,
    Memory, WorldEvent, TickResult, CharacterPerception,
)
from app.novel_studio.storage import NovelStorage
from app.novel_studio.character_agent import CharacterAgentRegistry, CharacterAgent
from app.novel_studio.scene_manager import SceneManager
from app.novel_studio.world_module import WorldModule
from app.novel_studio.narrative_engine import NarrativeEngine


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

logger = logging.getLogger(__name__)


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
        # ── 演化引擎 ──
        self._scene_manager = SceneManager()
        self._world_module = WorldModule()
        self._narrative = NarrativeEngine()
        self._is_evolving: bool = False

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
        self, novel_id: str, name: str, archetype: str | CharacterArchetype = CharacterArchetype.SUPPORTING,
        personality: list[str] | None = None, background: str = "",
        speech_style: str = "", goal: str = "", flaw: str = "",
        attributes: dict[str, int] | None = None,
        special_ability: str = "",
    ) -> Character | None:
        from app.novel_studio.models import Attributes
        # 统一 archetype 为枚举
        if isinstance(archetype, str):
            try:
                archetype_enum = CharacterArchetype(archetype)
            except ValueError:
                archetype_enum = CharacterArchetype.SUPPORTING
        else:
            archetype_enum = archetype
        
        # 按原型初始化属性
        attr_data = attributes or archetype_enum.default_attributes()
        char_attrs = Attributes(**{k: v for k, v in attr_data.items() if hasattr(Attributes, k)})
        
        char = Character(
            name=name, archetype=archetype_enum,
            personality=personality or [],
            background=background, speech_style=speech_style,
            goal=goal, flaw=flaw,
            attributes=char_attrs,
            special_ability=special_ability,
        )
        novel = self._storage.add_character(novel_id, char)
        if novel:
            # 注册到 Agent 中心
            self._agent_registry.register(char)
            return char
        return None

    def update_character(self, novel_id: str, char_id: str, **updates) -> Character | None:
        """更新角色属性（委托 storage）"""
        novel = self._storage.update_character(novel_id, char_id, updates)
        if novel and char_id in novel.characters:
            return novel.characters[char_id]
        return None

    def remove_character(self, novel_id: str, char_id: str) -> bool:
        """删除角色"""
        novel = self._storage.remove_character(novel_id, char_id)
        if novel:
            self._agent_registry.unregister(char_id)
            return True
        return False

    def remove_scene(self, novel_id: str, scene_id: str) -> bool:
        """删除场景"""
        novel = self._storage.remove_scene(novel_id, scene_id)
        return novel is not None

    def add_default_characters(self, novel_id: str) -> list[Character]:
        """为小说添加默认角色模板"""
        from app.novel_studio.models import Attributes
        chars = []
        for key, tmpl in DEFAULT_CHARACTER_ARCHETYPES.items():
            arch_name = tmpl["archetype"]
            if isinstance(arch_name, str):
                arch_enum = CharacterArchetype(arch_name)
            else:
                arch_enum = arch_name
            attr_data = arch_enum.default_attributes()
            char = Character(
                name=tmpl["name"],
                archetype=arch_enum,
                personality=list(tmpl["personality"]),
                speech_style=tmpl["speech_style"],
                attributes=Attributes(**attr_data),
            )
            novel = self._storage.add_character(novel_id, char)
            if novel:
                self._agent_registry.register(char)
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
                text = ""
                for attempt in range(3):
                    text, _ = self._llm_client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                        model=self._llm_client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
                    if text:
                        break
                    if attempt < 2:
                        import time
                        logger.warning(f"LLM returned empty (generate_content attempt {attempt+1}), retrying...")
                        time.sleep(1.5)
            elif self._model_router:
                client = self._model_router.get_client("architect", "complex")
                text = ""
                for attempt in range(3):
                    text, _ = client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                        model=client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
                    if text:
                        break
                    if attempt < 2:
                        import time
                        logger.warning(f"LLM(router) returned empty (generate_content attempt {attempt+1}), retrying...")
                        time.sleep(1.5)
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

    # ──── 世界演化模块 ────

    def init_evolution(self, novel_id: str, resume: bool = True) -> dict[str, Any]:
        """从已有小说数据初始化演化引擎"""
        # 先清空旧状态（防止跨小说污染）
        self._clear_evolution_state()

        # 如果要求恢复且存在存档
        if resume:
            char_states = self._storage.list_character_states(novel_id)
            evo_state = self._storage.load_evolution_state(novel_id)
            if char_states and evo_state:
                return self.load_evolution_state(novel_id)

        # 否则从头初始化
        novel = self._storage.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "小说未找到"}

        # 导入世界观
        if novel.world:
            self._world_module = WorldModule(novel.world)
            for sid, scene in novel.world.scenes.items():
                self._scene_manager.add_scene(scene)

        # 注册角色 Agent
        for cid, char in novel.characters.items():
            agent = self._agent_registry.register(char)
            if char.current_scene and char.current_scene in self._scene_manager._scenes:
                self._scene_manager.place_character(char, char.current_scene)

        self._current_novel_id = novel_id
        self._is_evolving = True
        return {
            "success": True,
            "novel_id": novel_id,
            "characters": len(novel.characters),
            "scenes": len(novel.world.scenes) if novel.world else 0,
        }

    def _clear_evolution_state(self) -> None:
        """清空当前演化状态"""
        self._agent_registry = CharacterAgentRegistry(model_router=self._model_router)
        self._scene_manager = SceneManager()
        self._world_module = WorldModule()
        self._narrative = NarrativeEngine()
        self._current_novel_id = None
        self._is_evolving = False

    def place_character_in_scene(self, char_name: str, scene_name: str) -> dict[str, Any]:
        """将角色放入场景"""
        agent = self._agent_registry.get_by_name(char_name)
        if not agent:
            return {"error": f"角色 {char_name} 不存在"}

        scene = None
        for sid, s in self._scene_manager._scenes.items():
            if s.name == scene_name:
                scene = s
                break
        if not scene:
            return {"error": f"场景 {scene_name} 不存在"}

        self._scene_manager.place_character(agent.character, scene.id)
        return {"success": True, "moved": f"{char_name} → {scene_name}"}

    def add_world_event(
        self, title: str, description: str,
        event_type: str = "", public: bool = True,
    ) -> dict[str, Any]:
        """添加世界大事件"""
        event = WorldEvent(
            timestamp=self._world_module.current_time,
            title=title,
            description=description,
            event_type=event_type,
            public_knowledge=public,
        )
        self._world_module.add_event(event)
        return {"event_id": event.id, "at_tick": self._world_module.current_time}

    def tick(self) -> dict[str, Any]:
        """执行一次世界演化 tick

        每个 tick：
        1. 时间 +1，场景状态变化
        2. 构建世界快照
        3. 对每个角色：一次 LLM 调用完成感知+决策
        """
        if not self._is_evolving:
            return {"error": "演化未初始化，请先调用 init_evolution"}

        self._world_module.advance_time()
        current_tick = self._world_module.current_time
        actions_log = []
        memories_added = 0

        # 场景随时间变化
        self._tick_scene_dynamics()

        # 构建世界快照（一次就够了）
        world_snapshot = self._build_world_snapshot(current_tick)

        # 遍历所有场景
        for scene_id in self._scene_manager._scenes:
            occupants = self._scene_manager.get_occupants(scene_id)
            if not occupants:
                continue

            scene = self._scene_manager._scenes.get(scene_id)
            scene_context = f"{scene.name if scene else '未知场景'}（t={current_tick}）"

            for char in occupants:
                agent = self._agent_registry.get(char.id)
                if not agent:
                    continue

                # 感知场景
                perception = self._scene_manager.get_perception(char.id)

                # ⭐ 单次调用：感知过滤 + 决策
                decision = agent.decide_with_world(
                    perception=perception,
                    scene_context=scene_context,
                    world_snapshot=world_snapshot,
                )

                # 解析感知、行动、对话
                perception_text = decision.get("perception", "")
                action_text = decision.get("action", "沉默观望")
                dialogue_text = decision.get("dialogue", "")

                action_desc = action_text
                if dialogue_text and dialogue_text != "沉默":
                    action_desc += f"，说道：{dialogue_text[:100]}"

                # 去重：如果和上一条记忆太像，降低重要度
                importance = 0.5
                if dialogue_text and dialogue_text != "沉默":
                    importance = 0.7
                if agent._memories:
                    last = agent._memories[-1].content
                    # 简单去重：检查内容重叠度
                    overlap = len(set(last[:40]) & set(action_desc[:40])) / max(len(set(action_desc[:20])), 1)
                    if overlap > 0.7:
                        importance = 0.2  # 重复行动，低重要度
                        if current_tick % 3 == 0:
                            action_desc += "（环顾四周，确认环境没有变化）"

                # 写入角色记忆
                tags = ["tick_action"]
                if perception.visible_chars:
                    tags.append("social")
                if perception_text:
                    # 把感知也记入记忆
                    agent.add_memory(
                        content=perception_text[:100],
                        scene_id=scene_id,
                        importance=0.3,
                        tags=["perception"],
                    )

                agent.add_memory(
                    content=action_desc,
                    scene_id=scene_id,
                    participants=perception.visible_chars,
                    importance=importance,
                    tags=tags,
                )
                memories_added += 1

                # 叙事引擎观察
                self._narrative.observe_action(
                    tick=current_tick,
                    char_name=char.name,
                    action=action_desc,
                    scene_id=scene_id,
                )

                actions_log.append({
                    "char": char.name,
                    "scene": scene.name if scene else "?",
                    "perception": perception_text,
                    "action": action_text,
                    "dialogue": dialogue_text if dialogue_text != "沉默" else "",
                })

        # 生成 tick 摘要
        if actions_log:
            summary_parts = [f"t={current_tick}"]
            for a in actions_log:
                line = f"{a['char']}在{a['scene']}{a['action']}"
                if a['dialogue']:
                    line += f"，说「{a['dialogue'][:80]}」"
                summary_parts.append(line)
            summary = "\n".join(summary_parts[:5])
        else:
            summary = f"t={current_tick}：无事发生"

        # 场景切换
        self._apply_scene_transitions()

        return {
            "tick": current_tick,
            "actions": actions_log,
            "new_memories": memories_added,
            "summary": summary,
        }

    # ── 场景动力（随时间变化） ──

    def _tick_scene_dynamics(self) -> None:
        """每个 tick 让场景状态产生微小变化"""
        current_tick = self._world_module.current_time
        time_of_day = current_tick % 4
        time_labels = {0: "清晨", 1: "正午", 2: "傍晚", 3: "深夜"}

        for scene in self._scene_manager._scenes.values():
            if time_of_day == 0:
                scene.mood = "苏醒"
                scene.sounds = [s for s in scene.sounds if s != "蟋蟀声"]
                if "鸟鸣" not in scene.sounds:
                    scene.sounds.append("鸟鸣")
            elif time_of_day == 2:
                scene.mood = "渐暗"
                if "蟋蟀声" not in scene.sounds:
                    scene.sounds.append("蟋蟀声")
            elif time_of_day == 3:
                scene.mood = "深夜寂静"

    # ── 场景切换（从角色行动解析） ──

    def _detect_scene_transitions(self) -> list[dict[str, str]]:
        """检查角色行动中是否包含场景切换意图"""
        transitions = []
        scene_names = {s.name: sid for sid, s in self._scene_manager._scenes.items()}
        move_keywords = ["走向", "前往", "进入", "离开", "返回", "穿过", "来到", "迈步向"]

        for char_id, agent in self._agent_registry._agents.items():
            if not agent._memories:
                continue
            last_action = agent._memories[-1].content.lower()
            for keyword in move_keywords:
                if keyword in last_action:
                    idx = last_action.find(keyword)
                    for sname, sid in scene_names.items():
                        if sname.lower() in last_action[idx:]:
                            current_sid = self._scene_manager.get_scene_for_char(char_id)
                            if current_sid and current_sid != sid:
                                transitions.append({
                                    "char_id": char_id,
                                    "char_name": agent.name,
                                    "from": current_sid,
                                    "to": sid,
                                    "to_name": sname,
                                })
                            break
        return transitions

    def _apply_scene_transitions(self) -> None:
        """执行场景切换"""
        for tr in self._detect_scene_transitions():
            agent = self._agent_registry.get(tr["char_id"])
            if agent:
                self._scene_manager.place_character(agent.character, tr["to"])
                agent.add_memory(
                    content=f"走向了{tr['to_name']}",
                    importance=0.8,
                    tags=["scene_transition"],
                )

    def batch_tick(self, count: int = 5) -> list[dict[str, Any]]:
        """批量执行多次 tick"""
        results = []
        for _ in range(count):
            result = self.tick()
            results.append(result)
        return results

    # ── 世界快照（给能力感知过滤用） ──

    def _build_world_snapshot(self, current_tick: int) -> str:
        """构建当前世界全貌（所有场景/角色/事件），给角色能力过滤用"""
        parts = [f"世界时间：t={current_tick}\n"]

        # 大事件
        event_summary = self._world_module.get_event_summary()
        if event_summary:
            parts.append(f"【世界事件】\n{event_summary}\n")

        # 所有场景
        parts.append("【场景状态】")
        for sid, scene in self._scene_manager._scenes.items():
            occupants = self._scene_manager.get_occupants(sid)
            char_names = [c.name for c in occupants]
            occ_str = "，".join(char_names) if char_names else "无人"
            parts.append(f"  {scene.name}：{occ_str}")
            if scene.sounds:
                parts.append(f"    可听到：{'，'.join(scene.sounds[:2])}")
        parts.append("")

        # 其他角色的最近行动（从叙事观察中取）
        recent_obs = self._narrative.get_recent_observations(10)
        if recent_obs:
            parts.append("【最新动态】")
            seen = set()
            for obs in reversed(recent_obs):
                key = f"{obs.tick}_{obs.char_name}"
                if key not in seen:
                    parts.append(f"  t={obs.tick} {obs.char_name}在{obs.scene_id}: {obs.action[:60]}")
                    seen.add(key)

        return "\n".join(parts)

    def write_narrative_chapter(self) -> dict[str, Any]:
        """从演化记录调用模型写实际章节正文"""
        novel = self.get_current_novel()
        if not novel:
            return {"error": "没有加载小说"}

        observations = self._narrative.get_recent_observations(20)
        if not observations:
            return {"error": "没有观察记录，请先运行 tick"}

        # 构建章节 Prompt
        obs_text = self._narrative.summarize_interactions(observations)
        world_context = self._world_module.get_world_context()
        event_summary = self._world_module.get_event_summary()

        scene_summaries = []
        for sid in self._scene_manager._scenes:
            scene_summaries.append(self._scene_manager.get_scene_summary(sid))

        ch_num = len(novel.chapters) + 1

        prompt = f"""你是一位小说作家。以下是从角色演化中记录的事件，请将其写成连贯的叙事章节。

这是全书的第 {ch_num} 章。

世界背景：
{world_context}

{event_summary}

场景状态：
{' | '.join(scene_summaries)}

角色事件记录：
{obs_text}

要求：
1. 这是第 {ch_num} 章的开篇叙事。**
2. 用第三人称叙事，语言要有文学感
3. 保留角色的性格和语气
4. 不需暴露角色的内心想法——通过行动和对话展现
5. 语言流畅自然
6. 先给这一章起一个精炼的章节名（4~10个字），然后写正文
7. 输出格式：第一行为章节名，第二行空行，第三行起为正文。章节名不要加任何前缀或标点。"""

        try:
            if self._model_router:
                client = self._model_router.get_client("architect", "complex")
                text, _ = client.chat(
                    [{"role": "system", "content": "你是一位小说作家。"},
                     {"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.8,
                    stream=False,
                )
                content = text or "（生成失败）"
            else:
                content = f"（请配置 LLM 客户端后使用。原始观察：{obs_text[:200]}）"

            # 解析章节名：第一行或前几行可能含标题
            chapter_title = ""
            chapter_content = content
            import re as _re
            first_line = content.strip().split("\n")[0].strip()
            # 匹配: ## 第X章　标题名 / 第X章 标题名 / ## 标题名
            m = _re.search(r'[#　\s]*(?:第\d+章[　\s]+)?(.+?)$', first_line)
            if m:
                candidate = m.group(1).strip().strip("#").strip("《》").strip()
                if 2 <= len(candidate) <= 20 and "。" not in candidate:
                    chapter_title = candidate
                    # 去掉正文中的标题行
                    rest_lines = content.strip().split("\n")
                    chapter_content = "\n".join(rest_lines[1:]).strip()
                    # 如果第二行是空行也跳过
                    if chapter_content.startswith("\n"):
                        chapter_content = chapter_content.lstrip("\n")

            ch_num = len(novel.chapters) + 1
            from app.novel_studio.models import Chapter
            full_title = f"第{ch_num}章　{chapter_title}" if chapter_title else f"第{ch_num}章"
            chapter = Chapter(
                number=ch_num,
                title=full_title,
                content=chapter_content,
                word_count=len(chapter_content),
                status="draft",
            )
            novel.chapters.append(chapter)
            self._storage.save_novel(novel)
            self._narrative.clear_observations(keep_last=5)

            return {
                "success": True,
                "chapter_number": ch_num,
                "content": content,
                "word_count": len(content),
            }
        except Exception as e:
            return {"error": f"生成失败: {str(e)}"}

    def rename_chapters(self) -> dict[str, Any]:
        """逐章调用 LLM 为无标题章节生成章节名，每次只读一章"""
        novel = self.get_current_novel()
        if not novel:
            return {"error": "没有加载小说"}

        renamed = []
        skipped = []

        for ch in novel.chapters:
            title = ch.title or ""
            # 已有章节名（含分隔符"　"或"·"）→ 跳过
            if "　" in title or "·" in title:
                skipped.append(ch.number)
                continue

            # 只读本章内容，截取前 800 字做摘要
            excerpt = ch.content[:800] if ch.content else ""
            if not excerpt.strip():
                skipped.append(ch.number)
                continue

            prompt = f"""以下是小说的第{ch.number}章正文（前800字）：

{excerpt}

请根据正文内容，给这一章起一个精炼的章节名（4~10个字）。
要求：
1. 紧扣本章核心事件或意象
2. 有文学感，不要太直白
3. 只输出章节名，不要加任何前缀、标点、解释"""

            try:
                if self._model_router:
                    client = self._model_router.get_client("architect", "complex")
                    text, _ = client.chat(
                        [{"role": "system", "content": "你是一位小说编辑，擅长起章节标题。"},
                         {"role": "user", "content": prompt}],
                        max_tokens=50,
                        temperature=0.7,
                        stream=False,
                    )
                    name = (text or "").strip().strip("#").strip("《》").strip()
                    # 验证：2~20字，不含句号
                    if 2 <= len(name) <= 20 and "。" not in name:
                        ch.title = f"第{ch.number}章　{name}"
                        renamed.append({"number": ch.number, "title": ch.title})
                    else:
                        skipped.append(ch.number)
                else:
                    skipped.append(ch.number)
            except Exception:
                skipped.append(ch.number)

        self._storage.save_novel(novel)
        return {
            "success": True,
            "renamed": renamed,
            "skipped_count": len(skipped),
            "renamed_count": len(renamed),
        }

    def get_evolution_state(self) -> dict[str, Any]:
        """获取演化状态"""
        scenes_info = self._scene_manager.list_scenes()
        agents_info = self._agent_registry.list_agents()
        return {
            "evolving": self._is_evolving,
            "current_tick": self._world_module.current_time,
            "scenes": scenes_info,
            "characters": agents_info,
            "observation_count": len(self._narrative._observations),
            "events": len(self._world_module._timeline),
        }

    def save_evolution_state(self, novel_id: str) -> dict[str, Any]:
        """保存完整演化状态到 storage（含角色记忆、场景状态、世界时间线）"""
        # 1. 保存每个角色的 Agent 状态（含记忆）
        for cid, agent in self._agent_registry._agents.items():
            agent_data = agent.to_serializable()
            self._storage.save_character_state(novel_id, agent_data)

        # 2. 保存演化上下文
        evo_state = {
            "current_tick": self._world_module.current_time,
            "scene_manager": {
                "locations": dict(self._scene_manager._locations),
                "occupants": {
                    sid: list(chars.keys())
                    for sid, chars in self._scene_manager._occupants.items()
                },
            },
            "world_module": self._world_module.to_serializable(),
            "narrative_engine": self._narrative.to_serializable(),
        }
        self._storage.save_evolution_state(novel_id, evo_state)

        # 3. 同步角色位置回 Novel
        novel = self._storage.get_novel(novel_id)
        if novel:
            for cid, char in novel.characters.items():
                agent = self._agent_registry.get(cid)
                if agent:
                    char.current_scene = agent.character.current_scene
            self._storage.save_novel(novel)

        return {"success": True, "tick": self._world_module.current_time}

    def load_evolution_state(self, novel_id: str) -> dict[str, Any]:
        """从 storage 恢复完整演化状态"""
        novel = self._storage.get_novel(novel_id)
        if not novel:
            return {"error": "小说未找到"}

        # 1. 恢复场景和世界观
        if novel.world:
            self._world_module = WorldModule(novel.world)
            for sid, scene in novel.world.scenes.items():
                self._scene_manager.add_scene(scene)

        # 2. 恢复角色 Agent（含记忆）
        char_state_ids = self._storage.list_character_states(novel_id)
        restored = 0
        for cid in char_state_ids:
            agent_data = self._storage.load_character_state(novel_id, cid)
            if agent_data:
                agent = CharacterAgent.from_serializable(agent_data, model_router=self._model_router)
                self._agent_registry._agents[cid] = agent
                restored += 1
                # 恢复位置
                if agent.character.current_scene:
                    self._scene_manager.place_character(agent.character, agent.character.current_scene)

        # 3. 恢复演化上下文
        evo_state = self._storage.load_evolution_state(novel_id)
        if evo_state:
            self._world_module._current_time = evo_state.get("current_tick", 0)
            wm_data = evo_state.get("world_module", {})
            if wm_data:
                self._world_module = WorldModule.from_serializable(wm_data)
            ne_data = evo_state.get("narrative_engine", {})
            if ne_data:
                self._narrative = NarrativeEngine.from_serializable(ne_data)
            # 恢复场景位置
            sm_data = evo_state.get("scene_manager", {})
            for cid, sid in sm_data.get("locations", {}).items():
                agent = self._agent_registry.get(cid)
                if agent and sid in self._scene_manager._scenes:
                    self._scene_manager.place_character(agent.character, sid)

        self._current_novel_id = novel_id
        self._is_evolving = True
        return {
            "success": True,
            "tick": self._world_module.current_time,
            "characters_restored": restored,
        }

    def export_evolution_log(self) -> str:
        """导出演化日志"""
        obs = self._narrative.get_recent_observations(50)
        if not obs:
            return "无演化记录"

        lines = [f"世界演化日志（t=0 ~ t={self._world_module.current_time}）", "=" * 40]
        for o in obs:
            lines.append(f"t={o.tick} {o.char_name}: {o.action}")
        return "\n".join(lines)

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

    def export_novel_directory(self, novel_id: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
        """按目录结构导出小说（含 TOC.md、分章文件、大纲、世界观）"""
        nid = novel_id or self._current_novel_id
        if not nid:
            return {"error": "没有指定小说 ID"}

        from pathlib import Path
        out = Path(output_dir) if output_dir else None
        return self._storage.export_to_directory(nid, out)
