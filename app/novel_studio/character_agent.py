"""Novel Studio — 角色 Agent（演化版）

每个角色 = 一个 Agent，拥有：
- 独立记忆系统
- 场景感知（不在同一场景就不知道）
- 知识过滤（没渠道知道的事不提及）

ContextCenter 集成：每个角色拥有独立的 SessionNode，
记忆通过 SessionContextRecord 持久化到磁盘，服务重启不丢失。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.novel_studio.models import (
    Character, Memory, CharacterPerception, DialogueLine, StorySegment,
    Attributes, EquipmentItem, Faction,
)
from app.ai.model_router import ModelRouter
from app.models.context import SessionContextRecord, SessionNode

logger = logging.getLogger(__name__)


class CharacterAgent:
    """角色 Agent——代表一个角色的行为、记忆和知识边界

    ContextCenter 集成：每个角色拥有独立的 SessionNode，
    记忆通过 SessionContextRecord 持久化到磁盘。
    """

    def __init__(
        self,
        character: Character,
        model_router: ModelRouter | None = None,
        context_center=None,
        character_session_id: str = "",
    ):
        self._char = character
        self._router = model_router
        self._context_center = context_center
        self._character_session_id = character_session_id
        # 角色记忆（角色自己的视角）— 内存缓存，启动时从 ContextCenter 加载
        self._memories: list[Memory] = []
        self._max_memories = 100
        # 启动时从持久化加载记忆
        if self._context_center and self._character_session_id:
            self._load_persisted_memories()

    @property
    def name(self) -> str:
        return self._char.name

    @property
    def character(self) -> Character:
        return self._char

    @property
    def memories(self) -> list[Memory]:
        return self._memories

    # ── 记忆管理 ──

    def add_memory(
        self, content: str, scene_id: str = "",
        participants: list[str] | None = None,
        importance: float = 0.5, tags: list[str] | None = None,
    ) -> Memory:
        """添加一条记忆（角色视角），同时写入 ContextCenter 持久化"""
        mem = Memory(
            timestamp=len(self._memories),
            content=content,
            scene_id=scene_id,
            char_pov=self._char.name,
            participants=participants or [],
            importance=importance,
            tags=tags or [],
        )
        self._memories.append(mem)
        # 写入 ContextCenter 持久化
        if self._context_center and self._character_session_id:
            try:
                record = SessionContextRecord(
                    session_id=self._character_session_id,
                    kind="message",
                    role="assistant",
                    content=content,
                    metadata={
                        "scene_id": scene_id,
                        "importance": importance,
                        "timestamp": len(self._memories),
                    },
                )
                self._context_center.append_context_record(
                    session_id=self._character_session_id,
                    record=record,
                )
            except Exception as e:
                logger.warning("角色 %s 记忆持久化失败: %s", self._char.name, e)
        # 简单遗忘机制：超出上限时丢掉最不重要的
        if len(self._memories) > self._max_memories:
            self._memories.sort(key=lambda m: m.importance)
            self._memories = self._memories[-self._max_memories:]
        return mem

    def get_knowing_summary(self, max_items: int = 10) -> str:
        """角色"知道的事"摘要——用于构造 Agent prompt"""
        if not self._memories:
            return f"{self._char.name}还没有任何记忆。"

        # 按重要度排序取最近+最重要的
        sorted_mems = sorted(self._memories, key=lambda m: (-m.importance, -self._memories.index(m)))
        selected = sorted_mems[:max_items]
        lines = [f"{self._char.name}记得的事："]
        for m in selected:
            line = f"  - {m.content}"
            if m.participants:
                line += f"（和{'、'.join(m.participants)}在一起）"
            lines.append(line)
        return "\n".join(lines)

    def has_tag_knowledge(self, tag: str) -> bool:
        """角色是否知道某个信息标签"""
        for m in self._memories:
            if tag in m.tags:
                return True
        return False

    def _load_persisted_memories(self) -> int:
        """从 ContextCenter 加载持久化的记忆到内存缓存"""
        loaded = 0
        try:
            window = self._context_center.get_recent_context(
                session_id=self._character_session_id,
                limit=self._max_memories,
            )
            for rec in window.records:
                meta = rec.metadata or {}
                mem = Memory(
                    timestamp=meta.get("timestamp", loaded),
                    content=rec.content,
                    scene_id=meta.get("scene_id", ""),
                    char_pov=self._char.name,
                    participants=[],
                    importance=meta.get("importance", 0.5),
                    tags=[],
                )
                self._memories.append(mem)
                loaded += 1
        except Exception as e:
            logger.warning("角色 %s 加载持久记忆失败: %s", self._char.name, e)
        return loaded

    @property
    def knowledge_context(self) -> str:
        """角色在 ContextCenter 中的知识摘要——用于构建去中心化决策 Prompt"""
        if not self._context_center or not self._character_session_id:
            return self.get_knowing_summary(5)
        try:
            window = self._context_center.get_recent_context(
                session_id=self._character_session_id,
                limit=10,
            )
            records = window.records
            if not records:
                return f"{self._char.name}还没有任何记忆。"
            parts = [f"{self._char.name}记得的事："]
            for rec in reversed(records):
                content = rec.content
                meta = rec.metadata or {}
                participants = meta.get("participants", [])
                if participants:
                    content += f"（和{'、'.join(participants)}在一起）"
                parts.append(f"  - {content}")
            return "\n".join(parts)
        except Exception:
            return self.get_knowing_summary(5)

    # ── Agent 决策 ──

    def build_character_sheet_prompt(self) -> str:
        """角色面板描述——注入决策 prompt 头部"""
        char = self._char
        parts = [f"姓名：{char.name}"]
        if char.personality:
            parts.append(f"性格：{'、'.join(char.personality)}")
        if char.background:
            parts.append(f"背景：{char.background}")
        if char.goal:
            parts.append(f"目标：{char.goal}")
        if char.speech_style:
            parts.append(f"说话风格：{char.speech_style}")
        if char.special_ability:
            parts.append(f"特殊能力：{char.special_ability}")
        if char.relationships:
            rels = [f"{k}（{v}）" for k, v in char.relationships.items()]
            parts.append(f"人际关系：{'、'.join(rels[:5])}")
        if char.appearance:
            parts.append(f"外貌：{char.appearance}")
        if char.skills:
            parts.append(f"技能：{'、'.join(char.skills[:5])}")
        return "\n".join(parts)

    # ── 对话生成 ──

    def generate_dialogue_line(
        self, context: str, speaking_to: str | None = None,
        topic: str | None = None, emotion: str | None = None,
    ) -> str:
        """生成一句角色台词（基于角色设定和当前上下文）"""
        try:
            if self._router:
                client = self._router.get_client("novel_writer")
                if client:
                    prompt = self.build_character_sheet_prompt()
                    prompt += f"\n当前场景：{context}"
                    if speaking_to:
                        prompt += f"\n说话对象：{speaking_to}"
                    if emotion:
                        prompt += f"\n情绪状态：{emotion}"
                    if topic:
                        prompt += f"\n话题：{topic}"
                    prompt += f"\n请以{self._char.name}的身份说一句话。保持角色性格。直接输出对话内容。"
                    messages = [
                        {"role": "system", "content": f"你正在扮演{self._char.name}。"},
                        {"role": "user", "content": prompt},
                    ]
                    text, _ = client.chat(
                        messages,
                        max_tokens=300,
                        temperature=0.85,
                        stream=False,
                    )
                    return (text or "……").strip()
            return "……"
        except Exception as e:
            logger.warning("角色 %s 对话失败: %s", self._char.name, e)
            return "……"

    def add_to_history(self, role: str, content: str) -> None:
        """将对话记录加入角色记忆"""
        self.add_memory(
            content=content,
            participants=[role] if role != "user" else [],
            importance=0.6,
            tags=["dialogue"],
        )

    def _parse_decision(self, text: str) -> dict[str, str]:
        """解析角色决策输出"""
        result = {"action": "", "dialogue": "", "inner": "", "perception": ""}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("感知：") or line.startswith("感知:"):
                result["perception"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("行动：") or line.startswith("行动:"):
                result["action"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("对话：") or line.startswith("对话:"):
                result["dialogue"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("内心：") or line.startswith("内心:"):
                result["inner"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        if not result["action"]:
            result["action"] = text[:50]
        return result

    # ── 序列化 ──

    def to_serializable(self) -> dict:
        return {
            "character": self._char.model_dump(mode="json") if hasattr(self._char, "model_dump") else {},
            "memories": [m.model_dump(mode="json") if hasattr(m, "model_dump") else {} for m in self._memories],
        }

    @classmethod
    def from_serializable(cls, data: dict, model_router=None) -> "CharacterAgent":
        char = Character(**data.get("character", {}))
        agent = cls(char, model_router=model_router)
        for m_data in data.get("memories", []):
            agent._memories.append(Memory(**m_data))
        return agent


class CharacterAgentRegistry:
    """角色 Agent 注册中心

    ContextCenter 集成：注册角色时自动创建持久化记忆 SessionNode。
    """

    def __init__(self, model_router: ModelRouter | None = None, context_center=None):
        self._agents: dict[str, CharacterAgent] = {}
        self._router = model_router
        self._context_center = context_center
        self._novel_id: str = ""

    def set_novel_context(self, novel_id: str):
        """设置当前小说 ID，用于构建角色会话路径"""
        self._novel_id = novel_id

    def register(self, character: Character, novel_id: str = "") -> CharacterAgent:
        """注册角色，自动创建 ContextCenter 会话（如已配置）"""
        novel_id = novel_id or self._novel_id
        char_session_id = ""
        if self._context_center and novel_id:
            char_session_id = f"novel_{novel_id}_char_{character.id}"
            novel_session_id = f"novel_{novel_id}"
            try:
                # 创建小说的根会话
                root_node = self._context_center.get_session_node(novel_session_id)
                if root_node is None:
                    root_node = SessionNode(
                        session_id=novel_session_id,
                        user_id="novel_studio",
                        channel="novel_system",
                        kind="root",
                        actor="system",
                        topic_key=novel_id,
                    )
                    self._context_center.register_session_node(root_node)
                # 创建角色的子会话
                char_node = self._context_center.get_session_node(char_session_id)
                if char_node is None:
                    char_node = SessionNode(
                        session_id=char_session_id,
                        user_id="novel_studio",
                        channel="novel_character",
                        kind="child",
                        actor="app",
                        parent_session_id=novel_session_id,
                        root_session_id=novel_session_id,
                        topic_key=character.name,
                    )
                    self._context_center.register_session_node(char_node)
            except Exception as e:
                logger.warning("角色 %s 会话创建失败: %s", character.name, e)

        agent = CharacterAgent(
            character,
            model_router=self._router,
            context_center=self._context_center,
            character_session_id=char_session_id,
        )
        self._agents[character.id] = agent
        return agent

    def get(self, char_id: str) -> CharacterAgent | None:
        return self._agents.get(char_id)

    def get_by_name(self, name: str) -> CharacterAgent | None:
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def __len__(self) -> int:
        return len(self._agents)

    def __iter__(self):
        return iter(self._agents.values())

    def __contains__(self, char_id: str) -> bool:
        return char_id in self._agents

    def remove(self, char_id: str) -> bool:
        """移除角色 Agent 并清理 ContextCenter 会话"""
        agent = self._agents.pop(char_id, None)
        if agent is None:
            return False
        if self._context_center and agent._character_session_id:
            try:
                self._context_center.unregister_session(agent._character_session_id)
            except Exception as e:
                logger.warning("角色 %s 会话清理失败: %s", agent.name, e)
        return True
