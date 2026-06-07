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
    from app.system.auth import require_auth
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

    engine = NovelStudioEngine(storage=None, model_router=model_router, context_center=runtime_services.get("context_center"))
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
        model_input_builder=runtime_services.get("model_input_builder"),
        require_auth=require_auth,
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
            AssetCapability(name="create_novel", description="创建一本新小说。自动生成 novel_id。返回 novel 对象含 id/title/genre/logline。示例：create_novel(title=\"穿越大明\", genre=\"历史奇幻\", logline=\"...\")",
                method="create_novel",
                input_schema={"title": {"type": "string", "desc": "书名"},
                              "genre": {"type": "string", "desc": "题材"},
                              "logline": {"type": "string", "desc": "一句话梗概"}}),
            AssetCapability(name="add_character", description="给小说添加角色。archetype 可选：protagonist/antagonist/mentor/ally。返回 character 对象。",
                method="add_character",
                input_schema={"novel_id": "string", "name": "string",
                              "archetype": "string", "personality": "list",
                              "background": "string"}),
            AssetCapability(name="update_character", description="更新已有角色的字段(名称/类型/性格/背景等)，只传需修改的参数即可。返回更新后的 character 对象。",
                method="update_character",
                input_schema={"novel_id": "string", "char_id": "string",
                              "name": "string", "archetype": "string",
                              "personality": "list", "background": "string"}),
            AssetCapability(name="delete_character", description="删除指定角色。返回 {message: 删除成功}。",
                method="delete_character",
                input_schema={"novel_id": "string", "char_id": "string"}),
            AssetCapability(name="save_outline", description="保存小说三幕大纲。three_act 为含 act1/act2/act3 的字典。返回 outline 对象。",
                method="save_outline",
                input_schema={"novel_id": "string", "summary": "string",
                              "three_act": "object"}),
            AssetCapability(name="add_outline_chapter", description="在大纲中添加章节规划。number 为序号。返回 chapter 对象。",
                method="add_outline_chapter",
                input_schema={"novel_id": "string", "number": "int",
                              "title": "string", "summary": "string",
                              "key_events": "list"}),
            AssetCapability(name="save_world", description="创建或更新世界观设定。rules 是规则列表。返回 world 对象。",
                method="save_world",
                input_schema={"novel_id": "string", "name": "string",
                              "overview": "string", "rules": "list"}),
            AssetCapability(name="add_scene", description="添加场景设定。返回 scene 对象含 id/name/location。",
                method="add_scene",
                input_schema={"novel_id": "string", "name": "string",
                              "location": "string", "description": "string"}),
            AssetCapability(name="update_scene", description="更新场景的字段，只传需修改的参数。返回更新后的 scene 对象。",
                method="update_scene",
                input_schema={"novel_id": "string", "scene_id": "string",
                              "name": "string", "location": "string",
                              "description": "string"}),
            AssetCapability(name="delete_scene", description="删除指定场景。返回 {message: 删除成功}。",
                method="delete_scene",
                input_schema={"novel_id": "string", "scene_id": "string"}),
            AssetCapability(name="chat", description="与小说创作助手对话，绑定当前小说上下文。进行创作讨论或咨询建议。",
                method="chat",
                input_schema={"novel_id": "string", "message": "string"}),
            AssetCapability(name="save_chapter", description="直接保存已撰写的章节到小说。content 须为纯叙事正文（不含评论/摘要）。返回 chapter 对象含 id/number/title/content。示例：save_chapter(novel_id=\"...\", title=\"第一章\", content=\"正文...\")",
                method="save_chapter",
                input_schema={"novel_id": "string", "title": "string", "content": "string", "number": "int"}),
            AssetCapability(name="update_chapter", description="更新章节的标题或内容。返回更新后的 chapter 对象含 id/number/title/content。",
                method="update_chapter",
                input_schema={"novel_id": "string", "chapter_id": "string",
                              "title": "string", "content": "string"}),
            AssetCapability(name="delete_chapter", description="按章节编号删除章节。返回 {message: 删除成功}。",
                method="delete_chapter",
                input_schema={"novel_id": "string", "chapter_number": "int"}),
            AssetCapability(name="get_novel", description="获取小说完整数据（含大纲章节规划、已写章节、角色、世界观、场景）。一次调用返回全部信息，是权威数据源。返回 novel_data 含 outline/chapters/characters/world/scenes 等。",
                method="get_novel",
                input_schema={"novel_id": "string"}),
            AssetCapability(name="generate", description="根据指令自动生成小说内容并保存为章节。AI 根据 instruction 创作并写入数据库。返回生成的 chapter 对象。",
                method="generate",
                input_schema={"novel_id": "string", "instruction": "string"}),
            AssetCapability(name="save_custom_prompt", description="设置小说的专属提示词/写作指令，控制 AI 写作风格和方向。返回 {message: 保存成功}。",
                method="save_custom_prompt",
                input_schema={"novel_id": "string", "custom_prompt": "string"}),
            AssetCapability(name="save_description", description="设置/更新小说简介（面向读者的故事概述）。返回 {message: 保存成功}。",
                method="save_description",
                input_schema={"novel_id": "string", "description": "string"}),
            AssetCapability(name="get_system_info", description="返回系统架构信息：源代码文件列表、能力清单、存储路径、启动命令。用于 LLM 自我诊断或回答代码相关的问题。",
                method="get_system_info",
                side_effect_level="none",
                input_schema={}),
            AssetCapability(name="delete_chapter_range", description="批量删除指定编号区间的章节。返回删除数量。",
                method="delete_chapter_range",
                input_schema={"novel_id": "string", "chapter_from": "int", "chapter_to": "int"}),
            AssetCapability(name="add_chapter", description="手动添加一个空章节。title 可选，默认自动命名。返回 chapter 对象。",
                method="add_chapter",
                input_schema={"novel_id": "string", "title": "string"}),
            AssetCapability(name="list_sessions", description="获取当前小说下的所有对话会话列表。",
                method="list_sessions",
                input_schema={"novel_id": "string"}),
            AssetCapability(name="create_session", description="创建新的对话会话并设为当前。返回 session_uuid。",
                method="create_session",
                input_schema={"novel_id": "string", "label": "string"}),
            AssetCapability(name="switch_session", description="切换到已有会话。",
                method="switch_session",
                input_schema={"novel_id": "string", "session_uuid": "string"}),
            AssetCapability(name="delete_session", description="删除指定会话及其聊天记录。",
                method="delete_session",
                input_schema={"novel_id": "string", "session_uuid": "string"}),
            AssetCapability(name="get_task", description="获取生成任务状态和事件列表（支持增量拉取 via from_event）。",
                method="get_task",
                input_schema={"task_id": "string", "from_event": "int"}),
            AssetCapability(name="get_latest_task", description="获取某小说的最新生成任务。",
                method="get_latest_task",
                input_schema={"novel_id": "string"}),
            AssetCapability(name="export_novel", description="导出小说全文文本。format 当前支持 text。返回 content 字符串。",
                method="export_novel",
                input_schema={"novel_id": "string", "format": "string"}),
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
        "save_chapter": lambda **p: _novel_save_chapter_resp(engine, **p),
        "update_chapter": lambda **p: _novel_update_chapter_resp(engine, **p),
        "delete_chapter": lambda **p: _novel_delete_chapter_resp(engine, **p),
        "get_novel": lambda **p: _novel_get_resp(engine, **p),
        "save_custom_prompt": lambda **p: {"success": engine.update_custom_prompt(p.get("novel_id", ""), p.get("custom_prompt", "")) is not None},
        "save_description": lambda **p: {"success": engine.update_description(p.get("novel_id", ""), p.get("description", "")) is not None},
        "get_system_info": lambda **p: _system_info_resp(engine, **p),
        "delete_chapter_range": lambda **p: _novel_delete_range_resp(engine, **p),
        "add_chapter": lambda **p: _novel_add_chapter_resp(engine, **p),
        "list_sessions": lambda **p: _session_list_resp(engine, **p),
        "create_session": lambda **p: _session_create_resp(engine, **p),
        "switch_session": lambda **p: _session_switch_resp(engine, **p),
        "delete_session": lambda **p: _session_delete_resp(engine, **p),
        "get_task": lambda **p: _task_get_resp(engine, **p),
        "get_latest_task": lambda **p: _task_latest_resp(engine, **p),
        "export_novel": lambda **p: _export_novel_resp(engine, **p),
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


