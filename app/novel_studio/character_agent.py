"""Novel Studio — 角色 Agent（演化版）

每个角色 = 一个 Agent，拥有：
- 独立记忆系统
- 场景感知（不在同一场景就不知道）
- 知识过滤（没渠道知道的事不提及）
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

logger = logging.getLogger(__name__)


class CharacterAgent:
    """角色 Agent——代表一个角色的行为、记忆和知识边界"""

    def __init__(
        self,
        character: Character,
        model_router: ModelRouter | None = None,
    ):
        self._char = character
        self._router = model_router
        # 角色记忆（角色自己的视角）
        self._memories: list[Memory] = []
        self._max_memories = 50

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
        """添加一条记忆（角色视角）"""
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

    # ── Agent 决策 ──

    def build_character_sheet_prompt(self) -> str:
        """角色面板描述——注入决策 prompt 头部"""
        return self._char.sheet_block()

    def build_decision_prompt(
        self,
        perception: CharacterPerception,
        scene_context: str,
    ) -> str:
        """构造角色决策 prompt（只包含角色知道的信息）"""
        parts = [f"你扮演的角色是{self._char.name}。"]
        
        # 角色面板
        parts.append(f"\n{self._char.sheet_block()}")

        # 关系（只提在场角色之间的关系）
        visible_names = perception.visible_chars
        if visible_names:
            rels = []
            for vn in visible_names:
                if vn in self._char.relationships:
                    rels.append(f"{vn}（{self._char.relationships[vn]}）")
                else:
                    rels.append(vn)
            parts.append(f"\n你身边的人：{'、'.join(rels)}")

        # 场景感知
        parts.append(f"\n当前场景：{scene_context}")
        if perception.scene_description:
            parts.append(f"你看到：{perception.scene_description}")
        if perception.sounds:
            parts.append(f"你听到：{'；'.join(perception.sounds[:3])}")
        if perception.smells:
            parts.append(f"你闻到：{'；'.join(perception.smells[:2])}")
        if perception.mood:
            parts.append(f"氛围：{perception.mood}")

        # 记忆（角色知道的事）
        knowing = self.get_knowing_summary(5)
        parts.append(f"\n{knowing}")

        # 决策指令
        parts.append(f"\n场景中不止你一个人。请以 {self._char.name} 的身份决定：")
        parts.append("1. 你在这个场景中会做什么行动？")
        parts.append("2. 如果你要说话，会说什么？")
        parts.append("\n请用以下格式输出：")
        parts.append("行动：<你想做的动作>")
        parts.append("对话：<你想说的话>（如果没有想说的就写'沉默'）")
        parts.append("内心：<你的内心想法>（可选）")

        return "\n".join(parts)

    def decide_with_world(
        self,
        perception: CharacterPerception,
        scene_context: str,
        world_snapshot: str = "",
    ) -> dict[str, str]:
        """一次调用完成：感知过滤 + 行动决策

        合并 query_perceived_context + decide 为单次 LLM 调用。
        角色基于自身能力从世界快照中提取自己能感知到的部分，再做出决策。
        """
        parts = [f"你扮演的角色是{self._char.name}。\n"]
        parts.append(self._char.sheet_block())

        # 特殊能力提示（穿越者金手指、异能等）
        if self._char.special_ability:
            parts.append(f"\n⚠️ 你的特殊能力：{self._char.special_ability}")
            parts.append("在决策时，这个能力会改变你能感知到的信息和你的思维方式。")

        # 穿越者额外提示
        if "穿越" in self._char.background or "现代" in self._char.background:
            parts.append(f"\n【重要】你不是这个时代的人。你的灵魂来自四百多年后的现代世界。")
            parts.append("你的思维方式、语言习惯、知识结构与周围人完全不同，你必须时刻伪装。")
            parts.append("你拥有现代人的知识储备——历史进程、科学常识、社会运作逻辑——")
            parts.append("但你绝不能直接暴露这些。所有的建议和行动都要包装成合理解释。")
            parts.append("你的特殊能力是你最大的底牌，谨慎使用。")

        # 关系
        visible_names = perception.visible_chars
        if visible_names:
            rels = []
            for vn in visible_names:
                if vn in self._char.relationships:
                    rels.append(f"{vn}（{self._char.relationships[vn]}）")
                else:
                    rels.append(vn)
            parts.append(f"\n你身边的人：{'、'.join(rels)}")

        # 场景
        parts.append(f"\n当前场景：{scene_context}")
        if perception.scene_description:
            parts.append(f"你看到：{perception.scene_description}")
        if perception.sounds:
            parts.append(f"你听到：{'；'.join(perception.sounds[:3])}")
        if perception.smells:
            parts.append(f"你闻到：{'；'.join(perception.smells[:2])}")
        if perception.mood:
            parts.append(f"氛围：{perception.mood}")

        # 记忆
        knowing = self.get_knowing_summary(5)
        parts.append(f"\n{knowing}")

        # 世界快照（给能力过滤用）
        if world_snapshot:
            parts.append(f"\n【当前世界状态】\n{world_snapshot}\n")

        # 单步指令
        parts.append(f"""\n请按以下步骤处理：

