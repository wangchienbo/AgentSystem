"""Novel Studio — 系统集成引导模块

将 Novel Studio 统一注册到 AgentSystem 主控：
  - FastAPI Router（HTTP 路由层）
  - AppBlueprint（主控 App 发现层）
  - RuntimeAsset（模型可发现资产层）
  - Worker（MasterControl 异步调度层）

任何入口（http_test_server / api.main / CLI）调用
`bootstrap_novel_studio(runtime_services, fastapi_app)` 即可完成全部注册。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块级单例：避免重复注册
# ---------------------------------------------------------------------------
_bootstrapped = False


def bootstrap_novel_studio(
    runtime_services: dict[str, Any],
    fastapi_app=None,
) -> dict[str, Any]:
    """将 Novel Studio 注册到 AgentSystem 运行时。

    Parameters
    ----------
    runtime_services : dict
        build_runtime() 返回的服务字典
    fastapi_app : FastAPI | None
        如果提供，会自动挂载 /api/novel 路由和 /studio 页面路由

    Returns
    -------
    dict
        {"engine": NovelStudioEngine, "router": APIRouter}
    """
    global _bootstrapped
    if _bootstrapped:
        logger.debug("novel_studio already bootstrapped, skipping")
        return {"engine": runtime_services.get("novel_engine"), "router": None}

    from app.novel_studio.engine import NovelStudioEngine
    from app.novel_studio.api import create_novel_router
    from app.models.app_blueprint import AppBlueprint
    from app.models.asset_contract import (
        AssetDescriptor, AssetCapability, AssetType, AssetKind,
        AssetState, Visibility,
    )

    # ── 1. 创建引擎 ────────────────────────────────────────────
    model_router = runtime_services.get("model_router")
    llm_client = None
    if model_router:
        try:
            llm_client = model_router.get_client("architect", "complex")
        except Exception:
            pass

    engine = NovelStudioEngine(storage=None, model_router=model_router)
    runtime_services["novel_engine"] = engine

    # ── 2. 创建路由 ────────────────────────────────────────────
    context_center = runtime_services.get("context_center")
    runtime_center = runtime_services.get("runtime_center")
    tool_calling_engine = runtime_services.get("tool_calling_engine")
    hot_tool_manager = runtime_services.get("hot_tool_manager")
    from app.services.prompt_composer import PromptComposer
    prompt_composer = PromptComposer()
    router = create_novel_router(
        model_router=model_router,
        llm_client=llm_client,
        engine=engine,
        context_center=context_center,
        runtime_center=runtime_center,
        tool_calling_engine=tool_calling_engine,
        hot_tool_manager=hot_tool_manager,
        prompt_composer=prompt_composer,
    )

    # ── 3. 挂载 FastAPI 路由（如果提供 app） ───────────────────
    if fastapi_app is not None:
        fastapi_app.include_router(router)
        logger.info("✅ novel_studio routes mounted on FastAPI app")

    # ── 4. 注册 AppBlueprint（主控 App 发现） ───────────────────
    _register_blueprint(runtime_services)

    # ── 5. 注册 RuntimeAsset（模型可发现资产） ──────────────────
    _register_asset(runtime_services, engine, model_router)

    # ── 6. 注册 Worker（MasterControl 异步调度） ────────────────
    _register_worker(runtime_services, engine)

    # ── 7. 注册 Pipeline 模块 ───────────────────────────────────
    _register_pipeline_modules()

    _bootstrapped = True
    return {"engine": engine, "router": router}


def _register_pipeline_modules():
    """注册管道模块到全局编排器"""
    from app.novel_studio.pipeline import register_default_modules
    register_default_modules()


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _register_blueprint(runtime_services: dict) -> None:
    """注册 AppBlueprint 到 AppRegistry"""
    from app.models.app_blueprint import AppBlueprint
    from app.models.app_profile import AppRuntimeProfile
    from app.models.runtime_policy import RuntimePolicy

    app_registry = runtime_services.get("app_registry")
    if not app_registry:
        return

    try:
        app_registry.get_blueprint("bp.novel_studio")
        logger.info("novel_studio blueprint already registered")
        return
    except Exception:
        pass

    novel_bp = AppBlueprint(
        id="bp.novel_studio",
        name="novel_studio",
        goal="小说创作工作室 — 支持写小说、管理大纲、设定世界观、角色创作",
        version="1.0.0",
        source_path="app/novel_studio/",
        app_shape="generic",
        runtime_profile=AppRuntimeProfile(),
        runtime_policy=RuntimePolicy(),
    )
    try:
        app_registry.register_blueprint(
            novel_bp,
            description="小说创作应用，支持大纲、角色、世界观、章节生成与角色对话",
        )
        logger.info("✅ novel_studio AppBlueprint registered")
    except Exception as e:
        logger.warning("Failed to register novel_studio blueprint: %s", e)


def _register_asset(runtime_services: dict, engine, model_router) -> None:
    """注册 RuntimeAsset 到 RuntimeCenter"""
    from app.models.asset_contract import (
        AssetDescriptor, AssetCapability, AssetType, AssetKind,
        AssetState, Visibility,
    )

    runtime_center = runtime_services.get("runtime_center")
    if not runtime_center:
        return

    novel_asset = AssetDescriptor(
        asset_id="asset:novel_studio:v1",
        name="小说工作室",
        description="小说创作应用，支持创建小说、管理角色、大纲、世界观、章节生成、章节编辑、角色编辑、场景编辑",
        asset_type=AssetType.APP,
        asset_kind=AssetKind.MATERIALIZED,
        version="2.0.0",
        owner_type="system",
        owner_id="system",
        source_of_truth="runtime",
        status=AssetState.ACTIVE,
        capabilities=[
            AssetCapability(name="create_novel", description="创建一本新小说",
                method="create_novel",
                input_schema={"title": {"type": "string", "desc": "书名"},
                              "genre": {"type": "string", "desc": "题材"},
                              "logline": {"type": "string", "desc": "一句话梗概"}}),
            AssetCapability(name="add_character", description="给小说添加角色",
                method="add_character",
                input_schema={"novel_id": "string", "name": "string",
                              "archetype": "string", "personality": "list",
                              "background": "string"}),
            AssetCapability(name="update_character", description="更新角色的名称/类型/性格/背景等字段",
                method="update_character",
                input_schema={"novel_id": "string", "char_id": "string",
                              "name": "string", "archetype": "string",
                              "personality": "list", "background": "string"}),
            AssetCapability(name="delete_character", description="删除指定角色",
                method="delete_character",
                input_schema={"novel_id": "string", "char_id": "string"}),
            AssetCapability(name="save_outline", description="保存小说三幕大纲",
                method="save_outline",
                input_schema={"novel_id": "string", "summary": "string",
                              "three_act": "object"}),
            AssetCapability(name="add_outline_chapter", description="添加大纲中的章节规划",
                method="add_outline_chapter",
                input_schema={"novel_id": "string", "number": "int",
                              "title": "string", "summary": "string",
                              "key_events": "list"}),
            AssetCapability(name="save_world", description="创建或更新世界观",
                method="save_world",
                input_schema={"novel_id": "string", "name": "string",
                              "overview": "string", "rules": "list"}),
            AssetCapability(name="add_scene", description="添加场景",
                method="add_scene",
                input_schema={"novel_id": "string", "name": "string",
                              "location": "string", "description": "string"}),
            AssetCapability(name="update_scene", description="更新场景的名称/地点/描述",
                method="update_scene",
                input_schema={"novel_id": "string", "scene_id": "string",
                              "name": "string", "location": "string",
                              "description": "string"}),
            AssetCapability(name="delete_scene", description="删除指定场景",
                method="delete_scene",
                input_schema={"novel_id": "string", "scene_id": "string"}),
            AssetCapability(name="chat", description="与小说创作助手对话，绑定当前小说上下文",
                method="chat",
                input_schema={"novel_id": "string", "message": "string"}),
            AssetCapability(name="character_dialogue", description="生成两个角色之间的对话",
                method="character_dialogue",
                input_schema={"novel_id": "string", "char1": "string",
                              "char2": "string", "topic": "string"}),
            AssetCapability(name="write_chapter", description="从大纲生成下一章内容",
                method="write_chapter",
                input_schema={"novel_id": "string"}),
            AssetCapability(name="update_chapter", description="更新章节标题或内容",
                method="update_chapter",
                input_schema={"novel_id": "string", "chapter_id": "string",
                              "title": "string", "content": "string"}),
            AssetCapability(name="delete_chapter", description="删除指定编号的章节",
                method="delete_chapter",
                input_schema={"novel_id": "string", "chapter_number": "int"}),
            AssetCapability(name="get_novel", description="获取小说完整数据（含所有章节、角色、世界观、大纲）",
                method="get_novel",
                input_schema={"novel_id": "string"}),
            AssetCapability(name="generate", description="根据指令生成小说内容并自动保存为章节",
                method="generate",
                input_schema={"novel_id": "string", "instruction": "string"}),
            AssetCapability(name="get_system_info", description="返回系统架构信息（数据模型、代码位置、能力清单、存储路径），供 LLM 自我诊断",
                method="get_system_info",
                side_effect_level="none",
                input_schema={}),
        ],
        visibility=Visibility.PUBLIC,
        tags=["novel", "writing", "creative"],
    )

    method_mappings = {
        "create_novel": lambda **p: _novel_create_resp(engine, **p),
        "add_character": lambda **p: _novel_add_char_resp(engine, **p),
        "update_character": lambda **p: _novel_update_char_resp(engine, **p),
        "delete_character": lambda **p: _novel_delete_char_resp(engine, **p),
        "save_outline": lambda **p: _novel_save_outline_resp(engine, **p),
        "add_outline_chapter": lambda **p: _novel_add_outline_chapter_resp(engine, **p),
        "save_world": lambda **p: _novel_create_world_resp(engine, **p),
        "add_scene": lambda **p: _novel_add_scene_resp(engine, **p),
        "update_scene": lambda **p: _novel_update_scene_resp(engine, **p),
        "delete_scene": lambda **p: _novel_delete_scene_resp(engine, **p),
        "chat": lambda **p: _novel_chat_resp(engine, **p),
        "character_dialogue": lambda **p: _novel_dialogue_resp(engine, **p),
        "write_chapter": lambda **p: _novel_write_chapter_resp(engine, **p),
        "update_chapter": lambda **p: _novel_update_chapter_resp(engine, **p),
        "delete_chapter": lambda **p: _novel_delete_chapter_resp(engine, **p),
        "get_novel": lambda **p: _novel_get_resp(engine, **p),
        "generate": lambda **p: _novel_generate_resp(engine, **p),
        "get_system_info": lambda **p: _system_info_resp(engine, **p),
    }

    try:
        runtime_center.register_asset(novel_asset, method_mappings=method_mappings)
        logger.info("✅ novel_studio RuntimeAsset registered with %d methods", len(method_mappings))
    except Exception as e:
        logger.warning("Failed to register novel_studio RuntimeAsset: %s", e)


def _register_worker(runtime_services: dict, engine) -> None:
    """注册 Worker 到 MasterControl"""
    master_control = runtime_services.get("master_control")
    if not master_control:
        return

    try:
        from app.novel_studio.worker import NovelStudioWorker
        worker = NovelStudioWorker(engine)
        master_control.register_app_worker("novel_studio", worker)
        logger.info("✅ novel_studio Worker registered")
    except Exception as e:
        logger.warning("Failed to register novel_studio Worker: %s", e)


# ---------------------------------------------------------------------------
# 资产方法响应代理（从 http_test_server 搬入）
# ---------------------------------------------------------------------------

def _novel_create_resp(engine, title="未命名", genre="", logline="", **kw):
    novel = engine.create_novel(title, genre=genre, author=kw.get("author", ""))
    if logline:
        engine.create_outline(novel.id, title, logline=logline)
    return {"success": True, "novel_id": novel.id, "title": novel.title}


def _novel_add_char_resp(engine, novel_id="", name="", archetype="",
                         personality=None, background="", speech_style="", **kw):
    char = engine.add_character(novel_id, name, archetype,
                                personality=personality or [],
                                background=background,
                                speech_style=speech_style)
    if char:
        return {"success": True, "character": {"id": char.id, "name": char.name}}
    return {"success": False, "error": "添加角色失败"}


def _novel_save_outline_resp(engine, novel_id="", summary="", three_act=None, **kw):
    engine.create_outline(novel_id, summary, three_act=three_act or {})
    return {"success": True}


def _novel_create_world_resp(engine, novel_id="", name="", overview="", rules=None, **kw):
    world = engine.create_world(novel_id, name, overview=overview, rules=rules or [])
    if world:
        return {"success": True}
    return {"success": False, "error": "创建世界观失败"}


def _novel_add_scene_resp(engine, novel_id="", name="", location="", description="", **kw):
    scene = engine.add_scene(novel_id, name, location=location, description=description)
    if scene:
        return {"success": True}
    return {"success": False, "error": "添加场景失败"}


def _novel_chat_resp(engine, novel_id="", message="", **kw):
    """同步聊天（供 RuntimeAsset 调用）"""
    import asyncio
    # 同步包装异步引擎调用
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # engine.generate_content 是 async，需要同步包装
    novel = engine.get_novel(novel_id)
    if not novel:
        return {"success": False, "error": "not_found"}
    result = loop.run_until_complete(engine.generate_content(novel_id, message))
    return {"success": True, "content": result.content}


def _novel_dialogue_resp(engine, novel_id="", char1="", char2="", topic="闲聊", **kw):
    """角色对话（供 RuntimeAsset 调用）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(engine.character_dialogue(novel_id, char1, char2, topic))
    return {"success": True, "result": result}


