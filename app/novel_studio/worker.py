"""Novel Studio — App Worker 实现

MasterControl 可调度的 App Worker。
收到任务后在独立上下文执行，通过 callback 报告结果，
通过 get_progress 实时反馈进度。
"""
from __future__ import annotations

import logging
from typing import Any, Callable
from threading import Lock
import asyncio

from app.system.master.master_control import TaskRecord, AppWorkerProtocol
from app.novel_studio.engine import NovelStudioEngine
from app.novel_studio.task_manager import get_latest_task, list_active_tasks

logger = logging.getLogger(__name__)


# ── operation → (required_params, handler) ─────────────────────────
OPERATIONS: dict[str, tuple[list[str], str]] = {
    "create_novel":       (["title"], "创建小说"),
    "add_character":      (["novel_id", "name"], "添加角色"),
    "save_outline":       (["novel_id"], "保存大纲"),
    "create_world":       (["novel_id", "name"], "创建世界观"),
    "add_scene":          (["novel_id", "name"], "添加场景"),
    "get_novel":          (["novel_id"], "查询小说"),
    "get_latest_task":    (["novel_id"], "查询小说最新生成任务/进度"),
    "get_active_tasks":   (["novel_id"], "查询小说当前所有运行中/排队的生成任务(能准确回答'是否有章节在跑')"),
    # ── 演化操作 ──
    "init_evolution":     (["novel_id"], "初始化演化"),
    "tick":               ([], "世界演化的一个时间步"),
    "place_character":    (["char_name", "scene_name"], "角色入场景"),
    "batch_tick":         ([], "批量演化"),
    "add_world_event":    (["title"], "添加世界事件"),
    "generate_chapter_from_evolution": ([], "从演化生成章节"),
    "get_evolution_state":([], "查看演化状态"),
    "export_evolution_log":([], "导出演化日志"),
    "save_evolution_state":(["novel_id"], "保存演化状态"),
    "write_narrative_chapter":([], "从演化记录生成章节正文"),
    # 角色属性
    "set_attributes":      (["novel_id", "name"], "设置角色属性"),
    "add_equipment":       (["novel_id", "name"], "添加装备"),
    "set_faction":         (["novel_id", "name"], "设置势力"),
    "rename_chapters":     ([], "为无标题章节批量生成章节名"),
    "export_novel":        ([], "按目录结构导出小说（含TOC、分章文件）"),
}


