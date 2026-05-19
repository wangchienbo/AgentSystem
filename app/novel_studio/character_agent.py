"""Novel Studio — 角色 Agent 基类

每个角色 = 一个 Agent，拥有独立的人格设定，
通过 LLM 调用生成符合角色风格的回复。
"""
from __future__ import annotations

import json
from typing import Any

from app.novel_studio.models import Character, DialogueLine, StorySegment
from app.ai.model_client import OpenAIResponsesClient
from app.ai.model_router import ModelRouter


class CharacterAgent:
    """角色 Agent 基类——代表一个小说角色的人格和行为风格。"""

    def __init__(
        self,
        character: Character,
        model_router: ModelRouter | None = None,
        client: OpenAIResponsesClient | None = None,
    ):
        self._character = character
        self._model_router = model_router
        self._client = client
        self._conversation_history: list[dict[str, str]] = []
        self._max_history = 20

    @property
    def name(self) -> str:
        return self._character.name

    @property
    def character(self) -> Character:
        return self._character

    def get_system_prompt(self) -> str:
        """构建角色系统 prompt"""
        return self._character.personality_prompt()

    def add_to_history(self, role: str, content: str) -> None:
        self._conversation_history.append({"role": role, "content": content})
        if len(self._conversation_history) > self._max_history:
            self._conversation_history = self._conversation_history[-self._max_history:]

    def get_dialogue_context(self) -> list[dict[str, str]]:
        """获取对话上下文（历史 + 角色 prompt）"""
        messages = [{"role": "system", "content": self.get_system_prompt()}]
        messages.extend(self._conversation_history[-self._max_history:])
        return messages

    async def speak(
        self,
        context: str,
        target_audience: str = "",
        emotion_hint: str = "",
    ) -> str:
        """让角色根据当前上下文说话"""
        prompt = context
        if target_audience:
            prompt += f"\n\n当前对话对象：{target_audience}"
        if emotion_hint:
            prompt += f"\n\n情绪提示：{emotion_hint}"

        self.add_to_history("user", prompt)

        # 构建完整对话 prompt（角色 prompt + 历史 + 当前）
        sys_prompt = self.get_system_prompt()
        history_text = ""
        for msg in self._conversation_history[-10:]:
            role = "你" if msg["role"] == "assistant" else "对方"
            history_text += f"\n{role}：{msg['content']}"
        full_prompt = f"{sys_prompt}\n\n---\n对话历史：{history_text}\n\n---\n请以角色的身份回复，不要解释你在扮演：\n{prompt}"

        try:
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": full_prompt},
            ]
            if self._client:
                text, _ = self._client.chat(
                    messages,
                    model=self._client._config.model,
                    max_tokens=1000,
                    temperature=0.85,
                    stream=False,
                )
            elif self._model_router:
                client = self._model_router.get_client("architect", "complex")
                text, _ = client.chat(
                    messages,
                    model=client._config.model,
                    max_tokens=1000,
                    temperature=0.85,
                    stream=False,
                )
            else:
                text = self._fallback_speak(context)
            text = text or f"[{self.name}沉默了片刻]"
        except Exception as e:
            text = f"[{self.name}沉默了片刻…]"

        self.add_to_history("assistant", text)
        return text

    def _extract_text_from_resp(self, resp: dict) -> str:
        """从 responses API 返回中提取文本"""
        if not resp:
            return ""
        output = resp.get("output", [])
        for item in output:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        return c.get("text", "")
        # Fallback: try choices format
        choices = resp.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "")
        return ""

    async def narrate_action(self, action_desc: str) -> str:
        """角色执行动作时的叙述"""
        sys_prompt = self.get_system_prompt()
        prompt = f"{sys_prompt}\n\n请用你的口吻描述以下动作：\n{action_desc}\n\n要求：用第一人称或第三人称，保持角色性格。直接描述，不要解释。"
        try:
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt},
            ]
            if self._client:
                text, _ = self._client.chat(messages, max_tokens=500, temperature=0.8, stream=False)
                return text or f"[{self.name}做出了动作：{action_desc}]"
            return f"[{self.name}做出了动作：{action_desc}]"
        except Exception:
            return f"[{self.name}做出了动作：{action_desc}]"

    def _fallback_speak(self, context: str) -> str:
        """无 LLM 时的 fallback——基于角色设定生成模板回复"""
        personality = self._character.personality or ["普通"]
        traits = "、".join(personality)
        return f"（{self.name}带着{traits}的语气说道）关于你说的，我有我的看法……"


class CharacterAgentRegistry:
    """角色 Agent 注册中心——管理所有角色 Agent"""

    def __init__(self, model_router: ModelRouter | None = None):
        self._agents: dict[str, CharacterAgent] = {}
        self._model_router = model_router

    def register(self, character: Character, client: OpenAIResponsesClient | None = None) -> CharacterAgent:
        agent = CharacterAgent(character, model_router=self._model_router, client=client)
        self._agents[character.id] = agent
        return agent

    def get(self, char_id: str) -> CharacterAgent | None:
        return self._agents.get(char_id)

    def remove(self, char_id: str) -> None:
        self._agents.pop(char_id, None)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {"id": aid, "name": a.name, "archetype": a.character.archetype.value}
            for aid, a in self._agents.items()
        ]

    def get_by_name(self, name: str) -> CharacterAgent | None:
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None
