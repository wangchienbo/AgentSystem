"""Pipeline — 小说生成管道：模块化、可编排、角色隔离

每个模块 = 一个独立 skill，负责单一创作环节。
模块间通过 PipelineContext 传递数据，角色/场景隔离由 SceneManager + CharacterAgent 保证。
"""
from __future__ import annotations

import abc
import logging
from typing import Any
from .prompt_loader import build_novel_context  # noqa: E402,F401


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
        context_center=None,
        llm_client=None,
        model_router=None,
    ):
        self.novel_id = novel_id
        self._storage = storage
        self._agent_registry = agent_registry
        self._scene_manager = scene_manager
        self._world_module = world_module
        self._context_center = context_center
        self._llm_client = llm_client
        self._model_router = model_router

        # 模块间的数据传递（命名空间隔离）
        self._outputs: dict[str, Any] = {}

        # 管道执行状态
        self._step_results: list[dict] = []  # 每一步的进度记录
        self._novel_cache = None

        # 角色决策回调（流式进度）
        self._character_decided_callback = None

        # 审核与重生成循环
        self.regeneration_feedback: str | None = None
        self.regeneration_count: int = 0
        self.needs_regeneration: bool = False  # 任何 step 设置此标记即可触发回退

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

    def save_novel(self):
        """将当前内存中的小说数据保存到 storage"""
        if self._novel_cache is not None:
            self._storage.save_novel(self._novel_cache)

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

    # ── 角色决策回调（流式进度核心） ──

    def set_character_decided_callback(self, callback):
        """设置每个角色决策完成后的回调 (result_dict) -> None"""
        self._character_decided_callback = callback

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
        "world_design",      # ① 世界观事件池设计（仅首次，已有则跳过）
        "world_check",        # ② 世界观完整性门禁（缺失则阻断）
        "world_evolve",       # ③ 世界演化：触发事件 + 推进 + 涟漪 + 归档
        "chapter_plan",       # ④ 大纲预测本章
        "scene_loop",         # ⑤ 场景级循环：预测→环境→角色→重预测 × N
        "narrative",          # ⑥ 叙事合成（多场景+连续性）
        "setting_check",      # ⑦ 设定一致性交叉比对（独立LLM调用）
        "editorial_review",   # ⑧ 章节质量审核（读者视角评分）
        "character_emerge",   # ⑨ 角色涌现（自动发现新角色）
        "memory_update",      # ⑩ 保存记忆
    ],
    "write_next_chapter_legacy": [
        "world_design",      # ① 世界观事件池设计（仅首次）
        "world_check",        # ② 世界观完整性门禁
        "world_evolve",       # ③ 世界演化
        "chapter_plan",       # ④ 查大纲定本章目标
        "scene_sequence",     # ⑤ 按4原则生成多场景序列
        "scene_build",        # ⑥ 细化所有场景的感官细节
        "character_action",   # ⑦ 每个角色在各自场景独立决策
        "narrative",          # ⑧ 合成叙事（多场景+上一章结尾）
        "setting_check",      # ⑨ 设定一致性交叉比对
        "editorial_review",   # ⑩ 章节质量审核
        "memory_update",      # ⑪ 保存记忆
    ],
    "quick_write": [
        "world_design",
        "world_check",
        "world_evolve",
        "chapter_plan",
        "scene_sequence",
        "scene_build",
        "character_action",
        "narrative",
        "setting_check",
        "editorial_review",
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


# ─── 小说级上下文构建器 ───────────────────────────────────────


def build_novel_context(novel) -> str:
    """从 Novel 对象构建统一的「小说级上下文块」

    包含小说类型、世界观设定、世界规则、专属写作指令等信息。
    注入到每个 pipeline 步骤的 prompt 中，让 LLM 始终了解小说的核心设定。

    返回格式化的标记块，可注入到任意 prompt 顶部。
    """
    if novel is None:
        return ""

    parts = [
        f"【小说】{novel.title}",
        f"【类型】{novel.genre}" if novel.genre else "",
    ]

    # 小说简介（面向用户的故事概述，也帮助 AI 理解故事定位）
    description = getattr(novel, "description", "") or ""
    if description:
        parts.append(f"【小说简介】{description}")

    # 世界观概述
    world = getattr(novel, "world", None)
    if world is not None:
        overview = getattr(world, "overview", "") or ""
        if overview:
            parts.append(f"【世界观概述】{overview}")
        rules = getattr(world, "rules", None) or []
        if rules:
            parts.append("【世界规则】")
            for r in rules:
                parts.append(f"  {r}")

    # 小说专属写作指令/提示词
    custom_prompt = getattr(novel, "custom_prompt", "") or ""
    if custom_prompt:
        parts.append(f"【小说专属写作指令】\n{custom_prompt}")

    # 过滤空段落
    parts = [p for p in parts if p]

    if not parts:
        return ""

    context = "\n".join(parts)
    return f"\n## 📖 小说核心设定\n{context}\n"