class NovelStudioWorker(AppWorkerProtocol):
    """小说工作室 Worker——独立 session，完整自我认知"""

    def __init__(self, engine: NovelStudioEngine):
        self._engine = engine
        self._tasks: dict[str, dict] = {}
        self._lock = Lock()

    def _set_progress(self, task_id: str, pct: int, msg: str):
        """更新任务进度"""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["progress_pct"] = pct
                self._tasks[task_id]["progress_msg"] = msg

    def execute(self, task_id: str, operation: str,
                params: dict, callback: Callable) -> None:
        """异步执行操作，完成后调 callback"""
        logger.info("NovelStudioWorker execute task=%s op=%s params=%s",
                     task_id, operation, params)

        with self._lock:
            self._tasks[task_id] = {
                "status": "running",
                "progress_pct": 0,
                "progress_msg": "准备中...",
            }

        try:
            # 根据操作类型选择执行逻辑，带进度
            result = self._do_execute_with_progress(task_id, operation, params)
            callback(task_id, "done", result=result)
        except Exception as e:
            logger.exception("NovelStudioWorker task %s failed", task_id)
            callback(task_id, "failed", error=str(e))

    def _safe_novel_id(self, params: dict) -> str:
        """获取可靠的 novel_id：优先 params，其次 engine 当前小说"""
        nid = params.get("novel_id", "")
        if not nid:
            current = self._engine.get_current_novel()
            if current:
                nid = current.id
        return nid

    def _do_execute_with_progress(self, task_id: str,
                                   operation: str, params: dict) -> dict:
        """带进度跟踪的执行（支持操作名别名）"""
        # 统一操作名——模型可能用各种变体
        op = operation.lower().replace(" ", "_").replace("-", "_")
        op_map = {
            "create_novel": "create_novel", "add_novel": "create_novel",
            "add_character": "add_character", "add_main_character": "add_character",
            "add_npc": "add_character", "add_char": "add_character",
            "add_villain": "add_character", "add_antagonist": "add_character",
            "save_outline": "save_outline", "create_outline": "save_outline",
            "create_world": "create_world", "add_world": "create_world",
            "add_world_setting": "create_world", "build_world": "create_world",
            "create_worldview": "create_world", "add_worldview": "create_world",
            "build_worldview": "create_world", "build_world": "create_world",
            "add_scene": "add_scene", "create_scene": "add_scene",
            "get_novel": "get_novel", "query_novel": "get_novel",
            "get_character": "get_novel", "get_novel_info": "get_novel",
            "get_latest_task": "get_latest_task", "query_latest_task": "get_latest_task",
            "latest_task": "get_latest_task", "get_progress": "get_latest_task",
            "query_progress": "get_latest_task", "get_task_status": "get_latest_task",
            "get_active_tasks": "get_active_tasks", "active_tasks": "get_active_tasks",
            "list_active_tasks": "get_active_tasks", "running_tasks": "get_active_tasks",
            "has_running_task": "get_active_tasks", "is_running": "get_active_tasks",
            "modify_novel": "add_character", "update_novel": "add_character",
            "save_chapter": "save_chapter",
            "add_chapter_outline": "add_chapter_outline",
            # 演化别名
            # 角色属性
            "set_attributes": "set_attributes", "set_stats": "set_attributes", "set_attr": "set_attributes",
            "add_equipment": "add_equipment", "equip": "add_equipment", "give_item": "add_equipment",
            "set_faction": "set_faction", "join_faction": "set_faction",
            "rename_chapters": "rename_chapters", "rename_chapter": "rename_chapters", "generate_chapter_names": "rename_chapters",
            "export_novel": "export_novel", "export_novel_directory": "export_novel", "download_novel": "export_novel",
        }
        canonical = op_map.get(op, op)
        if canonical == "create_novel":
            self._set_progress(task_id, 10, "正在创建小说项目...")
            novel = self._engine.create_novel(
                title=params.get("title", "未命名"),
                genre=params.get("genre", ""),
                author=params.get("author", ""),
            )
            self._set_progress(task_id, 50, "初始化完毕")

            if params.get("logline"):
                self._set_progress(task_id, 70, "正在生成大纲...")
                self._engine.create_outline(novel.id, novel.title, logline=params["logline"])

            self._set_progress(task_id, 100, "创建完成")
            return {"novel_id": novel.id, "title": novel.title}

        elif canonical == "add_character":
            self._set_progress(task_id, 20, "验证角色信息...")
            personality = params.get("personality", [])
            if isinstance(personality, str):
                personality = [personality]
            # 兼容模型的 role / archetype 不同传法
            archetype = params.get("archetype", params.get("role", "主角"))

            self._set_progress(task_id, 50, "正在将角色注册到小说...")
            name = params.get("name", "") or "未命名角色"
            char = self._engine.add_character(
                novel_id=self._safe_novel_id(params),
                name=name,
                archetype=archetype,
                personality=personality,
                background=params.get("background", ""),
                speech_style=params.get("speech_style", ""),
                special_ability=params.get("special_ability", ""),
            )
            if char:
                self._set_progress(task_id, 100, "角色添加完成")
                return {"character_id": char.id, "name": char.name}
            raise ValueError("添加角色失败")

        elif canonical == "save_outline":
            self._set_progress(task_id, 30, "正在保存大纲...")
            self._engine.create_outline(
                novel_id=self._safe_novel_id(params),
                title=params.get("title", ""),
                summary=params.get("summary", ""),
                logline=params.get("logline", ""),
                three_act=params.get("three_act"),
            )
            self._set_progress(task_id, 100, "大纲保存完成")
            return {"status": "ok"}

        elif canonical == "create_world":
            self._set_progress(task_id, 20, "正在构建世界观框架...")
            world = self._engine.create_world(
                novel_id=self._safe_novel_id(params),
                name=params.get("name", "世界观"),
                overview=params.get("overview", ""),
                rules=params.get("rules", []),
            )
            if world:
                self._set_progress(task_id, 100, "世界观创建完成")
                return {"status": "ok"}
            raise ValueError("创建世界观失败")

        elif canonical == "add_scene":
            self._set_progress(task_id, 30, "正在添加场景...")
            scene = self._engine.add_scene(
                novel_id=self._safe_novel_id(params),
                name=params.get("name", ""),
                location=params.get("location", ""),
                description=params.get("description", ""),
                atmosphere=params.get("atmosphere", ""),
                lighting=params.get("lighting", ""),
                temperature=params.get("temperature", ""),
                sights=params.get("sights", []),
                sounds=params.get("sounds", []),
                smells=params.get("smells", []),
                textures=params.get("textures", []),
                pov_character_id=params.get("pov_character_id", ""),
                pov_character_name=params.get("pov_character_name", ""),
                known_facts=params.get("known_facts", []),
                visible_objects=params.get("visible_objects", []),
                hidden_objects=params.get("hidden_objects", []),
            )
            if scene:
                self._set_progress(task_id, 100, "场景添加完成")
                return {"scene_id": scene.id, "name": scene.name}
            raise ValueError("添加场景失败")

        elif canonical == "save_chapter":
            self._set_progress(task_id, 30, "正在保存章节...")
            novel_id = self._safe_novel_id(params)
            ch_num = params.get("chapter_number", 1)
            title = params.get("title", f"第{ch_num}章")
            content = params.get("content", "")

            # 确保有大纲条目
            from app.novel_studio.models import ChapterOutline, Chapter
            self._engine.add_chapter_outline(
                novel_id=novel_id, number=int(ch_num),
                title=title,
                summary=params.get("summary", ""),
            )
            # 通过 storage 直接保存正文
            chapter = Chapter(
                number=int(ch_num),
                title=title,
                content=content,
                word_count=len(content),
                status="draft",
            )
            novel = self._engine._storage.add_chapter(novel_id, chapter)
            self._set_progress(task_id, 100, f"第{ch_num}章保存完成")
            return {"chapter_number": ch_num, "title": title, "word_count": len(content)}

        elif canonical == "list_novels":
            self._set_progress(task_id, 30, "正在列出小说...")
            novels = self._engine.list_novels()
            self._set_progress(task_id, 100, "查询完成")
            return {"success": True, "novels": novels}

        elif canonical == "get_novel":
            self._set_progress(task_id, 50, "正在查询小说...")
            novel = self._engine.get_novel(params.get("novel_id", ""))
            if novel:
                self._set_progress(task_id, 100, "查询完成")
                return {
                    "novel_id": novel.id,
                    "title": novel.title,
                    "genre": novel.genre,
                    "status": novel.status,
                    "char_count": novel.char_count,
                    "chapter_count": len(novel.chapters) if novel.chapters else 0,
                }
            raise ValueError("小说不存在")

        elif canonical == "get_latest_task":
            novel_id = params.get("novel_id", "")
            if not novel_id:
                raise ValueError("缺少 novel_id")
            self._set_progress(task_id, 50, "正在查询最新生成任务...")
            task = get_latest_task(novel_id)
            self._set_progress(task_id, 100, "查询完成")
            if not task:
                return {"novel_id": novel_id, "task": None, "message": "该小说暂无生成任务"}
            return {"novel_id": novel_id, "task": task.to_dict()}

        elif canonical == "get_active_tasks":
            novel_id = params.get("novel_id", "")
            self._set_progress(task_id, 50, "正在查询运行中的生成任务...")
            tasks = list_active_tasks(novel_id or None)
            self._set_progress(task_id, 100, "查询完成")
            running = [t for t in tasks if t["status"] == "running"]
            return {
                "novel_id": novel_id,
                "active_tasks": tasks,
                "running_count": len(running),
                "has_running": len(running) > 0,
                "message": "有章节/任务正在运行" if running else "当前无运行中的生成任务",
            }

        # ═══════════════════════════════════════════════════════════════
        # 角色属性操作
        # ═══════════════════════════════════════════════════════════════

        elif canonical == "set_attributes":
            self._set_progress(task_id, 50, "设置角色属性...")
            novel_id = self._safe_novel_id(params)
            novel = self._engine._storage.get_novel(novel_id)
            if not novel:
                raise ValueError("小说不存在")
            char_name = params.get("name", params.get("char_name", ""))
            char = next((c for c in novel.characters.values() if c.name == char_name), None)
            if not char:
                raise ValueError(f"角色 {char_name} 不存在")
            attr = params.get("attributes", params.get("stats", {}))
            from app.novel_studio.models import Attributes
            if isinstance(attr, dict):
                for k, v in attr.items():
                    if hasattr(char.attributes, k):
                        setattr(char.attributes, k, int(v))
            self._engine._storage.save_novel(novel)
            self._set_progress(task_id, 100, "属性设置完成")
            return {"success": True, "attributes": char.attributes.sheet()}

        elif canonical == "add_equipment":
            self._set_progress(task_id, 50, "添加装备...")
            novel_id = self._safe_novel_id(params)
            novel = self._engine._storage.get_novel(novel_id)
            if not novel:
                raise ValueError("小说不存在")
            char_name = params.get("name", params.get("char_name", ""))
            char = next((c for c in novel.characters.values() if c.name == char_name), None)
            if not char:
                raise ValueError(f"角色 {char_name} 不存在")
            from app.novel_studio.models import EquipmentItem
            eq = EquipmentItem(
                name=params.get("item_name", params.get("name", "未知物品")),
                slot=params.get("slot", "tool"),
                effect=params.get("effect", ""),
                stat_bonuses=params.get("stat_bonuses", {}),
                description=params.get("description", ""),
            )
            char.equipment.append(eq)
            self._engine._storage.save_novel(novel)
            self._set_progress(task_id, 100, "装备添加完成")
            return {"success": True, "equipment": eq.name}

        elif canonical == "set_faction":
            self._set_progress(task_id, 50, "设置势力...")
            novel_id = self._safe_novel_id(params)
            novel = self._engine._storage.get_novel(novel_id)
            if not novel:
                raise ValueError("小说不存在")
            char_name = params.get("name", params.get("char_name", ""))
            char = next((c for c in novel.characters.values() if c.name == char_name), None)
            if not char:
                raise ValueError(f"角色 {char_name} 不存在")
            from app.novel_studio.models import Faction
            char.faction = Faction(
                name=params.get("faction_name", params.get("name", "未知势力")),
                rank=params.get("rank", "成员"),
                description=params.get("description", ""),
            )
            self._engine._storage.save_novel(novel)
            self._set_progress(task_id, 100, "势力设置完成")
            return {"success": True, "faction": char.faction.name}

        elif canonical == "rename_chapters":
            self._set_progress(task_id, 10, "开始逐章生成章节名...")
            result = self._engine.rename_chapters()
            self._set_progress(task_id, 100, "章节名补全完成")
            return result

        elif canonical == "export_novel":
            self._set_progress(task_id, 20, "正在导出小说目录结构...")
            nid = self._safe_novel_id(params)
            output_dir = params.get("output_dir", None)
            result = self._engine.export_novel_directory(novel_id=nid, output_dir=output_dir)
            if result.get("success"):
                self._set_progress(task_id, 100, f"导出完成: {result.get('output_dir')}")
            return result

        else:
            raise ValueError(f"未知操作: {operation} (尝试过别名: {canonical})")

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def get_progress(self, task_id: str) -> dict:
        """实时进度查询——App 自己最清楚当前状态"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"pct": 0, "msg": "任务不存在", "status": "unknown"}
            return {
                "pct": task.get("progress_pct", 0),
                "msg": task.get("progress_msg", ""),
                "status": task.get("status", "unknown"),
            }
