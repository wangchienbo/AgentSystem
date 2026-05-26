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
    router = create_novel_router(model_router=model_router, llm_client=llm_client, engine=engine)

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

    _bootstrapped = True
    return {"engine": engine, "router": router}


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
        description="小说创作应用，支持创建小说、管理角色、大纲、世界观、章节生成",
        asset_type=AssetType.APP,
        asset_kind=AssetKind.MATERIALIZED,
        version="1.0.0",
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
            AssetCapability(name="save_outline", description="保存小说三幕大纲",
                method="save_outline",
                input_schema={"novel_id": "string", "summary": "string",
                              "three_act": "object"}),
            AssetCapability(name="save_world", description="创建或更新世界观",
                method="save_world",
                input_schema={"novel_id": "string", "name": "string",
                              "overview": "string", "rules": "list"}),
            AssetCapability(name="add_scene", description="添加场景",
                method="add_scene",
                input_schema={"novel_id": "string", "name": "string",
                              "location": "string", "description": "string"}),
        ],
        visibility=Visibility.PUBLIC,
        tags=["novel", "writing", "creative"],
    )

    method_mappings = {
        "create_novel": lambda **p: _novel_create_resp(engine, **p),
        "add_character": lambda **p: _novel_add_char_resp(engine, **p),
        "save_outline": lambda **p: _novel_save_outline_resp(engine, **p),
        "save_world": lambda **p: _novel_create_world_resp(engine, **p),
        "add_scene": lambda **p: _novel_add_scene_resp(engine, **p),
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
