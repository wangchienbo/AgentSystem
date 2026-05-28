"""Novel Studio — HTTP API 路由

为 HTTP 测试服务器提供小说创作的 API 端点。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.novel_studio.engine import NovelStudioEngine
from app.novel_studio.storage import NovelStorage
from app.novel_studio.models import CharacterArchetype, Chapter


def create_novel_router(model_router=None, llm_client=None, engine=None) -> APIRouter:
    """创建小说工作室 API 路由"""
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
        # 从指令中提取标题
        import re
        chapter_title = "未命名"
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

    @router.post("/dialogue")
    async def api_dialogue(data: dict):
        novel_id = data.get("novel_id", "")
        char1 = data.get("char1", "")
        char2 = data.get("char2", "")
        topic = data.get("topic", "闲聊")
        result = await engine.character_dialogue(novel_id, char1, char2, topic)
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

        return StreamingResponse(
            _stream_chat_events(engine, novel, message, novel_id),
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
    ):
        """SSE 事件生成器：构建上下文 → 流式 LLM → 章节保存"""
        # 构建小说上下文（与 /chat 保持一致）
        ctx = [f"# {novel.title}"]
        if novel.genre:
            ctx.append(f"类型：{novel.genre}")
        ctx.append(f"状态：{novel.status}")
        if novel.outline and novel.outline.summary:
            ctx.append(f"大纲摘要：{novel.outline.summary}")
        if novel.outline and novel.outline.chapters:
            chapters_plan = [f"  第{c.number}章 {c.title}" for c in novel.outline.chapters]
            ctx.append("章节规划：\n" + "\n".join(chapters_plan))
        if novel.characters:
            ctx.append("角色：")
            for c in novel.characters.values():
                ctx.append(f"  - {c.name}({c.archetype.value}): {'、'.join(c.personality)}")
                if c.goal:
                    ctx.append(f"    目标：{c.goal}")
        if novel.world:
            ctx.append(f"世界观：{novel.world.name} - {novel.world.overview}")
        if novel.chapters:
            ctx.append("已完成章节：")
            for ch in novel.chapters[-3:]:
                ctx.append(f"  第{ch.number}章 {ch.title}（{len(ch.content)}字）")

        full_context = "\n".join(ctx)
        system_prompt = f"""你是一位专业的小说创作助手，正在帮助用户创作小说。

当前小说《{novel.title}》的上下文信息：
{full_context}

你的能力：
1. 根据用户指令生成大纲、角色、世界观、章节等内容
2. 回答关于故事的问题，提供创作建议
3. 帮助用户规划剧情、分析角色、完善世界观
4. 直接生成小说内容（当用户要求写章节时）

规则：
- 保持角色性格一致
- 注意情节逻辑
- 语言自然流畅
- 直接回答问题，不要返回 JSON 格式
- 如果用户要求生成章节，直接写出内容"""

        import json as _json
        import time as _time
        import logging as _log
        _logger = _log.getLogger(__name__)

        try:
            # 1. 获取 LLM 客户端
            if engine._llm_client:
                client = engine._llm_client
                model = client._config.model
            elif engine._model_router:
                client = engine._model_router.get_client("architect", "complex")
                model = client._config.model
            else:
                yield _json.dumps({"error": "LLM 未配置"}) + "\n"
                return

            # 2. 流式生成
            full_text = ""
            token_count = 0
            for attempt in range(2):
                try:
                    for token in client.chat_stream(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=model,
                        max_tokens=2000,
                        temperature=0.8,
                    ):
                        token_count += 1
                        full_text += token
                        yield _json.dumps({"token": token}) + "\n"
                except Exception as e:
                    _logger.warning(f"chat_stream attempt {attempt+1} error: {e}")
                    if attempt == 0:
                        yield _json.dumps({"info": "重试中..."}) + "\n"
                        _time.sleep(1.5)
                        continue
                    raise
                if token_count > 0:
                    break
                if attempt == 0:
                    yield _json.dumps({"info": "重试中..."}) + "\n"
                    _time.sleep(1.5)

            # 3. 检测是否保存章节
            chapter_info = None
            if full_text and len(full_text) >= 100:
                import re as _re
                if _re.search(r'写|章|节|生成|继续|下一', message):
                    chapter_info = _save_as_chapter(novel_id, full_text, message)

            resp = {"done": True}
            if chapter_info:
                resp["chapter"] = chapter_info
            yield _json.dumps(resp) + "\n"

        except Exception as e:
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

        # 构建小说上下文
        ctx = [f"# {novel.title}"]
        if novel.genre:
            ctx.append(f"类型：{novel.genre}")
        ctx.append(f"状态：{novel.status}")
        if novel.outline and novel.outline.summary:
            ctx.append(f"大纲摘要：{novel.outline.summary}")
        if novel.outline and novel.outline.chapters:
            chapters_plan = [f"  第{c.number}章 {c.title}" for c in novel.outline.chapters]
            ctx.append("章节规划：\n" + "\n".join(chapters_plan))
        if novel.characters:
            ctx.append("角色：")
            for c in novel.characters.values():
                ctx.append(f"  - {c.name}({c.archetype.value}): {'、'.join(c.personality)}")
                if c.goal:
                    ctx.append(f"    目标：{c.goal}")
        if novel.world:
            ctx.append(f"世界观：{novel.world.name} - {novel.world.overview}")
        if novel.chapters:
            ctx.append("已完成章节：")
            for ch in novel.chapters[-3:]:
                ctx.append(f"  第{ch.number}章 {ch.title}（{len(ch.content)}字）")

        full_context = "\n".join(ctx)
        system_prompt = f"""你是一位专业的小说创作助手，正在帮助用户创作小说。

当前小说《{novel.title}》的上下文信息：
{full_context}

你的能力：
1. 根据用户指令生成大纲、角色、世界观、章节等内容
2. 回答关于故事的问题，提供创作建议
3. 帮助用户规划剧情、分析角色、完善世界观
4. 直接生成小说内容（当用户要求写章节时）

规则：
- 保持角色性格一致
- 注意情节逻辑
- 语言自然流畅
- 直接回答问题，不要返回 JSON 格式
- 如果用户要求生成章节，直接写出内容"""

        try:
            if engine._llm_client:
                text = ""
                for attempt in range(3):
                    text, _ = engine._llm_client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=engine._llm_client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
                    if text:
                        break
                    if attempt < 2:
                        import logging as _log
                        _log.getLogger(__name__).warning(f"LLM returned empty (attempt {attempt+1}), retrying...")
                        import time; time.sleep(1.5)
            elif engine._model_router:
                client = engine._model_router.get_client("architect", "complex")
                text = ""
                for attempt in range(3):
                    text, _ = client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
                    if text:
                        break
                    if attempt < 2:
                        import logging as _log
                        _log.getLogger(__name__).warning(f"LLM(router) returned empty (attempt {attempt+1}), retrying...")
                        import time; time.sleep(1.5)
            else:
                return {"success": False, "error": "请配置 LLM 客户端"}

            text = text or ""
            # 检测聊天中是否在写章节：消息含写/章/生成等关键词，且内容足够长
            chapter_info = None
            if text and len(text) >= 100:
                import re
                if re.search(r'写|章|节|生成|继续|下一', message):
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