def _novel_write_chapter_resp(engine, novel_id="", **kw):
    """写下一章（供 RuntimeAsset 调用）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    novel = engine.get_novel(novel_id)
    if not novel or not novel.outline:
        return {"success": False, "error": "请先创建大纲"}
    next_ch = None
    for co in novel.outline.chapters:
        existing = [c for c in novel.chapters if c.number == co.number]
        if not existing:
            next_ch = co
            break
    if not next_ch:
        return {"success": False, "error": "所有章节都写完了"}
    chapter = loop.run_until_complete(engine.write_chapter(novel_id, next_ch.number))
    if chapter:
        return {"success": True, "chapter": chapter.number, "title": chapter.title}
    return {"success": False, "error": "生成失败"}


def _novel_get_resp(engine, novel_id="", **kw):
    """获取小说数据（供 RuntimeAsset 调用）"""
    novel = engine.get_novel(novel_id)
    if not novel:
        return {"success": False, "error": "not_found"}
    return {"success": True, "novel": novel.model_dump(mode="json")}


# ─── 新注册的方法响应 ──────────────────────────────────────────────


def _novel_update_char_resp(engine, novel_id="", char_id="", **kw):
    from app.novel_studio.models import CharacterArchetype
    updates = {}
    for field in ["name", "archetype", "personality", "background", "speech_style", "goal", "flaw"]:
        if field in kw:
            updates[field] = kw[field]
    if "archetype" in updates and isinstance(updates["archetype"], str):
        try:
            updates["archetype"] = CharacterArchetype(updates["archetype"])
        except ValueError:
            pass
    char = engine.update_character(novel_id, char_id, **updates)
    if char:
        return {"success": True, "character": {"id": char.id, "name": char.name}}
    return {"success": False, "error": "角色不存在"}


def _novel_delete_char_resp(engine, novel_id="", char_id="", **kw):
    ok = engine.remove_character(novel_id, char_id)
    return {"success": ok, "error": "" if ok else "角色不存在"}


def _novel_add_outline_chapter_resp(engine, novel_id="", number=1, title="", summary="", key_events=None, **kw):
    engine.add_chapter_outline(novel_id, int(number), title, summary, key_events or [])
    return {"success": True}


def _novel_update_scene_resp(engine, novel_id="", scene_id="", **kw):
    updates = {}
    for field in ["name", "location", "description", "time_period", "weather"]:
        if field in kw:
            updates[field] = kw[field]
    if not updates:
        return {"success": False, "error": "no_updates"}
    novel = engine._storage.update_scene(novel_id, scene_id, updates)
    return {"success": novel is not None, "error": "" if novel else "场景不存在"}


def _novel_delete_scene_resp(engine, novel_id="", scene_id="", **kw):
    ok = engine.remove_scene(novel_id, scene_id)
    return {"success": ok, "error": "" if ok else "场景不存在"}


def _novel_update_chapter_resp(engine, novel_id="", chapter_id="", title=None, content=None, **kw):
    updates = {}
    if title is not None:
        updates["title"] = title
    if content is not None:
        updates["content"] = content
        updates["word_count"] = len(content)
    if not updates:
        return {"success": False, "error": "no_updates"}
    novel = engine._storage.update_chapter(novel_id, chapter_id, updates)
    return {"success": novel is not None}


def _novel_delete_chapter_resp(engine, novel_id="", chapter_number=None, **kw):
    if chapter_number is None:
        return {"success": False, "error": "缺少 chapter_number"}
    ok = engine._storage.delete_chapter(novel_id, int(chapter_number))
    return {"success": ok}


def _novel_generate_resp(engine, novel_id="", instruction="", **kw):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(engine.generate_content(novel_id, instruction))
    from app.novel_studio.api import _try_save_as_outline, _save_as_chapter
    from app.novel_studio.models import Chapter
    content = result.content if hasattr(result, 'content') else str(result)
    chapter_info = None
    if content and len(content) >= 100:
        import re
        if re.search(r'大纲|梗概|三幕', instruction):
            _try_save_as_outline(novel_id, content, engine)
        else:
            novel = engine.get_novel(novel_id)
            if novel and novel.chapters:
                chapter_number = max(c.number for c in novel.chapters) + 1
            else:
                chapter_number = 1
            chapter = Chapter(number=chapter_number, title="生成内容", content=content, word_count=len(content))
            engine._storage.add_chapter(novel_id, chapter)
            chapter_info = {"number": chapter_number, "title": "生成内容"}
    return {"success": True, "content": content, "chapter": chapter_info}


def _system_info_resp(engine, **kw):
    """返回系统架构信息"""
    return {"success": True, "info": engine.get_system_info()}
