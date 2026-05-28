"""Novel Studio — HTTP API 路由

为 HTTP 测试服务器提供小说创作的 API 端点。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

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
        novel = engine.get_novel(novel_id)
        chapter_number = 1
        chapter_title = "未命名"
        if novel:
            # 计算下一章编号
            if novel.chapters:
                chapter_number = max(c.number for c in novel.chapters) + 1
            else:
                chapter_number = 1
            # 从指令中提取标题（如果用户提到了章节名）
            import re
            title_match = re.search(r'[第](\d+)[章节]|["「『]([^"」』]+)["」』]', instruction)
            if title_match:
                num = title_match.group(1)
                name = title_match.group(2)
                if name:
                    chapter_title = name
                elif num:
                    chapter_title = f"第{num}章"
                else:
                    chapter_title = "未命名"
            elif len(instruction) > 5 and "写" not in instruction[:3]:
                chapter_title = instruction[:20]
            # 创建并保存章节
            chapter = Chapter(
                number=chapter_number,
                title=chapter_title,
                content=content,
                word_count=len(content),
            )
            engine._storage.add_chapter(novel_id, chapter)

        return {
            "success": True,
            "content": content,
            "chapter": {"number": chapter_number, "title": chapter_title},
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

    @router.post("/dialogue")
    async def api_dialogue(data: dict):
        novel_id = data.get("novel_id", "")
        char1 = data.get("char1", "")
        char2 = data.get("char2", "")
        topic = data.get("topic", "闲聊")
        result = await engine.character_dialogue(novel_id, char1, char2, topic)
        return {"success": True, "result": result}

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
                text, _ = engine._llm_client.chat(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                    model=engine._llm_client._config.model,
                    max_tokens=2000,
                    temperature=0.8,
                    stream=False,
                )
                # 冷启动重试：首次返回空则再试一次
                if not text:
                    import logging as _log
                    _log.getLogger(__name__).warning("LLM returned empty on first attempt, retrying...")
                    text, _ = engine._llm_client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=engine._llm_client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
            elif engine._model_router:
                client = engine._model_router.get_client("architect", "complex")
                text, _ = client.chat(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                    model=client._config.model,
                    max_tokens=2000,
                    temperature=0.8,
                    stream=False,
                )
                # 冷启动重试
                if not text:
                    import logging as _log
                    _log.getLogger(__name__).warning("LLM(router) returned empty on first attempt, retrying...")
                    text, _ = client.chat(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        model=client._config.model,
                        max_tokens=2000,
                        temperature=0.8,
                        stream=False,
                    )
            else:
                return {"success": False, "error": "请配置 LLM 客户端"}

            return {"success": True, "content": text or "（模型返回为空，请重试）"}
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

    return router
