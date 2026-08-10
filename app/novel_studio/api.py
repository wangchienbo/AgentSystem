"""Novel Studio — HTTP API 路由

为 HTTP 测试服务器提供小说创作的 API 端点。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Generator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.novel_studio.engine import NovelStudioEngine
from app.novel_studio.storage import NovelStorage
from app.novel_studio.models import CharacterArchetype, Chapter
from app.novel_studio.session_store import SessionStore

logger = logging.getLogger(__name__)


# ──── 模块级共享单例 ─────────────────────────────────────────
# 会话元数据存储。提升为模块级单例，使 create_novel_router 闭包与
# bootstrap 的资产方法（_session_*_resp）共享同一个实例。
# 之前它只在闭包内定义，导致 bootstrap `from api import _session_store` 抛 ImportError。
session_store = SessionStore()


def create_novel_router(
    model_router=None,
    llm_client=None,
    engine=None,
    context_center=None,
    runtime_center=None,
    tool_calling_engine=None,
    hot_tool_manager=None,
    prompt_composer=None,
    model_input_builder=None,
    require_auth=None,
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

    _deps = [Depends(require_auth)] if require_auth else []
    router = APIRouter(prefix="/api/novel", tags=["novel-studio"], dependencies=_deps)
    if engine is None:
        engine = NovelStudioEngine(
            storage=NovelStorage(),
            model_router=model_router,
            llm_client=llm_client,
        )

    # ──── 会话管理辅助 ─────────────────────────────────────────
    # 复用模块级单例（bootstrap 资产方法也依赖它）
    _session_store = session_store

    def _extract_username(request: Request) -> str:
        """从 cookie 提取用户名"""
        sid = request.cookies.get("session_id", "")
        if sid.startswith("session_"):
            return sid[len("session_"):]
        return "anonymous"

    def _resolve_session(novel_id: str, username: str, request_session_uuid: str = "") -> str:
        """解析当前会话 uuid — 返回有效的 session_uuid 字符串"""
        if request_session_uuid:
            # 用户指定了 uuid：确认存在，切换到它
            _session_store.switch_session(username, novel_id, request_session_uuid)
            return request_session_uuid
        # 无指定：获取当前或新建
        current = _session_store.get_current_session(username, novel_id)
        if current:
            return current
        return _session_store.create_session(username, novel_id)

    # ──────── 路由 ────────

    @router.post("/create")
    async def api_create_novel(data: dict):
        title = data.get("title", "未命名")
        genre = data.get("genre", "")
        author = data.get("author", "")
        logline = data.get("logline", "")
        description = data.get("description", "")
        novel = engine.create_novel(title, genre=genre, author=author, description=description)
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
        d = novel.model_dump(mode="json")
        # 紧凑摘要（放在 JSON 顶部确保截断后也能看到全部章节清单）
        _sp = [f"《{d.get('title', '')}》状态:{d.get('status', '?')}"]
        _ol = (d.get("outline") or {}).get("chapters") or []
        _ch = d.get("chapters") or []
        _sp.append(f"大纲:{len(_ol)}章")
        if _ol:
            _sp.append("规划:" + ",".join(f"#{c['number']}{c['title']}" for c in _ol))
        _sp.append(f"已写:{len(_ch)}章")
        if _ch:
            _dl = []
            for _c in _ch:
                _n = _c.get("number", "?")
                _t = _c.get("title", "?")
                _dl.append(f"#{_n} {_t}")
            _sp.append("已写明细:" + " | ".join(_dl))
        _cd = d.get("characters") or {}
        if isinstance(_cd, dict) and _cd:
            _sp.append(f"角色:{len(_cd)}个")
        _wd = d.get("world") or {}
        if _wd.get("name"):
            _sp.append(f"世界观:{_wd['name']}")
        summary = " | ".join(_sp)
        return {"success": True, "_summary": summary, "novel": d}

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
        if len(content) < 500:
            return None  # 太短不认为是章节正文
        # 中文占比检测
        chinese_count = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
        chinese_ratio = chinese_count / max(len(content), 1)
        if chinese_ratio < 0.4:
            return None  # 中文占比过低，不是叙事章节
        # 检测是否为 LLM 回复文本特征
        head = content.strip()[:200]
        if any(head.startswith(e) for e in ['✅', '📖', '🎭', '⭐', '🔥', '💀']) or '**' in head[:50]:
            return None  # 看起来是 LLM 回复文本
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
        novel_id = getattr(novel, 'novel_id', '') or getattr(novel, 'id', '')
        lines = [f"**{novel.title}**", f"小说 ID：`{novel_id}`", f"类型：{novel.genre or '未设定'}"]
        if novel.outline and novel.outline.summary:
            lines.append(f"梗概：{novel.outline.summary[:200]}")
        if novel.characters:
            chars = []
            for c in novel.characters.values():
                role = c.archetype.value if hasattr(c.archetype, 'value') else str(c.archetype)
                chars.append(f"{c.name}({role})")
            lines.append(f"角色（{len(chars)}个）：{'、'.join(chars[:8])}")
            if len(chars) > 8:
                lines[-1] += f"…等共{len(chars)}个"
        if novel.chapters:
            done = [c for c in novel.chapters if c.content]
            lines.append(f"已写{len(done)}章 / 共{len(novel.chapters)}章")
            if done:
                lines.append("最近章节：")
                for c in done[-3:]:
                    preview = c.content[:30].replace('\n', ' ')
                    lines.append(f"  第{c.number}章 {c.title}：{preview}…")
        if novel.world:
            w = novel.world
            lines.append(f"世界观：{w.name or '未命名'}")
            if w.scenes:
                lines.append(f"  场景（{len(w.scenes)}个）：{'、'.join(list(w.scenes.keys())[:3])}")
        if novel.outline and novel.outline.chapters:
            pending = sum(1 for co in novel.outline.chapters
                         if not any(c.number == co.number for c in novel.chapters if c.content))
            lines.append(f"待写章节：{pending}章")
            # Include outline chapter list for detailed queries
            lines.append("大纲章节：")
            for oc in novel.outline.chapters[:10]:
                summary = (oc.summary or "")[:60]
                lines.append(f"  第{oc.number}章 «{oc.title}» — {summary}...")
            if len(novel.outline.chapters) > 10:
                lines.append(f"  …共{len(novel.outline.chapters)}章")
        if novel.characters and isinstance(novel.characters, dict):
            lines.append("角色详情：")
            for c_name, c_data in novel.characters.items():
                role = ""
                if hasattr(c_data, 'archetype'):
                    role = c_data.archetype.value if hasattr(c_data.archetype, 'value') else str(c_data.archetype)
                elif isinstance(c_data, dict):
                    role = c_data.get('archetype', c_data.get('role', ''))
                bg = ""
                if hasattr(c_data, 'background'):
                    bg = c_data.background or ""
                elif isinstance(c_data, dict):
                    bg = c_data.get('background', '') or ''
                bg_short = (bg[:40] + "...") if len(bg) > 40 else bg
                lines.append(f"  {c_name}({role}): {bg_short}" if role else f"  {c_name}")
        lines.append(f"状态：{novel.status}")
        return '\n'.join(lines)

    # ──── 辅助：构建 call_asset_method 工具定义 ────
    def _build_asset_tool_def() -> dict:
        """构建 call_asset_method 的 OpenAI 函数调用格式，包含所有方法描述"""
        _desc_lines = []
        _desc_lines.append("调用小说工作室资产（asset:novel_studio:v1）的方法。所有方法都是安全的系统接口——直接调用即可，无需阅读源码了解实现细节。")
        _desc_lines.append("写操作后若想确认是否生效，可再次调用 get_novel 验证（但不要自己去读数据文件或源码）。")
        _desc_lines.append("")
        _desc_lines.append("### 完整方法清单")
        _desc_lines.append("")
        _methods = [
            ("get_novel", "novel_id",
             "获取小说完整数据。一次调用返回所有内容：大纲、已写章节、角色、世界观、场景、状态。返回数据中 _summary 字段是紧凑摘要（永远可见，不会被截断），包含全部已写/大纲章节编号和标题、角色数列表、世界观和场景信息。即使 novel 字段被截断，_summary 也能告诉你完整的章节清单和角色清单。",
             "返回值：{success, _summary(紧凑摘要), novel(完整数据)} – _summary 含 📖标题 📝章节(✓已写/□大纲) 👥角色列表 🌍世界观 🎭场景",
             "示例：get_novel(novel_id=\"novel_20260601_xxxx\")",
             "→ 回答任何小说问题前调一次就够。先看 _summary 了解全貌，再根据需要从 novel 中取详情"),
            ("save_chapter", "novel_id, title, content, [number]",
             "直接保存已撰写的章节到小说。content 只包含纯叙事正文，不含你的评论/摘要/结构说明。",
             "返回值：{ok: true, result: {chapter: {id, number, title, content}, message: \"保存成功\"}}",
             "示例：save_chapter(novel_id=\"...\", title=\"第一章 初入京城\", content=\"正文...\")",
             "→ 写完整章后调用保存。若想验证保存是否成功，可再调 get_novel 查看 chapters 列表"),
            ("save_outline", "novel_id, title, logline, summary, three_act, themes, tone",
             "保存小说三幕大纲。three_act 是包含 act1/act2/act3 各幕描述的字典。",
             "返回值：{ok: true, result: {outline_id, title}}",
             "示例：save_outline(novel_id=\"...\", title=\"穿越大明\", three_act={act1: \"开场\"})",
             "→ 大纲编辑完成后调用保存"),
            ("add_outline_chapter", "novel_id, number, title, summary, key_events, characters_involved, settings, pov_character",
             "在大纲中添加一个章节规划。number 是章节序号，title 是章节标题。",
             "返回值：{ok: true, result: {chapter: {number, title, summary}}}",
             "示例：add_outline_chapter(novel_id=\"...\", number=1, title=\"初入京城\", key_events=[\"到达\", \"偶遇\"])",
             "→ 规划小说章节结构时使用"),
            ("add_character", "novel_id, name, archetype, personality, background, speech_style",
             "添加角色到小说。archetype 可选值：protagonist/antagonist/mentor/ally/neutral/adversary/foil/confidante。",
             "返回值：{ok: true, result: {character: {id, name, archetype, personality}}}",
             "示例：add_character(novel_id=\"...\", name=\"沈逸之\", archetype=\"protagonist\", personality=[\"机敏\", \"坚韧\"], background=\"锦衣卫北镇抚司百户\")",
             "→ 创建新角色时调用"),
            ("update_character", "novel_id, char_id, name, archetype, personality, background, speech_style",
             "更新已有角色的一个或多个字段。只传需要更新的参数即可。",
             "返回值：{ok: true, result: {character: {id, name, ...}}}",
             "示例：update_character(novel_id=\"...\", char_id=\"char_xxx\", personality=[\"成熟\"])",
             "→ 修改角色属性时调用"),
            ("delete_character", "novel_id, char_id",
             "从小说中删除指定角色。",
             "返回值：{ok: true, result: {message: \"删除成功\"}}",
             "示例：delete_character(novel_id=\"...\", char_id=\"char_xxx\")",
             "→ 移除不需要的角色"),
            ("save_world", "novel_id, name, overview, rules",
             "创建或更新世界观设定。rules 是规则列表，每条规则包含 rule 和 description。",
             "返回值：{ok: true, result: {world_id, name}}",
             "示例：save_world(novel_id=\"...\", name=\"大明世界\", overview=\"嘉靖年间...\", rules=[{rule: \"皇权至上\", description: \"...\"}])",
             "→ 定义小说世界规则时调用"),
            ("add_scene", "novel_id, name, location, description, time, weather",
             "添加一个场景设定。场景是故事发生的地点+时间+氛围的组合。",
             "返回值：{ok: true, result: {scene: {id, name, location}}}",
             "示例：add_scene(novel_id=\"...\", name=\"京城街市\", location=\"北京城\", description=\"繁华的明代街市\")",
             "→ 定义故事场景时调用"),
            ("update_scene", "novel_id, scene_id, name, location, description, time, weather",
             "更新已有场景的名称/地点/描述等字段。",
             "返回值：{ok: true, result: {scene: {id, name, location}}}",
             "示例：update_scene(novel_id=\"...\", scene_id=\"scene_xxx\", description=\"深夜的街市\")",
             "→ 调整场景设定时调用"),
            ("delete_scene", "novel_id, scene_id",
             "删除指定场景。",
             "返回值：{ok: true, result: {message: \"删除成功\"}}",
             "示例：delete_scene(novel_id=\"...\", scene_id=\"scene_xxx\")",
             "→ 移除不需要的场景"),
            ("write_chapter", "novel_id",
             "从大纲自动生成下一章内容。需要先有大纲章节规划。AI 会根据大纲章节概要自动创作完整章节。",
             "返回值：{ok: true, result: {chapter: {id, number, title, content}}}",
             "示例：write_chapter(novel_id=\"...\")",
             "→ 让系统自动写下一章"),
            ("update_chapter", "novel_id, chapter_id, title, content",
             "更新已有章节的标题或内容。",
             "返回值：{ok: true, result: {chapter: {id, number, title, content}}}",
             "示例：update_chapter(novel_id=\"...\", chapter_id=\"ch_xxx\", content=\"新内容...\")",
             "→ 修改已写章节"),
            ("delete_chapter", "novel_id, chapter_number",
             "按章节编号删除小说中的完整章节。",
             "返回值：{ok: true, result: {message: \"删除成功\"}}",
             "示例：delete_chapter(novel_id=\"...\", chapter_number=3)",
             "→ 删除不需要的章节"),
            ("character_dialogue", "novel_id, char1, char2, topic",
             "生成两个角色之间的对话。指定角色名和话题，AI 自动生成符合角色性格的对话内容。",
             "返回值：{ok: true, result: {dialogue: [{speaker, line}, ...]}}",
             "示例：character_dialogue(novel_id=\"...\", char1=\"沈逸之\", char2=\"严世藩\", topic=\"朝堂对峙\")",
             "→ 需要角色对话场景时调用"),
            ("chat", "novel_id, message",
             "与小说创作助手对话，绑定当前小说上下文进行创作交流。",
             "返回值：{ok: true, result: {reply: \"AI回复内容\"}}",
             "示例：chat(novel_id=\"...\", message=\"帮我构思一下下一个情节\")",
             "→ 进行创作讨论（当前已通过本会话进行，一般不需要主动调）"),
            ("create_novel", "title, genre, logline",
             "创建一本新小说。自动生成 novel_id。",
             "返回值：{ok: true, result: {novel: {id, title, genre, logline}}}",
             "示例：create_novel(title=\"穿越大明\", genre=\"历史奇幻\", logline=\"一名现代特工穿越到明朝嘉靖年间...\")",
             "→ 开始创作新作品时调用"),
            ("generate", "novel_id, instruction",
             "根据指令自动生成小说内容并保存为章节。AI 根据指令创作完整内容并写入数据库。",
             "返回值：{ok: true, result: {chapter: {id, number, title, content}}}",
             "示例：generate(novel_id=\"...\", instruction=\"写第一章，主角沈逸之在执行秘密任务时意外穿越\")",
             "→ 快速生成章节内容"),
            ("save_custom_prompt", "novel_id, custom_prompt",
             "设置或更新小说的专属提示词/写作指令。用于指导 AI 按特定风格或方向写作。",
             "返回值：{ok: true, result: {message: \"保存成功\"}}",
             "示例：save_custom_prompt(novel_id=\"...\", custom_prompt=\"文风参考金庸，对话简洁有力，动作描写细致\")",
             "→ 控制小说写作风格"),
            ("save_description", "novel_id, description",
             "设置或更新小说简介（故事概述），面向读者的介绍文字。",
             "返回值：{ok: true, result: {message: \"保存成功\"}}",
             "示例：save_description(novel_id=\"...\", description=\"一个普通大学生穿越到玄幻世界，每天午夜随机抽取天赋的故事\")",
             "→ 设置小说简介"),
            ("get_system_info", "",
             "返回系统架构信息：源代码文件列表、数据模型、完整能力清单、存储路径、启动命令。",
             "返回值：{ok: true, result: {files: [...], capabilities: [...], storage: \"...\", startup: \"...\"}}",
             "示例：get_system_info()",
             "→ 回答关于代码/架构/能力的问题"),
        ]
        for i, ma in enumerate(_methods, 1):
            name, params, desc, ret, example, usage = ma
            _desc_lines.append(f"**{i}. {name}({params})**")
            _desc_lines.append(f"  - 说明：{desc}")
            _desc_lines.append(f"  - {ret}")
            _desc_lines.append(f"  - 示例：`{example}`")
            _desc_lines.append(f"  - {usage}")
            _desc_lines.append("")
        description = "\n".join(_desc_lines)
        _all_methods = "get_novel, save_chapter, save_outline, add_outline_chapter, " \
                       "add_character, update_character, delete_character, " \
                       "save_world, add_scene, update_scene, delete_scene, " \
                       "write_chapter, update_chapter, delete_chapter, " \
                       "character_dialogue, chat, create_novel, generate, " \
                       "save_custom_prompt, save_description, get_system_info"
        return {
            "type": "function",
            "function": {
                "name": "call_asset_method",
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset_id": {
                            "type": "string",
                            "description": "资产ID，固定为 asset:novel_studio:v1",
                        },
                        "method": {
                            "type": "string",
                            "description": f"方法名，必填。可选：{_all_methods}",
                        },
                        "params": {
                            "type": "object",
                            "description": "参数对象，必须包含 novel_id（新建小说、get_system_info 除外）。"
                                           "具体参数见上方方法清单中的说明。",
                        },
                    },
                    "required": ["asset_id", "method"],
                },
            },
        }

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

    @router.post("/chat/history")
    async def api_chat_history(request: Request, data: dict):
        """获取小说对话历史（支持分页：limit/offset）"""
        novel_id = data.get("novel_id", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        novel = engine.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "小说未找到"}

        username = _extract_username(request)
        session_uuid = data.get("session_uuid", "")
        if not session_uuid:
            session_uuid = _session_store.get_current_session(username, novel_id)
        if not session_uuid:
            session_uuid = _session_store.create_session(username, novel_id)

        limit = data.get("limit", 50)
        offset = data.get("offset", 0)

        session_id = get_or_create_novel_session(novel_id, context_center, user_id=username, session_uuid=session_uuid)
        records = []
        total = 0
        if context_center:
            window = context_center.read_context(session_id, limit=10000)  # 读取全部消息记录
            all_records = [
                {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
                for r in window.records
                if r.kind == "message"
            ]
            total = len(all_records)
            # 倒序截取：offset=0 返回最新的 limit 条
            start = max(0, total - offset - limit)
            end = max(0, total - offset)
            records = all_records[start:end] if start < end else []
        return {
            "success": True,
            "records": records,
            "total": total,
            "limit": limit,
            "offset": offset,
            "session_id": session_id,
            "session_uuid": session_uuid,
            "username": username,
        }

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
            _stream_chat_events(engine, novel, message, novel_id, system_prompt, context_center, session_id, runtime_center, model_input_builder),
            media_type="application/x-ndjson; charset=utf-8",
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
        model_input_builder=None,
    ) -> Generator:
        """SSE 事件生成器：工具轮次 → 流式输出 → 章节保存"""
        import json as _json
        import time as _time
        import logging as _log
        _logger = _log.getLogger(__name__)

        try:
            full_text = ""

            # ── 新架构：系统工具调用引擎（分层提示词 + ToolCallingEngine）──
            if tool_calling_engine and hot_tool_manager and prompt_composer:
                yield _json.dumps({"info": "AI 思考中..."}) + "\n"

                # 1. 读取总提示词模板并注入小说数据
                app_system_prompt = prompt_composer.read_skill("novel_studio/main")
                novel_data = _format_novel_state(novel)
                app_system_prompt = app_system_prompt.replace("{novel_data}", novel_data)

                # 2. 使用 ModelInputBuilder 构建上下文（支持窗口 + 压缩）
                model_input_view = None
                if context_center and model_input_builder:
                    model_input_view = model_input_builder.build(
                        session_id=session_id,
                        window_turns=10,
                    )
                # fallback: 传统 history 方式
                window = context_center.get_recent_context(session_id, limit=10) if context_center and model_input_view is None else None
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
                    model_input_view=model_input_view,
                )

                # 3. 填充系统提示词
                _sp = SYSTEM_PROMPT_TEMPLATE.format(
                    session_context=formatted_ctx,
                    tools_description="",
                    tool_loop_governor="[收敛优先] 🔴【核心规则】必须一次性并行输出所有独立工具调用——系统自动并行执行互不依赖的多个工具。每一轮LLM调用都算一轮，无论输出几个工具都算一轮。一轮调10个工具远优于10轮各调1个。一旦拿到足够回答用户问题的数据，立即停止调任何工具，只输出中文回复。不要连续多轮逐次调用工具。查询小说状态只需调一次 get_novel。",
                    branch_guidance="",
                    app_routing_rules="",
                )

                # 4. 获取所有工具定义（不限制，LLM 根据需要自主选择）
                all_tools = hot_tool_manager.get_tools_for_session(session_id)
                tool_defs = [
                    ToolDef(name=t["name"], description=t.get("description", ""),
                            parameters=t.get("parameters", {"type": "object", "properties": {}}))
                    for t in all_tools
                ]

                # 5. 执行多轮工具调用
                result = tool_calling_engine.execute_turns(
                    skill_id="novel_studio",
                    system_prompt=_sp,
                    user_message=message,
                    tools=tool_defs,
                    asset_id="asset:novel_studio:v1",
                    session_id=session_id,
                    max_turns=15,
                )

                # 6. 提取回复正文（优先从 save_chapter 工具参数中提取）
                text = (result.final_text or "").strip()
                for _tc in (result.tool_calls or []):
                    if _tc.tool_name == "call_asset_method" and isinstance(_tc.args, dict):
                        if _tc.args.get("method") == "save_chapter" and isinstance(_tc.args.get("params"), dict):
                            _chapter_content = _tc.args["params"].get("content", "").strip()
                            if len(_chapter_content) > 500:
                                text = _chapter_content
                                break
                full_text = text

                if full_text:
                    # 流式输出：分段 + 分块发送
                    paragraphs = full_text.split('\n')
                    for pi, para in enumerate(paragraphs):
                        if pi > 0:
                            yield _json.dumps({"token": "\n"}) + "\n"
                        if para:
                            chunk_size = 60
                            for j in range(0, len(para), chunk_size):
                                yield _json.dumps({"token": para[j:j+chunk_size]}) + "\n"
                else:
                    yield _json.dumps({"error": "模型返回为空"}) + "\n"
                    return

            # ── 旧架构路径 ──
            # 1. 获取 LLM 客户端
            elif runtime_center:
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
    async def api_chat(request: Request, data: dict):
        """AI 对话接口：绑定小说上下文的自由对话（支持 session_uuid 参数）"""
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
        username = _extract_username(request)
        session_uuid = data.get("session_uuid", "")
        if not session_uuid:
            session_uuid = _session_store.get_current_session(username, novel_id)
        if not session_uuid:
            session_uuid = _session_store.create_session(username, novel_id)
        _session_store.touch_session(username, novel_id, session_uuid)
        session_id = get_or_create_novel_session(novel_id, context_center, user_id=username, session_uuid=session_uuid)
        log_novel_context_records(novel, context_center, session_id)
        log_context_record(session_id, message, context_center, role="user", kind="message")

        try:
            _skip_auto_save = False
            if tool_calling_engine and hot_tool_manager and prompt_composer:
                # ── 新架构：系统工具调用引擎 ──
                # 1. 读取总提示词模板
                app_system_prompt = prompt_composer.read_skill("novel_studio/main")
                novel_data = _format_novel_state(novel)
                app_system_prompt = app_system_prompt.replace("{novel_data}", novel_data)

                # 2. 使用 ModelInputBuilder 构建上下文（支持窗口 + 压缩）
                model_input_view = None
                if context_center and model_input_builder:
                    model_input_view = model_input_builder.build(
                        session_id=session_id,
                        window_turns=10,
                    )
                # fallback: 传统 history 方式
                window = context_center.get_recent_context(session_id, limit=10) if context_center and model_input_view is None else None
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
                    model_input_view=model_input_view,
                )

                # 3. 填充系统提示词
                system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                    session_context=formatted_ctx,
                    tools_description="",
                    tool_loop_governor="[收敛优先] 🔴【核心规则】必须一次性并行输出所有独立工具调用——系统自动并行执行互不依赖的多个工具。每一轮LLM调用都算一轮，无论输出几个工具都算一轮。一轮调10个工具远优于10轮各调1个。一旦拿到足够回答用户问题的数据，立即停止调任何工具，只输出中文回复。不要连续多轮逐次调用工具。查询小说状态只需调一次 get_novel。",
                    branch_guidance="",
                    app_routing_rules="",
                )

                # 4. 获取所有工具定义（不限制，LLM 根据需要自主选择）
                all_tools = hot_tool_manager.get_tools_for_session(session_id)
                tool_defs = [
                    ToolDef(name=t["name"], description=t.get("description", ""),
                            parameters=t.get("parameters", {"type": "object", "properties": {}}))
                    for t in all_tools
                ]

                # 5. 执行多轮工具调用
                result = tool_calling_engine.execute_turns(
                    skill_id="novel_studio",
                    system_prompt=system_prompt,
                    user_message=message,
                    tools=tool_defs,
                    asset_id="asset:novel_studio:v1",
                    session_id=session_id,
                    max_turns=15,
                )
                text = (result.final_text or "").strip()
                # 检测是否有 save_chapter 工具调用，如有则用章节正文覆盖回复文本
                # （LLM 常输出 meta 评论而非章节正文，直接从工具参数中提取更可靠）
                for _tc in (result.tool_calls or []):
                    if _tc.tool_name == "call_asset_method" and isinstance(_tc.args, dict):
                        if _tc.args.get("method") == "save_chapter" and isinstance(_tc.args.get("params"), dict):
                            _chapter_content = _tc.args["params"].get("content", "").strip()
                            if len(_chapter_content) > 500:
                                text = _chapter_content
                                break
                # 新架构：LLM 自主管理章节保存，跳过 auto-save
                _skip_auto_save = True

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

            # 检测聊天中是否在写章节（仅旧架构路径，新架构 LLM 用 save_chapter 自主管理）
            chapter_info = None
            if not _skip_auto_save and text and len(text) >= 100:
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
    # 聊天缓冲（后台运行，浏览器断开不丢失）
    # ═══════════════════════════════════════════════════════════════

    @router.post("/chat/start")
    async def api_chat_start(request: Request, data: dict):
        """启动后台聊天任务，浏览器断开后服务器继续运行，结果自动保存到 ContextCenter（支持 session_uuid）"""
        novel_id = data.get("novel_id", "")
        message = data.get("message", "")
        if not novel_id or not message:
            return {"success": False, "error": "缺少 novel_id 或 message"}

        # 检查是否有已存在的运行中聊天任务
        existing = get_latest_task(novel_id)
        if existing and existing.kind == "chat" and existing.status == "running":
            return {
                "success": True,
                "task_id": existing.id,
                "note": "已有运行中的聊天任务，继续使用",
            }

        # 解析会话
        username = _extract_username(request)
        session_uuid = data.get("session_uuid", "")
        if not session_uuid:
            session_uuid = _session_store.get_current_session(username, novel_id)
        if not session_uuid:
            session_uuid = _session_store.create_session(username, novel_id, "新对话")
        _session_store.touch_session(username, novel_id, session_uuid)

        # 创建任务
        session_id = get_or_create_novel_session(novel_id, context_center, user_id=username, session_uuid=session_uuid)
        task = create_task(
            novel_id=novel_id,
            template="chat",
            kind="chat",
            message=message,
            session_id=session_id,
        )
        logger.info("Chat task %s created: novel=%s message_len=%d", task.id, novel_id, len(message))

        def _run_chat_in_thread():
            """在后台线程运行 LLM 调用（同步执行，不阻塞 uvicorn）"""
            from datetime import datetime, timezone
            _loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(_loop)
            try:
                task.status = "running"
                task.events.append({"type": "status", "text": "running", "ts": datetime.now(timezone.utc).isoformat()})

                # 1. 获取小说数据和会话
                novel = engine.get_novel(novel_id)
                if not novel:
                    raise RuntimeError(f"小说 {novel_id} 未找到")

                # 2. 记录用户消息到 ContextCenter
                log_novel_context_records(novel, context_center, session_id)
                log_context_record(session_id, message, context_center, role="user", kind="message")
                task.events.append({"type": "user_msg", "text": message, "ts": datetime.now(timezone.utc).isoformat()})

                # 3. 调用 LLM（优先新架构：系统工具调用引擎）
                text = ""
                _skip_auto_save = False
                if tool_calling_engine and hot_tool_manager and prompt_composer:
                    # 新架构：系统工具调用引擎
                    app_system_prompt = prompt_composer.read_skill("novel_studio/main")
                    novel_data = _format_novel_state(novel)
                    app_system_prompt = app_system_prompt.replace("{novel_data}", novel_data)

                    model_input_view = None
                    if context_center and model_input_builder:
                        model_input_view = model_input_builder.build(
                            session_id=session_id,
                            window_turns=10,
                        )
                    window = context_center.get_recent_context(session_id, limit=10) if context_center and model_input_view is None else None
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
                        model_input_view=model_input_view,
                    )

                    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                        session_context=formatted_ctx,
                        tools_description="",
                        tool_loop_governor="[收敛优先] 🔴【核心规则】必须一次性并行输出所有独立工具调用——系统自动并行执行互不依赖的多个工具。每一轮LLM调用都算一轮，无论输出几个工具都算一轮。一轮调10个工具远优于10轮各调1个。一旦拿到足够回答用户问题的数据，立即停止调任何工具，只输出中文回复。不要连续多轮逐次调用工具。查询小说状态只需调一次 get_novel。",
                        branch_guidance="",
                        app_routing_rules="",
                    )

                    all_tools = hot_tool_manager.get_tools_for_session(session_id)
                    tool_defs = [
                        ToolDef(name=t["name"], description=t.get("description", ""),
                                parameters=t.get("parameters", {"type": "object", "properties": {}}))
                        for t in all_tools
                    ]

                    result = tool_calling_engine.execute_turns(
                        skill_id="novel_studio",
                        system_prompt=system_prompt,
                        user_message=message,
                        tools=tool_defs,
                        asset_id="asset:novel_studio:v1",
                        session_id=session_id,
                        max_turns=15,
                    )
                    text = (result.final_text or "").strip()
                    for _tc in (result.tool_calls or []):
                        if _tc.tool_name == "call_asset_method" and isinstance(_tc.args, dict):
                            if _tc.args.get("method") == "save_chapter" and isinstance(_tc.args.get("params"), dict):
                                _chapter_content = _tc.args["params"].get("content", "").strip()
                                if len(_chapter_content) > 500:
                                    text = _chapter_content
                                    break
                    _skip_auto_save = True

                elif runtime_center:
                    # 兼容旧架构
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
                        raise RuntimeError("请配置 LLM 客户端")

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
                    # 降级：普通对话
                    system_prompt = build_novel_system_prompt(novel)
                    if engine._llm_client:
                        client = engine._llm_client
                    elif engine._model_router:
                        client = engine._model_router.get_client("novel_writer", "complex")
                    else:
                        raise RuntimeError("请配置 LLM 客户端")

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
                            logger.warning(f"LLM returned empty (attempt {attempt+1}), retrying...")
                            import time; time.sleep(1.5)
                    text = (text or "").strip()

                # 4. 记录 LLM 回复到 ContextCenter
                if text:
                    log_context_record(session_id, text, context_center, role="assistant", kind="message")

                # 5. 尝试自动保存章节（旧架构兼容）
                chapter_info = None
                if not _skip_auto_save and text and len(text) >= 100:
                    import re
                    if re.search(r'大纲|梗概|三幕', message):
                        _try_save_as_outline(novel_id, text, engine)
                    elif re.search(r'写|章|节|生成|继续|下一', message):
                        chapter_info = _save_as_chapter(novel_id, text, message)

                # 6. 更新任务结果
                result_data = {"content": text or "（模型未返回有效内容，请换个说法再试）"}
                if chapter_info:
                    result_data["chapter"] = chapter_info
                task.result = result_data
                task.status = "complete"
                task.events.append({"type": "complete", "text": text, "ts": datetime.now(timezone.utc).isoformat()})
                logger.info("Chat task %s complete: text_len=%d", task.id, len(text or ""))

            except Exception as e:
                logger.exception("后台聊天线程异常")
                task.status = "error"
                task.error = str(e)
                task.events.append({"type": "error", "text": str(e), "ts": datetime.now(timezone.utc).isoformat()})
            finally:
                _loop.close()
                _asyncio.set_event_loop(None)

        main_loop = _asyncio.get_event_loop()
        main_loop.run_in_executor(None, _run_chat_in_thread)

        return {"success": True, "task_id": task.id}

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

    # ═══════════════════════════════════════════════════════════════
    # 会话管理 API
    # ═══════════════════════════════════════════════════════════════

    @router.post("/sessions")
    async def api_list_sessions(request: Request, data: dict):
        """获取用户在当前小说下的所有会话列表"""
        novel_id = data.get("novel_id", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        username = _extract_username(request)
        sessions = _session_store.list_sessions(username, novel_id)
        return {"success": True, "sessions": sessions, "username": username}

    @router.post("/session/create")
    async def api_create_session(request: Request, data: dict):
        """创建新会话并设为当前"""
        novel_id = data.get("novel_id", "")
        if not novel_id:
            return {"success": False, "error": "缺少 novel_id"}
        label = data.get("label", "")
        username = _extract_username(request)
        session_uuid = _session_store.create_session(username, novel_id, label)
        # 创建对应的 ContextCenter 会话节点
        session_id = get_or_create_novel_session(novel_id, context_center, user_id=username, session_uuid=session_uuid)
        return {"success": True, "session_uuid": session_uuid, "session_id": session_id}

    @router.post("/session/switch")
    async def api_switch_session(request: Request, data: dict):
        """切换到已有会话"""
        novel_id = data.get("novel_id", "")
        session_uuid = data.get("session_uuid", "")
        if not novel_id or not session_uuid:
            return {"success": False, "error": "缺少 novel_id 或 session_uuid"}
        username = _extract_username(request)
        ok = _session_store.switch_session(username, novel_id, session_uuid)
        if not ok:
            return {"success": False, "error": "会话不存在"}
        return {"success": True, "session_uuid": session_uuid}

    @router.post("/session/delete")
    async def api_delete_session(request: Request, data: dict):
        """删除指定会话"""
        novel_id = data.get("novel_id", "")
        session_uuid = data.get("session_uuid", "")
        if not novel_id or not session_uuid:
            return {"success": False, "error": "缺少 novel_id 或 session_uuid"}
        username = _extract_username(request)
        ok = _session_store.delete_session(username, novel_id, session_uuid)
        if not ok:
            return {"success": False, "error": "会话不存在"}
        return {"success": True, "deleted": session_uuid}

    return router

