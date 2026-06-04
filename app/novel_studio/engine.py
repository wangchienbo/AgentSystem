"""Novel Studio — 小说创作引擎（主控层）

整合大纲、剧情、世界观、角色 Agent、存储模块，
对外提供统一的创作接口。
"""
from __future__ import annotations

import asyncio
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
        context_center=None,
    ):
        self._storage = storage or NovelStorage()
        self._context_center = context_center
        self._agent_registry = agent_registry or CharacterAgentRegistry(model_router, context_center=self._context_center)
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

    def update_custom_prompt(self, novel_id: str, custom_prompt: str) -> Novel | None:
        novel = self._storage.get_novel(novel_id)
        if not novel:
            return None
        novel.custom_prompt = custom_prompt
        self._storage.save_novel(novel)
        return novel

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

    def add_chapter(self, novel_id: str, title: str, content: str = "", number: int | None = None) -> Chapter | None:
        """创建空白章节"""
        novel = self._storage.get_novel(novel_id)
        if novel is None:
            return None
        next_number = number or (max((c.number for c in novel.chapters), default=0) + 1)
        chapter = Chapter(
            number=next_number,
            title=title,
            content=content,
            word_count=len(content),
            status="draft",
        )
        result = self._storage.add_chapter(novel_id, chapter)
        return chapter if result else None

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
            # 注册到 Agent 中心（附带 novel_id 用于 ContextCenter 会话）
            self._agent_registry.register(char, novel_id=novel_id)
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
            self._agent_registry.remove(char_id)
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
                self._agent_registry.register(char, novel_id=novel_id)
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

    # ──── 剧情生成模块（已迁移到 Pipeline 多 Agent 管道） ────

    # 旧 generate_content / write_chapter / character_dialogue 已废弃移除
    # ──── Pipeline: 多 Agent 管道生成 ────

    async def generate_next_chapter(
        self,
        novel_id: str,
        template: str = "write_next_chapter",
        progress_callback=None,
    ) -> dict:
        """使用 Pipeline 多角色 Agent 管道生成下一章

        核心特性：
        - 每个角色独立 Agent（独立 LLM 调用）
        - 信息隔离：角色只知道自己能感知到的
        - 模块化：5 步管道（规划→场景→行为→叙事→记忆）

        Returns:
            dict: {success, chapter_number, title, content, steps, ...}
        """
        from app.novel_studio.pipeline import (
            PipelineContext,
            get_orchestrator,
        )
        from app.novel_studio.pipeline.orchestrator import PipelineOrchestrator

        novel = self._storage.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "小说未找到"}

        # 预热角色 Agent（如果未注册）
        if novel.characters:
            for cid, char in novel.characters.items():
                if not self._agent_registry.get(cid):
                    self._agent_registry.register(char, novel_id=novel_id)

        # 预热 SceneManager（如果有场景）
        self._scene_manager = SceneManager()
        if novel.world and novel.world.scenes:
            for sid, scene in novel.world.scenes.items():
                self._scene_manager.add_scene(scene)

        # 构建 PipelineContext
        ctx = PipelineContext(
            novel_id=novel_id,
            storage=self._storage,
            agent_registry=self._agent_registry,
            scene_manager=self._scene_manager,
            world_module=self._world_module,
            llm_client=self._llm_client,
            model_router=self._model_router,
        )

        # 执行管道
        orch = get_orchestrator()
        try:
            ctx = await orch.run(template, ctx=ctx, progress_callback=progress_callback)
        except Exception as e:
            logger.exception("Pipeline 执行失败")
            return {
                "success": False,
                "error": str(e),
                "steps": ctx.get_progress(),
            }

        narrative_output = ctx.get_output("narrative")
        plan_output = ctx.get_output("chapter_plan")

        return {
            "success": True,
            "chapter_number": (narrative_output or {}).get("chapter_number",
                (plan_output or {}).get("chapter_number", 0)),
            "title": (narrative_output or {}).get("title",
                (plan_output or {}).get("title", "")),
            "content": (narrative_output or {}).get("content", ""),
            "word_count": (narrative_output or {}).get("word_count", 0),
            "steps": ctx.get_progress(),
            "actions": ctx.get_output("character_action", {}).get("actions", []),
        }

    # ────·─── 共享管道辅助 ────·───

    def _prepare_pipeline_context(self, novel_id: str, template: str):
        """准备管道上下文，返回 (ctx, orch, step_names)，shared by stream & task runners"""
        from app.novel_studio.pipeline import (
            PipelineContext,
            get_orchestrator,
        )

        novel = self._storage.get_novel(novel_id)
        if not novel:
            raise ValueError("小说未找到")

        # 预热角色 Agent
        if novel.characters:
            for cid, char in novel.characters.items():
                if not self._agent_registry.get(cid):
                    self._agent_registry.register(char, novel_id=novel_id)

        # 设置小说上下文（供后续 register 调用使用）
        self._agent_registry.set_novel_context(novel_id)

        # 预热 SceneManager — 使用 sync 而非重建，保持累积状态
        if novel.world and novel.world.scenes:
            self._scene_manager.sync_scenes(novel.world.scenes)
        # 清除上一轮的事件日志
        self._scene_manager.clear_events()

        # 构建 PipelineContext
        ctx = PipelineContext(
            novel_id=novel_id,
            storage=self._storage,
            agent_registry=self._agent_registry,
            scene_manager=self._scene_manager,
            world_module=self._world_module,
            context_center=self._context_center,
            llm_client=self._llm_client,
            model_router=self._model_router,
        )

        orch = get_orchestrator()
        step_names = orch.get_step_names(template)
        return ctx, orch, step_names

    async def run_next_chapter_task(
        self,
        novel_id: str,
        template: str,
        task: "GenerateTask",
    ):
        """后台执行管道，结果写入 GenerateTask（不依赖 HTTP 连接存活）

        - 在 task.events 中缓冲每一步事件
        - task.status: pending → running → complete | error
        - 任何异常写入 task.error，不抛出
        """
        from app.novel_studio.pipeline import get_orchestrator
        from app.novel_studio.task_manager import GenerateTask
        import asyncio, json

        task.status = "running"

        try:
            ctx, orch, step_names = self._prepare_pipeline_context(novel_id, template)
        except ValueError as e:
            task.status = "error"
            task.error = str(e)
            task.events.append({"type": "error", "message": str(e)})
            return

        # step_waiting
        for name in step_names:
            module = orch._modules.get(name)
            desc = module.description if module else name
            task.events.append({
                "type": "step_waiting",
                "module": name,
                "description": desc,
                "status": "waiting",
            })

        # 角色事件小队列
        char_queue = asyncio.Queue()

        def character_callback(result_dict, done_count, total_count):
            char_queue.put_nowait({
                "type": "character_done",
                "character": result_dict.get("character", "?"),
                "action": result_dict.get("行动") or result_dict.get("action", ""),
                "dialogue": result_dict.get("对话") or result_dict.get("dialogue", ""),
                "inner": result_dict.get("内心") or result_dict.get("inner", ""),
                "progress": {"done": done_count, "total": total_count},
            })

        ctx._character_decided_callback = character_callback

        # 逐步骤执行
        try:
            for idx, name in enumerate(step_names):
                module = orch._modules.get(name)
                if module is None:
                    task.events.append({"type": "error", "message": f"模块未注册: {name}"})
                    task.status = "error"
                    return

                # step_start
                task.events.append({
                    "type": "step_start", "module": name,
                    "description": module.description if module else name,
                    "status": "running",
                })

                try:
                    ctx = await module.execute(ctx)

                    if module.modifies_storage:
                        ctx.refresh_novel()

                    # 排空角色事件
                    while not char_queue.empty():
                        task.events.append(char_queue.get_nowait())

                    task.events.append({
                        "type": "step_done", "module": name,
                        "status": "done", "summary": module.description,
                    })

                except Exception as e:
                    import traceback as _tb
                    ctx.record_step(name, "error", f"{module.description}失败: {str(e)}")
                    task.events.append({"type": "error", "message": f"管道执行失败: {str(e)}"})
                    task.status = "error"
                    return

            # 取最终输出
            narrative_output = ctx.get_output("narrative")
            plan_output = ctx.get_output("chapter_plan")
            actions = ctx.get_output("character_action", {}).get("actions", [])

            task.result = {
                "chapter_number": (narrative_output or {}).get("chapter_number",
                    (plan_output or {}).get("chapter_number", 0)),
                "title": (narrative_output or {}).get("title",
                    (plan_output or {}).get("title", "")),
                "content": (narrative_output or {}).get("content", ""),
                "word_count": (narrative_output or {}).get("word_count", 0),
                "steps": ctx.get_progress(),
                "actions": actions,
            }
            task.events.append({"type": "complete", **task.result})
            task.status = "complete"

        except Exception as e:
            import traceback as _tb
            task.error = f"管道执行失败: {str(e)}"
            task.events.append({"type": "error", "message": task.error})
            task.status = "error"

    async def generate_next_chapter_stream(
        self,
        novel_id: str,
        template: str = "write_next_chapter",
    ):
        """流式生成下一章（异步生成器，每一步 yield 一个 JSON 事件）

        Events:
            {"type":"step_start","module":"...","description":"📋 章节规划"}
            {"type":"step_done","module":"...","description":"...","summary":"..."}
            {"type":"character_done","character":"...","action":"...","dialogue":"...","inner":"...","progress":{"done":2,"total":5}}
            {"type":"complete","chapter_number":6,"title":"...","word_count":3136,"content":"...","steps":[...],"actions":[...]}
            {"type":"error","message":"..."}
        """
        from app.novel_studio.pipeline import (
            PipelineContext,
            get_orchestrator,
        )
        from app.novel_studio.pipeline.orchestrator import PipelineOrchestrator

        try:
            ctx, orch, step_names = self._prepare_pipeline_context(novel_id, template)
        except ValueError as e:
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"
            return

        # 1️⃣ 立即 yield 所有步骤的 waiting 事件
        for name in step_names:
            module = orch._modules.get(name)
            desc = module.description if module else name
            yield json.dumps({
                "type": "step_waiting",
                "module": name,
                "description": desc,
                "status": "waiting",
            }, ensure_ascii=False) + "\n"

        # 角色事件小队列（character_action 步骤中使用）
        char_queue = asyncio.Queue()

        def character_callback(result_dict, done_count, total_count):
            char_queue.put_nowait({
                "type": "character_done",
                "character": result_dict.get("character", "?"),
                "action": result_dict.get("行动") or result_dict.get("action", ""),
                "dialogue": result_dict.get("对话") or result_dict.get("dialogue", ""),
                "inner": result_dict.get("内心") or result_dict.get("inner", ""),
                "progress": {"done": done_count, "total": total_count},
            })

        ctx._character_decided_callback = character_callback

        # 2️⃣ 逐步骤执行管道，直接 yield event
        #    逐步骤 yield event，不依赖 Queue
        try:
            for idx, name in enumerate(step_names):
                module = orch._modules.get(name)
                if module is None:
                    yield json.dumps({
                        "type": "error",
                        "message": f"模块未注册: {name}",
                    }, ensure_ascii=False) + "\n"
                    return

                # step_start
                yield json.dumps({
                    "type": "step_start",
                    "module": name,
                    "description": module.description if module else name,
                    "status": "running",
                }, ensure_ascii=False) + "\n"

                try:
                    ctx = await module.execute(ctx)

                    if module.modifies_storage:
                        ctx.refresh_novel()

                    # 排空角色事件
                    while not char_queue.empty():
                        ev = char_queue.get_nowait()
                        yield json.dumps(ev, ensure_ascii=False) + "\n"

                    # step_done
                    yield json.dumps({
                        "type": "step_done",
                        "module": name,
                        "status": "done",
                        "summary": module.description,
                    }, ensure_ascii=False) + "\n"

                except Exception as e:
                    import traceback as _tb
                    ctx.record_step(name, "error", f"{module.description}失败: {str(e)}")
                    yield json.dumps({
                        "type": "error",
                        "message": f"管道执行失败: {str(e)}",
                    }, ensure_ascii=False) + "\n"
                    return

            # 取最终输出
            narrative_output = ctx.get_output("narrative")
            plan_output = ctx.get_output("chapter_plan")
            actions = ctx.get_output("character_action", {}).get("actions", [])

            # complete
            yield json.dumps({
                "type": "complete",
                "chapter_number": (narrative_output or {}).get("chapter_number",
                    (plan_output or {}).get("chapter_number", 0)),
                "title": (narrative_output or {}).get("title",
                    (plan_output or {}).get("title", "")),
                "content": (narrative_output or {}).get("content", ""),
                "word_count": (narrative_output or {}).get("word_count", 0),
                "steps": ctx.get_progress(),
                "actions": actions,
            }, ensure_ascii=False) + "\n"

        except Exception as e:
            import traceback as _tb
            yield json.dumps({
                "type": "error",
                "message": f"管道执行失败: {str(e)}",
            }, ensure_ascii=False) + "\n"

        return  # 生成器结束

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

    def get_system_info(self) -> dict[str, Any]:
        """返回系统架构信息供 LLM 自我诊断"""

        # 模块分层（抽象描述，不暴露具体文件路径）
        layers = [
            {"name": "API 层", "desc": "聊天端点、CRUD 操作、流式输出入口"},
            {"name": "业务逻辑层", "desc": "核心创作业务逻辑、数据校验与转换"},
            {"name": "数据层", "desc": "数据模型定义（Novel, Character, World, Chapter）"},
            {"name": "存储层", "desc": "数据持久化与读写"},
            {"name": "上下文构建层", "desc": "对话系统提示词组装"},
            {"name": "UI 层", "desc": "Web 前端界面"},
            {"name": "资产注册层", "desc": "系统集成与工具注册"},
            {"name": "角色推理层", "desc": "角色对话模拟与行为推理"},
            {"name": "场景管理层", "desc": "场景创建与管理"},
            {"name": "世界观模块", "desc": "世界观构建与维护"},
            {"name": "叙事引擎", "desc": "叙事生成与节奏控制"},
            {"name": "后台任务层", "desc": "异步任务调度和执行"},
        ]

        # 数据模型
        data_model = {
            "Novel(title, genre)": {
                "outline": "Outline 对象 — {title, logline, summary, three_act{act1,act2,act3}, chapters[], themes, tone}",
                "characters": "dict[char_id -> Character] — {name, archetype, personality[], background, goal, speech_style}",
                "world": "WorldSetting 对象 — {name, overview, rules[], factions[], scenes{scene_id -> SceneSetting}}",
                "chapters": "list[Chapter] — [{number, title, content, status, outline_id, notes, word_count}]",
                "status": "planning | writing | editing | published",
            }
        }

        # 能力清单（与 AssetCapability 定义一致）
        capabilities = [
            {"name": "get_novel", "params": "novel_id", "desc": "获取小说完整数据"},
            {"name": "save_outline", "params": "novel_id, title, logline, summary, three_act, themes, tone", "desc": "保存三幕大纲"},
            {"name": "add_outline_chapter", "params": "novel_id, number, title, summary, key_events, characters_involved, settings, pov_character", "desc": "在大纲中添加章节规划"},
            {"name": "add_character", "params": "novel_id, name, archetype, personality[], background, speech_style, goal", "desc": "添加角色"},
            {"name": "update_character", "params": "novel_id, char_id, ...", "desc": "更新角色字段"},
            {"name": "delete_character", "params": "novel_id, char_id", "desc": "删除角色"},
            {"name": "save_world", "params": "novel_id, name, overview, rules[], factions[]", "desc": "保存世界观"},
            {"name": "add_scene", "params": "novel_id, name, location, description, time, weather", "desc": "添加场景"},
            {"name": "update_scene", "params": "novel_id, scene_id, ...", "desc": "更新场景"},
            {"name": "delete_scene", "params": "novel_id, scene_id", "desc": "删除场景"},
            {"name": "write_chapter", "params": "novel_id", "desc": "从大纲生成下一章并保存"},
            {"name": "update_chapter", "params": "novel_id, chapter_id, title, content", "desc": "更新已保存章节"},
            {"name": "delete_chapter", "params": "novel_id, chapter_number", "desc": "删除指定编号章节"},
            {"name": "add_chapter", "params": "novel_id, title (可选)", "desc": "手动添加空章节"},
            {"name": "character_dialogue", "params": "novel_id, char1, char2, topic", "desc": "角色对话模拟"},
            {"name": "chat", "params": "novel_id, message", "desc": "小说创作对话"},
            {"name": "create_novel", "params": "title, genre, logline", "desc": "新建小说"},
            {"name": "generate", "params": "novel_id, instruction", "desc": "根据指令生成内容并自动保存"},
            {"name": "get_system_info", "params": "无需参数", "desc": "返回本系统架构信息（即此方法）"},
        ]

        storage = {
            "novels": "小说数据",
            "sessions": "对话上下文记忆",
            "prompts": "子技能提示词文件",
            "config": "系统配置文件",
        }

        startup = {
            "command": "agentsystem serve --port 8765",
            "port": 8765,
        }

        return {
            "app_name": "Novel Studio（小说工作室）",
            "asset_id": "asset:novel_studio:v1",
            "layers": layers,
            "data_model": data_model,
            "capabilities": capabilities,
            "storage": storage,
            "startup": startup,
        }