def _novel_save_chapter_resp(engine, novel_id="", title="", content="", number=None, **kw):
    """保存 LLM 撰写的章节内容到小说。带验证：只接受纯中文叙事文本。"""
    import logging
    _log = logging.getLogger(__name__)

    if not content or len(content) < 500:
        _log.warning("save_chapter rejected: too short (%s chars)", len(content) if content else 0)
        return {"success": False, "error": "章节内容太短（至少500字），看起来不是完整的章节正文。"}

    # 统计中文占比
    chinese_count = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
    chinese_ratio = chinese_count / max(len(content), 1)

    # 前200字符特征检测
    head = content.strip()[:200]
    has_bold_marker = '**' in head[:50]
    has_reply_markers = any(m in head for m in ['已成功', '已保存', '章节', 'Chapter', 'Response'])
    starts_with_emoji = any(head.startswith(e) for e in ['✅', '📖', '🎭', '⭐', '🔥', '💀'])
    has_meta_markers = head.startswith('**') or ':', ': ' in head[:30]

    # 决策：是回复文本还是章节正文？
    is_response = (
        starts_with_emoji
        or (has_bold_marker and chinese_ratio < 0.6)
        or (chinese_ratio < 0.5)
        or (has_reply_markers and chinese_ratio < 0.7)
    )

    _log.info(
        "save_chapter decision novel=%s title=%s len=%s chinese_ratio=%.0f%% marker=%s response=%s",
        novel_id, title, len(content), chinese_ratio * 100, has_bold_marker or starts_with_emoji, is_response,
    )

    if is_response:
        return {"success": False, "error": "内容看起来是回复文本而非章节正文。save_chapter 只用于保存纯叙事章节内容。"}

    if not title:
        existing = engine.get_novel(novel_id)
        next_num = max((c.number for c in existing.chapters), default=0) + 1 if existing else 1
        title = f"第{next_num}章"

    chapter = engine.add_chapter(novel_id, title, content, number=int(number) if number else None)
    if chapter:
        return {"success": True, "chapter": {"number": chapter.number, "title": chapter.title, "word_count": chapter.word_count}}
    return {"success": False, "error": "保存章节失败"}


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