第一步 — 信息过滤
基于你的能力（属性/装备/特殊能力/势力/记忆），从【当前世界状态】中找出你实际能知道的信息：
- 同一场景内的全可见
- 感知敏锐（有效感知≥14）→ 能注意更多细节
- 有特殊能力 → 能力会让你看到常人看不到的联系
- 有远程能力/装备 → 可能感知到其他场景
- 同一势力 → 知道势力内情报
- 排除你没渠道知道的信息

第二步 — 做出决策
基于你过滤后知道的信息，以 {self._char.name} 的身份决定。

输出格式：
感知：<你注意到/知道的事>
行动：<你此刻的行动>
对话：<你要说的话，如果没有就写沉默>
内心：<你的内心想法>（可选）""")

        prompt = "\n".join(parts)

        try:
            if self._router:
                client = self._router.get_client("architect", "complex")
                messages = [
                    {"role": "system", "content": f"你正在扮演{self._char.name}。先判断自己知道什么，再行动。不要跳角色。"},
                    {"role": "user", "content": prompt},
                ]
                text, _ = client.chat(
                    messages,
                    max_tokens=600,
                    temperature=0.8,
                    stream=False,
                )
                return self._parse_decision(text or "行动：沉默观望")
            return {"action": "沉默观望", "dialogue": "沉默", "inner": ""}
        except Exception as e:
            logger.warning("角色决策失败 %s: %s", self._char.name, e)
            return {"action": "沉默观望", "dialogue": "沉默", "inner": ""}

    # ── 对话方法（被 engine.character_dialogue 调用） ──

    async def speak(self, context: str, target_audience: str = "") -> str:
        """以角色身份生成一句对话台词"""
        parts = [f"你扮演的角色是{self._char.name}。"]
        parts.append(f"\n{self._char.sheet_block()}")

        if self._char.speech_style:
            parts.append(f"\n说话风格：{self._char.speech_style}")

        if self._memories:
            parts.append(f"\n{self.get_knowing_summary(5)}")

        if target_audience:
            parts.append(f"\n对话对象：{target_audience}")

        parts.append(f"\n当前情境：\n{context}")
        parts.append(f"\n请以{self._char.name}的身份说一句话（仅回复你所说的内容，不要加动作描写以外的说明）：")

        prompt = "\n".join(parts)
        system_prompt = (
            f"你正在扮演{self._char.name}。保持角色性格一致，"
            f"用词和语气符合角色设定。只输出角色台词，不要加注解。"
        )

        try:
            if self._router:
                client = self._router.get_client("architect", "complex")
                messages = [
                    {"role": "system", "content": system_prompt},
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
    """角色 Agent 注册中心"""

    def __init__(self, model_router: ModelRouter | None = None):
        self._agents: dict[str, CharacterAgent] = {}
        self._router = model_router

    def register(self, character: Character) -> CharacterAgent:
        agent = CharacterAgent(character, model_router=self._router)
        self._agents[character.id] = agent
        return agent

    def get(self, char_id: str) -> CharacterAgent | None:
        return self._agents.get(char_id)

    def get_by_name(self, name: str) -> CharacterAgent | None:
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def remove(self, char_id: str) -> None:
        self._agents.pop(char_id, None)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {"id": aid, "name": a.name, "memories": len(a.memories)}
            for aid, a in self._agents.items()
        ]

    def to_serializable(self) -> dict:
        return {
            "agents": {aid: a.to_serializable() for aid, a in self._agents.items()},
        }

    @classmethod
    def from_serializable(cls, data: dict, model_router=None) -> "CharacterAgentRegistry":
        registry = cls(model_router=model_router)
        for aid, a_data in data.get("agents", {}).items():
            agent = CharacterAgent.from_serializable(a_data, model_router=model_router)
            registry._agents[aid] = agent
        return registry

