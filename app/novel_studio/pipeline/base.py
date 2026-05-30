"""Pipeline — 小说生成管道：模块化、可编排、角色隔离

每个模块 = 一个独立 skill，负责单一创作环节。
模块间通过 PipelineContext 传递数据，角色/场景隔离由 SceneManager + CharacterAgent 保证。
"""
from __future__ import annotations

import abc
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PipelineContext:
    """小说管道的上下文容器

    - 不直接持有 Novel 引用，始终通过 novel_id + storage 获取最新数据
    - 每个模块读写自己的命名空间 (_outputs[module_name])
    - 角色隔离委托 CharacterAgentRegistry（每个角色独立记忆）
    - 场景感知隔离委托 SceneManager（get_perception 过滤信息）
    """

    def __init__(
        self,
        novel_id: str,
        storage,
        agent_registry,
        scene_manager,
        world_module,
        llm_client=None,
        model_router=None,
    ):
        self.novel_id = novel_id
        self._storage = storage
        self._agent_registry = agent_registry
        self._scene_manager = scene_manager
        self._world_module = world_module
        self._llm_client = llm_client
        self._model_router = model_router

        # 模块间的数据传递（命名空间隔离）
        self._outputs: dict[str, Any] = {}

        # 管道执行状态
        self._step_results: list[dict] = []  # 每一步的进度记录
        self._novel_cache = None

    # ── 小说数据 ──

    @property
    def novel(self):
        """当前小说数据（延迟加载，始终从 storage 取最新）"""
        if self._novel_cache is None:
            self._novel_cache = self._storage.get_novel(self.novel_id)
        return self._novel_cache

    def refresh_novel(self):
        """强制重新加载小说数据（其他模块可能修改了 storage）"""
        self._novel_cache = self._storage.get_novel(self.novel_id)

    # ── 模块间数据传递 ──

    def get_output(self, name: str, default=None):
        """读取其他模块的输出"""
        return self._outputs.get(name, default)

    def set_output(self, name: str, data: Any):
        """写入本模块的输出"""
        self._outputs[name] = data

    # ── 角色 Agent 隔离 ──

    def get_agent_by_name(self, name: str):
        """按名称获取角色 Agent"""
        return self._agent_registry.get_by_name(name)

    def get_agent_by_id(self, char_id: str):
        """按 ID 获取角色 Agent"""
        return self._agent_registry.get(char_id)

    def ensure_agents(self, characters: dict) -> None:
        """确保所有角色都有 Agent 注册（首次加载或新增角色时调用）"""
        for cid, char in characters.items():
            if not self._agent_registry.get(cid):
                self._agent_registry.register(char)

    # ── 场景感知隔离 ──

    def place_character_in_scene(self, character, scene_id: str) -> None:
        """将角色放入场景"""
        self._scene_manager.place_character(character, scene_id)

    def add_scene_to_manager(self, scene) -> None:
        """向 SceneManager 注册场景"""
        self._scene_manager.add_scene(scene)

    def get_perception(self, char_id: str):
        """获取角色在当前场景的感知（信息隔离核心）"""
        return self._scene_manager.get_perception(char_id)

    def get_occupants(self, scene_id: str):
        """获取场景内所有角色"""
        return self._scene_manager.get_occupants(scene_id)

    def get_visible_chars(self, char_id: str):
        """角色能看到谁（排除自己）"""
        return self._scene_manager.get_visible_chars(char_id)

    # ── 世界模块 ──

    @property
    def world_module(self):
        return self._world_module

    # ── LLM 客户端 ──

    def get_llm_client(self, profile: str = "novel_writer"):
        if self._llm_client:
            return self._llm_client
        if self._model_router:
            return self._model_router.get_client(profile)
        return None

    # ── 进度记录 ──

    def record_step(self, module_name: str, status: str, summary: str, detail: Any = None):
        self._step_results.append({
            "module": module_name,
            "status": status,
            "summary": summary,
            "detail": detail,
        })

    def get_progress(self) -> list[dict]:
        return list(self._step_results)


class BaseModule(abc.ABC):
    """所有管道模块的基类

    每个模块：
    - 有唯一的 name（用作 ctx._outputs 的命名空间）
    - 通过 execute(ctx) 执行
    - 通过 ctx.get_output() 读其他模块的输出
    - 通过 ctx.set_output() 写自己的输出
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """模块唯一名称（用作输出命名空间 key）"""
        ...

    @property
    def modifies_storage(self) -> bool:
        """执行后是否修改了持久化数据（用于触发 ctx.refresh_novel）"""
        return False

    @property
    def description(self) -> str:
        """模块的中文描述（用于 UI 进度展示）"""
        return ""

    @abc.abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """执行模块逻辑"""
        ...


# 常用管道模板
PIPELINE_TEMPLATES: dict[str, list[str]] = {
    "write_next_chapter": [
        "chapter_plan",       # ① 查大纲定本章目标
        "scene_build",        # ② 选场景定参与者
        "character_action",   # ③ 每个角色独立决策
        "narrative",          # ④ 合成叙事章节
        "memory_update",      # ⑤ 保存记忆
    ],
    "quick_write": [
        "chapter_plan",
        "scene_build",
        "character_action",
        "narrative",
    ],
    "character_chat": [
        "scene_build",
        "character_action",
    ],
    "timeline_advance": [
        "timeline_advance",
        "memory_update",
    ],
}