def _system_info_resp(engine, **kw):
    """返回系统架构信息"""
    return {"success": True, "info": engine.get_system_info()}


# ──── 新增能力：批量删除章节 ──────────────────────────────


def _novel_delete_range_resp(engine, novel_id="", chapter_from=0, chapter_to=0, **kw):
    if not novel_id or chapter_from <= 0 or chapter_to < chapter_from:
        return {"success": False, "error": "参数错误"}
    deleted = engine._storage.delete_chapters_range(novel_id, int(chapter_from), int(chapter_to))
    return {"success": True, "deleted_count": deleted}


# ──── 新增能力：手动添加空章节 ──────────────────────────


def _novel_add_chapter_resp(engine, novel_id="", title="", **kw):
    """手动添加空章节"""
    from app.novel_studio.pipeline.step_chapter_plan import determine_chapter_number
    number = determine_chapter_number(engine._storage, novel_id)
    ch = engine._storage.add_chapter(novel_id, number=number, title=title or f"第{number}章")
    if ch:
        return {"success": True, "chapter": {"id": ch.id, "number": ch.number, "title": ch.title, "content": ch.content}}
    return {"success": False, "error": "添加失败"}


# ──── 新增能力：会话管理 ──────────────────────────────────


def _session_list_resp(engine, novel_id="", username="", **kw):
    from app.novel_studio.api import _session_store
    if not novel_id:
        return {"success": False, "error": "缺少 novel_id"}
    sessions = _session_store.list_sessions(username, novel_id)
    return {"success": True, "sessions": sessions, "count": len(sessions)}


def _session_create_resp(engine, novel_id="", username="", label="", **kw):
    from app.novel_studio.api import _session_store, context_center, get_or_create_novel_session
    if not novel_id:
        return {"success": False, "error": "缺少 novel_id"}
    session_uuid = _session_store.create_session(username, novel_id, label)
    session_id = get_or_create_novel_session(novel_id, context_center, user_id=username, session_uuid=session_uuid)
    return {"success": True, "session_uuid": session_uuid, "session_id": session_id}


def _session_switch_resp(engine, novel_id="", username="", session_uuid="", **kw):
    from app.novel_studio.api import _session_store
    if not novel_id or not session_uuid:
        return {"success": False, "error": "缺少 novel_id 或 session_uuid"}
    ok = _session_store.switch_session(username, novel_id, session_uuid)
    return {"success": ok, "error": "" if ok else "会话不存在"}


def _session_delete_resp(engine, novel_id="", username="", session_uuid="", **kw):
    from app.novel_studio.api import _session_store
    if not novel_id or not session_uuid:
        return {"success": False, "error": "缺少 novel_id 或 session_uuid"}
    ok = _session_store.delete_session(username, novel_id, session_uuid)
    return {"success": ok, "error": "" if ok else "会话不存在"}


# ──── 新增能力：任务状态查询 ──────────────────────────────


def _task_get_resp(engine, task_id="", from_event=0, **kw):
    from app.novel_studio.task_manager import get_task
    task = get_task(task_id)
    if not task:
        return {"success": False, "error": "任务未找到"}
    data = task.to_dict(from_event_index=from_event)
    data["success"] = True
    return data


def _task_latest_resp(engine, novel_id="", **kw):
    from app.novel_studio.task_manager import get_latest_task
    if not novel_id:
        return {"success": False, "error": "缺少 novel_id"}
    task = get_latest_task(novel_id)
    if not task:
        return {"success": True, "task": None}
    return {"success": True, "task": task.to_dict()}


# ──── 新增能力：导出小说 ──────────────────────────────────


def _export_novel_resp(engine, novel_id="", format="text", **kw):
    """导出小说文本"""
    novel = engine.get_novel(novel_id)
    if not novel:
        return {"success": False, "error": "小说不存在"}
    if format == "text":
        lines = [f"# {novel.title}", ""]
        for ch in getattr(novel, "chapters", []):
            lines.append(f"## 第{ch.number}章 {ch.title}")
            lines.append("")
            lines.append(ch.content or "")
            lines.append("")
        text = "\n".join(lines)
        return {"success": True, "format": "text", "content": text, "length": len(text)}
    return {"success": False, "error": f"不支持的格式: {format}"}
