"""Novel Studio — HTTP API 路由

为 HTTP 测试服务器提供小说创作的 API 端点。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Generator

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.novel_studio.engine import NovelStudioEngine
from app.novel_studio.storage import NovelStorage
from app.novel_studio.models import CharacterArchetype, Chapter

logger = logging.getLogger(__name__)


def create_novel_router(
    model_router=None,
    llm_client=None,
    engine=None,
    context_center=None,
    runtime_center=None,
    tool_calling_engine=None,
    hot_tool_manager=None,
    prompt_composer=None,
) -> APIRouter:
    """创建小说工作室 API 路由

    Parameters
    ----------
    context_center : ContextCenter | None
        如果提供，LLM 调用的上下文将通过 ContextCenter 统一管理
    runtime_center : RuntimeCenter | None
        如果提供，资产方法调用可通过 RuntimeCenter 调度
    tool_calling_engine : ToolCallingEngine | None
        如果提供，使用系统工具调用引擎（包含 read_prompt_skill、call_asset_method 等）
    hot_tool_manager : HotToolManager | None
        如果提供，获取注册的工具定义列表
    prompt_composer : PromptComposer | None
        如果提供，读取分层提示词模板
    """
    from app.novel_studio.novel_context_builder import (
        build_novel_system_prompt,
        get_or_create_novel_session,
        get_or_create_dialogue_session,
        log_context_record,
        log_novel_context_records,
    )
    from app.system.gateway.tool_calling_interpreter import (
        build_session_context,
        SYSTEM_PROMPT_TEMPLATE,
    )
    from app.ai.tool_calling_engine import ToolDef

    router = APIRouter(prefix="/api/novel", tags=["novel-studio"])
    if engine is None:
        engine = NovelStudioEngine(
            storage=NovelStorage(),
            model_router=model_router,
            llm_client=llm_client,
        )

    @router.post("/create")
    async def api_create_novel(data: dict):
        title = data.get("title", "未命名")
        genre = data.get("genre", "")
        author = data.get("author", "")
        logline = data.get("logline", "")
        novel = engine.create_novel(title, genre=genre, author=author)
        # 如果有梗概先存为 outline
        if logline:
            engine.create_outline(novel.id, title, logline=logline)
        return {"success": True, "novel_id": novel.id, "title": novel.title}

    @router.post("/list")
    async def api_list_novels(data: dict = {}):
        novels = engine.list_novels()
        return {"success": True, "novels": novels}

    @router.post("/get")
    async def api_get_novel(data: dict):
        novel_id = data.get("novel_id", "")
        novel = engine.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "not_found"}
        return {"success": True, "novel": novel.model_dump(mode="json")}

    @router.post("/report")
    async def api_novel_report(data: dict):
        novel_id = data.get("novel_id", "")
        report = engine.get_novel_full_report(novel_id)
        novel = engine.get_novel(novel_id)
        return {
            "success": True,
            "report": report,
            "title": novel.title if novel else "",
        }

    @router.post("/outline")
    async def api_get_outline(data: dict):
        novel_id = data.get("novel_id", "")
        novel = engine.get_novel(novel_id)
        if not novel or not novel.outline:
            return {"success": True, "html": None, "has_outline": False}
        outline = novel.outline
        parts = [f"**梗概：** {outline.summary or '无'}" if outline.summary else ""]
        if outline.three_act.get("act1"):
            parts.append(f"\n**第一幕：** {outline.three_act['act1']}")
        if outline.three_act.get("act2"):
            parts.append(f"\n**第二幕：** {outline.three_act['act2']}")
        if outline.three_act.get("act3"):
            parts.append(f"\n**第三幕：** {outline.three_act['act3']}")
        if outline.chapters:
            parts.append("\n**章节大纲：**")
            for ch in outline.chapters:
                mark = "✅" if ch.status == "done" else "📝"
                parts.append(f"\n{mark} 第{ch.number}章 {ch.title}")
                if ch.summary:
                    parts.append(f"   > {ch.summary}")
        return {
            "success": True,
            "has_outline": True,
            "html": "\n".join(parts),
        }

    @router.post("/outline/save")
    async def api_save_outline(data: dict):
        novel_id = data.get("novel_id", "")
        summary = data.get("summary", "")
        three_act = data.get("three_act", {})
        novel = engine.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "not_found"}
        engine.create_outline(novel_id, novel.title, summary=summary, three_act=three_act)
        return {"success": True}

    @router.post("/outline/chapter")
    async def api_add_chapter_outline(data: dict):
        novel_id = data.get("novel_id", "")
        number = int(data.get("number", 1))
        title = data.get("title", f"第{number}章")
        summary = data.get("summary", "")
        key_events = data.get("key_events", [])
        engine.add_chapter_outline(novel_id, number, title, summary, key_events)
        return {"success": True}

    @router.post("/characters")
    async def api_list_characters(data: dict):
        novel_id = data.get("novel_id", "")
        novel = engine.get_novel(novel_id)
        if not novel:
            return {"success": True, "characters": []}
        chars = []
        for c in novel.characters.values():
            chars.append({
                "id": c.id,
                "name": c.name,
                "archetype": c.archetype.value,
                "personality": c.personality,
                "background": c.background[:80] + "..." if len(c.background) > 80 else c.background,
                "speech_style": c.speech_style,
            })
        return {"success": True, "characters": chars}

    @router.post("/character/add")
    async def api_add_character(data: dict):
        novel_id = data.get("novel_id", "")
        name = data.get("name", "新角色")
        archetype_str = data.get("archetype", "配角")
        personality = data.get("personality", [])
        background = data.get("background", "")
        speech_style = data.get("speech_style", "")
        try:
            archetype = CharacterArchetype(archetype_str)
        except ValueError:
            archetype = CharacterArchetype.SUPPORTING
        char = engine.add_character(
            novel_id, name, archetype=archetype,
            personality=personality, background=background,
            speech_style=speech_style,
        )
        if char:
            return {"success": True, "character": {"id": char.id, "name": char.name}}
        return {"success": False, "error": "novel_not_found"}

    @router.post("/character/update")
    async def api_update_character(data: dict):
        novel_id = data.get("novel_id", "")
        char_id = data.get("char_id", "")
        updates = {}
        for field in ["name", "archetype", "personality", "background", "speech_style", "goal", "flaw"]:
            if field in data:
                updates[field] = data[field]
        if not novel_id or not char_id or not updates:
            return {"success": False, "error": "缺少参数"}
        char = engine.update_character(novel_id, char_id, **updates)
        if char:
            return {"success": True, "character": {"id": char.id, "name": char.name}}
        return {"success": False, "error": "角色不存在"}

    @router.post("/character/delete")
    async def api_delete_character(data: dict):
        novel_id = data.get("novel_id", "")
        char_id = data.get("char_id", "")
        if not novel_id or not char_id:
            return {"success": False, "error": "缺少参数"}
        ok = engine.remove_character(novel_id, char_id)
        return {"success": ok, "error": "" if ok else "角色不存在"}

    @router.post("/world")
    async def api_get_world(data: dict):
        novel_id = data.get("novel_id", "")
        novel = engine.get_novel(novel_id)
        if not novel or not novel.world:
            return {"success": True, "html": None, "has_world": False}
        w = novel.world
        parts = [f"**{w.name}**"]
        if w.overview:
            parts.append(f"\n概述：{w.overview}")
        if w.rules:
            parts.append(f"\n规则：\n" + "\n".join(f"- {r}" for r in w.rules))
        if w.scenes:
            parts.append(f"\n场景数：{len(w.scenes)}")
            for s in w.scenes.values():
                parts.append(f"\n  📍 {s.name}（{s.location}）")
        return {"success": True, "has_world": True, "html": "\n".join(parts)}

    @router.post("/world/save")
    async def api_save_world(data: dict):
        novel_id = data.get("novel_id", "")
        name = data.get("name", "世界")
        overview = data.get("overview", "")
        rules = data.get("rules", [])
        engine.create_world(novel_id, name, overview=overview, rules=rules)
        return {"success": True}

    @router.post("/scene/add")
    async def api_add_scene(data: dict):
        novel_id = data.get("novel_id", "")
        name = data.get("name", "新场景")
        location = data.get("location", "")
        description = data.get("description", "")
        engine.add_scene(novel_id, name, location=location, description=description)
        return {"success": True}

    @router.post("/scene/delete")
    async def api_delete_scene(data: dict):
        novel_id = data.get("novel_id", "")
        scene_id = data.get("scene_id", "")
        if not novel_id or not scene_id:
            return {"success": False, "error": "缺少参数"}
        ok = engine.remove_scene(novel_id, scene_id)
        return {"success": ok, "error": "" if ok else "场景不存在"}

    @router.post("/scene/update")
    async def api_update_scene(data: dict):
        novel_id = data.get("novel_id", "")
        scene_id = data.get("scene_id", "")
        updates = {}
        for field in ["name", "location", "description", "time_period", "weather", "lighting", "temperature"]:
            if field in data:
                updates[field] = data[field]
        if not novel_id or not scene_id or not updates:
            return {"success": False, "error": "缺少参数"}
        novel = engine._storage.update_scene(novel_id, scene_id, updates)
        return {"success": novel is not None, "error": "" if novel else "场景不存在"}

    @router.post("/generate")
    async def api_generate(data: dict):
        novel_id = data.get("novel_id", "")
        instruction = data.get("instruction", "继续写下去")
        result = await engine.generate_content(novel_id, instruction)
        content = result.content

        # 自动保存为章节
        chapter_info = _save_as_chapter(novel_id, content, instruction)
        if not chapter_info:
            chapter_info = {"number": 0, "title": ""}

        return {
            "success": True,
            "content": content,
            "chapter": chapter_info,
        }

    @router.post("/generate/next")
    async def api_generate_next(data: dict):
        novel_id = data.get("novel_id", "")
        template = data.get("template", "write_next_chapter")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        result = await engine.generate_next_chapter(novel_id, template=template)
        return result

    @router.post("/generate/next/stream")
    async def api_generate_next_stream(data: dict):
        novel_id = data.get("novel_id", "")
        template = data.get("template", "write_next_chapter")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}

        generator = engine.generate_next_chapter_stream(novel_id, template=template)
        return StreamingResponse(generator, media_type="application/x-ndjson")

    # ──── 后台任务 API（缓冲模式，断开连接后继续生成） ────

    import asyncio as _asyncio
    from app.novel_studio.task_manager import create_task, get_task, get_latest_task, cleanup_old_tasks

    @router.post("/generate/start")
    async def api_generate_start(data: dict):
        """启动后台生成任务，返回 task_id（不阻塞，不断开）"""
        novel_id = data.get("novel_id", "")
        template = data.get("template", "write_next_chapter")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}

        # 检查是否有已存在的运行中任务
        existing = get_latest_task(novel_id)
        if existing and existing.status == "running":
            return {
                "success": True,
                "task_id": existing.id,
                "note": "已有运行中的任务，继续使用",
            }

        task = create_task(novel_id, template)
        # 在后台线程池启动管道执行（client.chat() 是同步 httpx，会阻塞事件循环）
        def _run_pipeline_in_thread():
            """Use a separate event loop in a thread to avoid blocking uvicorn's event loop"""
            _loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(_loop)
            try:
                _loop.run_until_complete(
                    engine.run_next_chapter_task(novel_id, template, task)
                )
            except Exception:
                logger.exception("后台管道线程异常")
            finally:
                _loop.close()
                _asyncio.set_event_loop(None)

        main_loop = _asyncio.get_event_loop()
        main_loop.run_in_executor(None, _run_pipeline_in_thread)

        return {"success": True, "task_id": task.id}

    @router.get("/task/{task_id}")
    async def api_get_task(task_id: str, from_event: int = 0):
        """获取任务状态和事件（支持增量拉取 via from_event）"""
        task = get_task(task_id)
        if not task:
            return {"success": False, "error": "任务未找到"}

        data = task.to_dict(from_event_index=from_event)
        data["success"] = True
        return data

    @router.get("/tasks/latest")
    async def api_get_latest_task(novel_id: str = ""):
        """获取某小说最新的任务"""
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        task = get_latest_task(novel_id)
        if not task:
            return {"success": True, "task": None}
        return {"success": True, "task": task.to_dict()}

    # ──── 辅助函数：从 LLM 生成内容中提取章节标题 ────
    def _extract_chapter_title(content: str, default: str = "未命名") -> str:
        """从 LLM 生成的内容首段中提取章节标题"""
        import re
        # 尝试匹配各种标题格式
        lines = content.strip().split('\n')
        first_line = lines[0].strip() if lines else ""
        # 匹配 "第N章 标题" 或 "# 第N章 标题" 或 "## 第N章 标题"
        title_match = re.search(r'(?:#{1,6}\s*)?第(\d+)[章节]\s*[：:]\s*(.+?)(?:[#\n]|$)', first_line)
        if title_match:
            return title_match.group(2).strip()
        title_match = re.search(r'(?:#{1,6}\s*)?第(\d+)[章节]\s+(.+?)(?:[#\n]|$)', first_line)
        if title_match:
            return title_match.group(2).strip()
        # 匹配 "## 标题" 或 "# 标题"
        title_match = re.search(r'^#{1,6}\s+(.+?)(?:[#\n]|$)', first_line)
        if title_match:
            return title_match.group(1).strip()
        # 匹配 "**标题**" 格式
        title_match = re.search(r'^\*\*(.+?)\*\*', first_line)
        if title_match:
            return title_match.group(1).strip()
        # 如果第一行很短（<30字），把它当作标题
        if len(first_line) < 30 and first_line and not first_line.startswith('"'):
            return first_line[:30]
        return default

    # ──── 辅助函数：将 LLM 生成内容保存为章节 ────
    def _save_as_chapter(novel_id: str, content: str, instruction: str = "") -> dict | None:
        """检测生成内容是否为章节正文，若是则自动保存。返回 {number, title} 或 None"""
        if len(content) < 100:
            return None  # 太短不认为是章节正文
        novel = engine.get_novel(novel_id)
        if not novel:
            return None
        # 计算下一章编号
        if novel.chapters:
            chapter_number = max(c.number for c in novel.chapters) + 1
        else:
            chapter_number = 1
        # 从生成内容中提取标题（优先），回退到指令
        chapter_title = _extract_chapter_title(content)
        if chapter_title == "未命名":
            import re
            title_match = re.search(r'[第](\d+)[章节]|["「『]([^"」』]+)["」』]', instruction)
            if title_match:
                num = title_match.group(1)
                name = title_match.group(2)
                if name:
                    chapter_title = name
                elif num:
                    chapter_title = f"第{num}章"
            elif len(instruction) > 5 and "写" not in instruction[:3]:
                chapter_title = instruction[:20]
        chapter = Chapter(
            number=chapter_number,
            title=chapter_title,
            content=content,
            word_count=len(content),
        )
        engine._storage.add_chapter(novel_id, chapter)
        return {"number": chapter_number, "title": chapter_title}

    # ──── 辅助函数：将 LLM 响应保存为大纲 ────
    def _try_save_as_outline(novel_id: str, content: str, engine) -> bool:
        """尝试从 LLM 输出中提取并保存大纲信息（静默跳过，不影响响应）"""
        if not content or len(content) < 50:
            return False
        novel = engine.get_novel(novel_id)
        if not novel:
            return False
        try:
            import re as _re
            # 提取摘要（取前300字作为梗概）
            summary = content[:300].strip()
            # 检测是否有三幕结构
            three_act = {}
            act_patterns = {
                "act1": r'(?:第?一[幕部]|开端|setup|beginning).*?(?=第?二[幕部]|发展|middle|$|第?三[幕部])',
                "act2": r'(?:第?二[幕部]|发展|middle|confrontation).*?(?=第?三[幕部]|结局|end|resolution|$)',
                "act3": r'(?:第?三[幕部]|结局|end|resolution).*',
            }
            for key, pat in act_patterns.items():
                m = _re.search(pat, content, _re.DOTALL | _re.IGNORECASE)
                if m:
                    three_act[key] = m.group(0).strip()[:500]
            # 提取章节规划
            chapter_matches = _re.findall(
                r'(?:第(\d+)[章节][：: ]+(.+?)(?=第\d+[章节]|$))',
                content + '\n第999章 END',
                _re.DOTALL
            )
            if not chapter_matches:
                chapter_matches = _re.findall(
                    r'(?:第\s*(\d+)\s*[章节][：:]\s*(.+?)(?:\n|$))',
                    content,
                )
            # 保存大纲
            engine.create_outline(
                novel_id, novel.title,
                summary=summary,
                three_act=three_act,
            )
            # 保存每个章节规划
            for num_str, title in chapter_matches:
                if not num_str or not title:
                    continue
                try:
                    engine.add_chapter_outline(
                        novel_id, int(num_str),
                        title.strip()[:50],
                        summary="",
                        key_events=[],
                    )
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def _format_novel_state(novel) -> str:
        """格式化小说当前状态，用于注入总提示词。"""
        from app.novel_studio.models import CharacterArchetype
        lines = [f"**{novel.title}**", f"类型：{novel.genre or '未设定'}"]
        if novel.outline and novel.outline.summary:
            lines.append(f"梗概：{novel.outline.summary[:200]}")
        if novel.characters:
            chars = []
            for c in novel.characters.values():
                role = c.archetype.value if hasattr(c.archetype, 'value') else str(c.archetype)
                chars.append(f"{c.name}({role})")
            lines.append(f"角色（{len(chars)}个）：{'、'.join(chars[:12])}")
            if len(chars) > 12:
                lines[-1] += f"…等共{len(chars)}个"
        if novel.chapters:
            done = [c for c in novel.chapters if c.content]
            lines.append(f"已写{len(done)}章 / 共{len(novel.chapters)}章")
            if done:
                lines.append("最近章节：")
                for c in done[-3:]:
                    preview = c.content[:60].replace('\n', ' ')
                    lines.append(f"  第{c.number}章 {c.title}：{preview}…")
        if novel.world:
            w = novel.world
            lines.append(f"世界观：{w.name or '未命名'}")
            if w.scenes:
                lines.append(f"  场景（{len(w.scenes)}个）：{'、'.join(list(w.scenes.keys())[:5])}")
        if novel.outline and novel.outline.chapters:
            pending = sum(1 for co in novel.outline.chapters
                         if not any(c.number == co.number for c in novel.chapters if c.content))
            lines.append(f"待写章节：{pending}章")
        lines.append(f"状态：{novel.status}")
        return '\n'.join(lines)

    # ──── 辅助：构建 call_asset_method 工具定义 ────
    def _build_asset_tool_def() -> dict:
        """构建 call_asset_method 的 OpenAI 函数调用格式，包含所有方法描述"""
        return {
            "type": "function",
            "function": {
                "name": "call_asset_method",
                "description": "调用小说工作室资产（asset:novel_studio:v1）的方法。"
                               "可用方法清单（含参数说明）：\n"
                               "1. get_novel(novel_id) - 获取小说完整数据\n"
                               "2. save_outline(novel_id, title, logline, summary, three_act, themes, tone) - 保存三幕大纲\n"
                               "3. add_outline_chapter(novel_id, number, title, summary, key_events, characters_involved, "
                               "settings, pov_character) - 在大纲中添加章节规划\n"
                               "4. add_character(novel_id, name, archetype, personality, background, speech_style) - 添加角色\n"
                               "5. update_character(novel_id, char_id, ...) - 更新角色\n"
                               "6. delete_character(novel_id, char_id) - 删除角色\n"
                               "7. save_world(novel_id, name, overview, rules) - 保存世界观\n"
                               "8. add_scene(novel_id, name, location, description, time, weather) - 添加场景\n"
                               "9. update_scene(novel_id, scene_id, ...) - 更新场景\n"
                               "10. delete_scene(novel_id, scene_id) - 删除场景\n"
                               "11. write_chapter(novel_id) - 从大纲生成下一章\n"
                               "12. update_chapter(novel_id, chapter_id, title, content) - 更新章节\n"
                               "13. delete_chapter(novel_id, chapter_number) - 删除章节\n"
                               "14. character_dialogue(novel_id, char1, char2, topic) - 角色对话生成\n"
                               "15. chat(novel_id, message) - 对话\n"
                               "16. create_novel(title, genre, logline) - 新建小说\n"
                               "17. generate(novel_id, instruction) - 指令生成",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset_id": {
                            "type": "string",
                            "description": "资产ID，固定为 asset:novel_studio:v1",
                        },
                        "method": {
                            "type": "string",
                            "description": "方法名，必填。可选：get_novel, save_outline, add_outline_chapter, "
                                           "add_character, update_character, delete_character, "
                                           "save_world, add_scene, update_scene, delete_scene, "
                                           "write_chapter, update_chapter, delete_chapter, "
                                           "character_dialogue, chat, create_novel, generate",
                        },
                        "params": {
                            "type": "object",
                            "description": "参数对象，必须包含 novel_id（新建小说除外）。"
                                           "各方法需要的参数详见上方 description。",
                        },
                    },
                    "required": ["asset_id", "method"],
                },
            },
        }

    @router.post("/chapter/write")
    async def api_write_chapter(data: dict):
        novel_id = data.get("novel_id", "")
        novel = engine.get_novel(novel_id)
        if not novel or not novel.outline:
            return {"success": False, "content": "请先创建大纲和章节规划"}
        # 找到下一个未写的章节
        next_ch = None
        for co in novel.outline.chapters:
            existing = [c for c in novel.chapters if c.number == co.number]
            if not existing:
                next_ch = co
                break
        if not next_ch:
            return {"success": False, "content": "所有章节都写完了！"}
        chapter = await engine.write_chapter(novel_id, next_ch.number)
        if chapter:
            return {"success": True, "content": chapter.content[:2000], "chapter": chapter.number}
        return {"success": False, "content": "章节生成失败"}

    @router.post("/chapter/delete")
    async def api_delete_chapter(data: dict):
        novel_id = data.get("novel_id", "")
        chapter_number = data.get("chapter_number", 0)
        if not novel_id or not chapter_number:
            return {"success": False, "error": "缺少参数"}
        ok = engine._storage.delete_chapter(novel_id, chapter_number)
        return {"success": ok}

    @router.post("/chapter/update")
    async def api_update_chapter(data: dict):
        novel_id = data.get("novel_id", "")
        chapter_id = data.get("chapter_id", "")
        title = data.get("title", None)
        content = data.get("content", None)
        if not novel_id or not chapter_id:
            return {"success": False, "error": "缺少参数"}
        updates = {}
        if title is not None:
            updates["title"] = title
        if content is not None:
            updates["content"] = content
            updates["word_count"] = len(content)
        novel = engine._storage.update_chapter(novel_id, chapter_id, updates)
        return {"success": novel is not None}

    @router.post("/chapter/add")
    async def api_add_chapter(data: dict):
        novel_id = data.get("novel_id", "")
        title = data.get("title", "新章节")
        content = data.get("content", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        chapter = engine.add_chapter(novel_id, title=title, content=content)
        if chapter:
            return {"success": True, "chapter": {"id": chapter.id, "number": chapter.number, "title": chapter.title}}
        return {"success": False, "error": "小说不存在"}

    @router.post("/dialogue")
    async def api_dialogue(data: dict):
        novel_id = data.get("novel_id", "")
        char1 = data.get("char1", "")
        char2 = data.get("char2", "")
        topic = data.get("topic", "闲聊")
        # 通过 ContextCenter 管理对话会话（每个角色对话独立上下文窗口）
        d_session_id = get_or_create_dialogue_session(novel_id, char1, char2, context_center)
        log_context_record(d_session_id, f"话题：{topic}", context_center, role="user", kind="message")
        result = await engine.character_dialogue(novel_id, char1, char2, topic)
        log_context_record(d_session_id, result, context_center, role="assistant", kind="message")
        return {"success": True, "result": result}

    @router.post("/chat/stream")
    async def api_chat_stream(data: dict):
        """SSE 流式 AI 对话接口：实时逐 token 显示生成内容"""
        novel_id = data.get("novel_id", "")
        message = data.get("message", "")
        if not novel_id:
            return JSONResponse({"success": False, "error": "缺少 novel_id"})
        if not message:
            return JSONResponse({"success": False, "error": "消息不能为空"})
        novel = engine.get_novel(novel_id)
        if not novel:
            return JSONResponse({"success": False, "error": "小说未找到"})

        # 通过 ContextCenter 管理上下文（如果可用）
        session_id = get_or_create_novel_session(novel_id, context_center)
        log_novel_context_records(novel, context_center, session_id)
        log_context_record(session_id, message, context_center, role="user", kind="message")

        # 使用集中式系统 prompt 构建
        system_prompt = build_novel_system_prompt(novel)

        return StreamingResponse(
            _stream_chat_events(engine, novel, message, novel_id, system_prompt, context_center, session_id, runtime_center),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ──── SSE 辅助生成器 ────
    def _stream_chat_events(
        engine: NovelStudioEngine,
        novel,
        message: str,
        novel_id: str,
        system_prompt: str,
        context_center=None,
        session_id: str = "",
        runtime_center=None,
    ) -> Generator:
        """SSE 事件生成器：工具轮次 → 流式输出 → 章节保存"""
        import json as _json
        import time as _time
        import logging as _log
        _logger = _log.getLogger(__name__)

        try:
            # 1. 获取 LLM 客户端
            if engine._llm_client:
                client = engine._llm_client
            elif engine._model_router:
                client = engine._model_router.get_client("novel_writer", "complex")
            else:
                yield _json.dumps({"error": "LLM 未配置"}) + "\n"
                return
            model = client._config.model
            max_tok = getattr(client._config, 'max_tokens', 4096)
            temp = getattr(client._config, 'temperature', 0.7)
            max_turn = getattr(client._config, 'max_turns', 30)

            full_text = ""

            # 2. 生成文本
            if runtime_center:
                # ── 有运行时中心：使用 chat_turns 多轮工具调用 ──
                tool_def = _build_asset_tool_def()

                def _call_asset_handler(asset_id, method, params=None):
                    try:
                        result = runtime_center.call_asset_method(asset_id, method, params or {})
                        if hasattr(result, 'to_dict'):
                            return result.to_dict()
                        return result
                    except Exception as e:
                        return {"error": str(e), "ok": False}

                # 立即通知前端：模型正在思考
                yield _json.dumps({"info": "思考中..."}) + "\n"

                final_text, usage = client.chat_turns(
                    system_prompt=system_prompt,
                    user_message=message,
                    tools=[tool_def],
                    tool_handlers={"call_asset_method": _call_asset_handler},
                    model=model,
                    max_tokens=max_tok,
                    temperature=temp,
                    max_turns=max_turn,
                )
                full_text = final_text or ""

                # 流式输出 final_text（分段发送模拟实时显示）
                if full_text:
                    paragraphs = full_text.split('\n')
                    for pi, para in enumerate(paragraphs):
                        if pi > 0:
                            yield _json.dumps({"token": "\n"}) + "\n"
                        if para:
                            chunk_size = 60
                            for j in range(0, len(para), chunk_size):
                                yield _json.dumps({"token": para[j:j+chunk_size]}) + "\n"
            else:
                # ── 无 runtime_center：降级到纯流式 ──
                yield _json.dumps({"info": "普通模式"}) + "\n"
                for attempt in range(2):
                    try:
                        for token in client.chat_stream(
                            [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                            model=model,
                            max_tokens=max_tok,
                            temperature=temp,
                        ):
                            full_text += token
                            yield _json.dumps({"token": token}) + "\n"
                    except Exception as e:
                        _logger.warning(f"chat_stream attempt {attempt+1} error: {e}")
                        if attempt == 0:
                            yield _json.dumps({"info": "重试中..."}) + "\n"
                            _time.sleep(1.5)
                            continue
                        raise
                    if full_text:
                        break
                    if attempt == 0:
                        yield _json.dumps({"info": "重试中..."}) + "\n"
                        _time.sleep(1.5)

            if not full_text:
                yield _json.dumps({"error": "模型返回为空"}) + "\n"
                return

            # 记录完整回复到 ContextCenter
            if full_text and context_center and session_id:
                log_context_record(session_id, full_text, context_center, role="assistant", kind="message")

            resp = {"done": True, "mode": "chat"}
            yield _json.dumps(resp) + "\n"

        except Exception as e:
            import traceback
            _logger.error("_stream_chat_events error: %s\n%s", e, traceback.format_exc())
            yield _json.dumps({"error": str(e)}) + "\n"

    @router.post("/chat")
    async def api_chat(data: dict):
        """AI 对话接口：绑定小说上下文的自由对话"""
        novel_id = data.get("novel_id", "")
        message = data.get("message", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        if not message:
            return {"success": False, "error": "消息不能为空"}

        novel = engine.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "小说未找到"}

        # 通过 ContextCenter 管理上下文
        session_id = get_or_create_novel_session(novel_id, context_center)
        log_novel_context_records(novel, context_center, session_id)
        log_context_record(session_id, message, context_center, role="user", kind="message")

        try:
            if tool_calling_engine and hot_tool_manager and prompt_composer:
                # ── 新架构：系统工具调用引擎 ──
                # 1. 读取总提示词模板
                app_system_prompt = prompt_composer.read_skill("novel_studio/main")
                novel_data = _format_novel_state(novel)
                app_system_prompt = app_system_prompt.replace("{novel_data}", novel_data)

                # 2. 获取历史并构建 session context
                window = context_center.get_recent_context(session_id, limit=10) if context_center else None
                history = [
                    {"role": r.role, "content": r.content}
                    for r in window.records if r.kind == "message"
                ] if window else []
                formatted_ctx = build_session_context(
                    history=history,
                    pending_intent=None,
                    pending_params={},
                    missing_param=None,
                    available_apps=[],
                    app_system_prompt=app_system_prompt,
                )

                # 3. 填充系统提示词
                system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                    session_context=formatted_ctx,
                    tools_description="",
                    tool_loop_governor="你仅能使用下方面板的可用工具。每次调用后评估是否收集到足够信息回答用户问题。",
                    branch_guidance="",
                    app_routing_rules="",
                )

                # 4. 获取工具定义（过滤系统工具 + 保留 read_prompt_skill 和 call_asset_method）
                all_tools = hot_tool_manager.get_tools_for_session(session_id)
                allowed = ("call_asset_method", "list_assets", "query_asset_info",
                           "read_prompt_skill", "find_tool", "ask_clarification", "unclear")
                tool_defs = [
                    ToolDef(name=t["name"], description=t.get("description", ""),
                            parameters=t.get("parameters", {"type": "object", "properties": {}}))
                    for t in all_tools if t["name"] in allowed
                ]

                # 5. 执行多轮工具调用
                result = tool_calling_engine.execute_turns(
                    skill_id="novel_studio",
                    system_prompt=system_prompt,
                    user_message=message,
                    tools=tool_defs,
                    asset_id="asset:novel_studio:v1",
                    session_id=session_id,
                    max_turns=20,
                )
                text = (result.final_text or "").strip()

            elif runtime_center:
                # ── 兼容旧架构：有 runtime_center ──
                tool_def = _build_asset_tool_def()
                system_prompt = build_novel_system_prompt(novel)

                def _call_asset_handler(asset_id, method, params=None):
                    try:
                        result = runtime_center.call_asset_method(asset_id, method, params or {})
                        if hasattr(result, 'to_dict'):
                            return result.to_dict()
                        return result
                    except Exception as e:
                        return {"error": str(e), "ok": False}

                if engine._llm_client:
                    client = engine._llm_client
                elif engine._model_router:
                    client = engine._model_router.get_client("novel_writer", "complex")
                else:
                    return {"success": False, "error": "请配置 LLM 客户端"}

                text, usage = client.chat_turns(
                    system_prompt=system_prompt,
                    user_message=message,
                    tools=[tool_def],
                    tool_handlers={"call_asset_method": _call_asset_handler},
                    model=client._config.model,
                    max_tokens=getattr(client._config, 'max_tokens', 4096),
                    temperature=getattr(client._config, 'temperature', 0.7),
                    max_turns=getattr(client._config, 'max_turns', 30),
                )
                text = (text or "").strip()
            else:
                # ── 降级：普通对话 ──
                system_prompt = build_novel_system_prompt(novel)
                if engine._llm_client:
                    client = engine._llm_client
                elif engine._model_router:
                    client = engine._model_router.get_client("novel_writer", "complex")
                else:
                    return {"success": False, "error": "请配置 LLM 客户端"}

                for attempt in range(3):
                    text, _ = client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=client._config.model,
                        max_tokens=getattr(client._config, 'max_tokens', 4096),
                        temperature=getattr(client._config, 'temperature', 0.7),
                    )
                    if text:
                        break
                    if attempt < 2:
                        _logger.warning(f"LLM returned empty (attempt {attempt+1}), retrying...")
                        import time; time.sleep(1.5)
                text = (text or "").strip()

            # 记录完整回复到 ContextCenter
            if text and context_center and session_id:
                log_context_record(session_id, text, context_center, role="assistant", kind="message")

            # 检测聊天中是否在写章节
            chapter_info = None
            if text and len(text) >= 100:
                import re
                if re.search(r'大纲|梗概|三幕', message):
                    _try_save_as_outline(novel_id, text, engine)
                elif re.search(r'写|章|节|生成|继续|下一', message):
                    chapter_info = _save_as_chapter(novel_id, text, message)

            resp = {"success": True, "content": text or "（模型未返回有效内容，请换个说法再试）"}
            if chapter_info:
                resp["chapter"] = chapter_info
            return resp
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # 演化引擎 API
    # ═══════════════════════════════════════════════════════════════

    @router.post("/evolve/init")
    async def api_evolve_init(data: dict):
        novel_id = data.get("novel_id", "")
        result = engine.init_evolution(novel_id)
        return {"success": True, "result": result}

    @router.post("/evolve/place")
    async def api_evolve_place(data: dict):
        char_name = data.get("char_name", "")
        scene_name = data.get("scene_name", "")
        result = engine.place_character_in_scene(char_name, scene_name)
        return {"success": True, "result": result}

    @router.post("/evolve/tick")
    async def api_evolve_tick(data: dict):
        result = engine.tick()
        return {"success": True, "result": result}

    @router.post("/evolve/batch")
    async def api_evolve_batch(data: dict):
        count = int(data.get("count", 5))
        results = engine.batch_tick(count)
        return {"success": True, "results": results}

    @router.post("/evolve/state")
    async def api_evolve_state(data: dict = {}):
        result = engine.get_evolution_state()
        return {"success": True, "result": result}

    @router.post("/evolve/event")
    async def api_evolve_event(data: dict):
        result = engine.add_world_event(
            title=data.get("title", ""),
            description=data.get("description", ""),
            event_type=data.get("event_type", ""),
        )
        return {"success": True, "result": result}

    @router.post("/evolve/save")
    async def api_evolve_save(data: dict):
        novel_id = data.get("novel_id", "")
        result = engine.save_evolution_state(novel_id)
        return {"success": True, "result": result}

    @router.post("/evolve/write")
    async def api_evolve_write(data: dict = {}):
        result = engine.write_narrative_chapter()
        return {"success": True, "result": result}

    @router.post("/evolve/log")
    async def api_evolve_log(data: dict = {}):
        log = engine.export_evolution_log()
        return {"success": True, "log": log}

    # ═══════════════════════════════════════════════════════════════
    # 导出 API
    # ═══════════════════════════════════════════════════════════════

    @router.post("/export")
    async def api_export_novel(data: dict):
        """按目录结构导出小说（含 TOC.md、分章文件、大纲、世界观）"""
        novel_id = data.get("novel_id", "")
        output_dir = data.get("output_dir", None)
        if not novel_id:
            current = engine.get_current_novel()
            if current:
                novel_id = current.id
        if not novel_id:
            return {"success": False, "error": "请指定 novel_id"}
        result = engine.export_novel_directory(novel_id=novel_id, output_dir=output_dir)
        return result

    @router.post("/export/text")
    async def api_export_text(data: dict):
        """导出为纯文本"""
        novel_id = data.get("novel_id", "")
        text = engine._storage.export_text(novel_id)
        return {"success": True, "text": text, "length": len(text)}

    # ──── 删除 API ────

    @router.post("/delete")
    async def api_delete_novel(data: dict):
        """删除整本小说及其关联数据"""
        novel_id = data.get("novel_id", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        if engine._storage.delete_novel(novel_id):
            return {"success": True, "deleted": novel_id}
        return {"success": False, "error": "not_found"}

    @router.post("/chapter/delete")
    async def api_delete_chapter(data: dict):
        """删除指定编号的章节"""
        novel_id = data.get("novel_id", "")
        chapter_number = int(data.get("chapter_number", 0))
        if not novel_id or chapter_number <= 0:
            return {"success": False, "error": "参数错误"}
        if engine._storage.delete_chapter(novel_id, chapter_number):
            return {"success": True, "chapter_number": chapter_number}
        return {"success": False, "error": "章节未找到"}

    @router.post("/chapter/delete_range")
    async def api_delete_chapters_range(data: dict):
        """删除编号范围内的章节"""
        novel_id = data.get("novel_id", "")
        from_number = int(data.get("from", 0))
        to_number = int(data.get("to", 0))
        if not novel_id or from_number <= 0 or to_number < from_number:
            return {"success": False, "error": "参数错误"}
        deleted = engine._storage.delete_chapters_range(novel_id, from_number, to_number)
        return {"success": True, "deleted": deleted, "from": from_number, "to": to_number}

    return router
