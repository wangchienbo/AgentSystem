"""NarrativeEngine — 叙事引擎

不参与世界演化，只做两件事：
1. 观察：记录角色在场景中的互动
2. 抽象：从互动记录中提取有叙事价值的内容，写成章节
"""
from __future__ import annotations

import logging
from typing import Any

from app.novel_studio.models import (
    Novel, Chapter, Character, Memory, ChapterOutline,
)

logger = logging.getLogger(__name__)


class ObservationRecord:
    """一次观察记录——角色互动的原始日志"""
    def __init__(self, tick: int, char_name: str, action: str, scene_id: str = ""):
        self.tick = tick
        self.char_name = char_name
        self.action = action
        self.scene_id = scene_id


class NarrativeEngine:
    """叙事引擎——观察者视角"""

    def __init__(self):
        self._observations: list[ObservationRecord] = []

    def observe(self, record: ObservationRecord) -> None:
        """记录一次观察"""
        self._observations.append(record)

    def observe_action(self, tick: int, char_name: str, action: str, scene_id: str = "") -> None:
        """快捷记录角色行动"""
        self.observe(ObservationRecord(tick, char_name, action, scene_id))

    def get_recent_observations(self, limit: int = 20) -> list[ObservationRecord]:
        """获取最近的观察记录"""
        return self._observations[-limit:]

    def generate_chapter(
        self,
        novel: Novel,
        observations: list[ObservationRecord],
        model_router=None,
    ) -> Chapter | None:
        """从观察记录生成章节

        不做 LLM 调用——只负责从互动记录中抽象结构化大纲，
        实际写作交给 worker 或外部。
        """
        if not observations:
            return None

        # 从观察中提取章节骨架
        scene_transitions = []
        char_actions: dict[str, list[str]] = {}
        for obs in observations:
            if obs.char_name not in char_actions:
                char_actions[obs.char_name] = []
            char_actions[obs.char_name].append(obs.action)
            if obs.scene_id and (not scene_transitions or scene_transitions[-1] != obs.scene_id):
                scene_transitions.append(obs.scene_id)

        ch_num = len(novel.chapters) + 1
        summary_parts = []
        for char_name, actions in char_actions.items():
            summary_parts.append(f"{char_name}：{'；'.join(actions[-3:])}")

        outline = ChapterOutline(
            number=ch_num,
            title=f"第{ch_num}章",
            summary=" | ".join(summary_parts),
            characters_involved=list(char_actions.keys()),
            settings=scene_transitions,
        )

        chapter = Chapter(
            number=ch_num,
            title=outline.title,
            word_count=0,
            status="outline",
        )

        return chapter

    def summarize_interactions(
        self,
        observations: list[ObservationRecord],
    ) -> str:
        """将观察记录转为叙事摘要"""
        if not observations:
            return "没有发生值得记录的事。"

        groups: dict[str, list[str]] = {}
        for obs in observations:
            groups.setdefault(obs.char_name, []).append(obs.action)

        lines = []
        for char_name, actions in groups.items():
            actions_str = "，".join(actions[-5:])
            lines.append(f"{char_name}：{actions_str}")

        return "\n".join(lines)

    def clear_observations(self, keep_last: int = 0) -> None:
        """清理观察记录"""
        if keep_last > 0:
            self._observations = self._observations[-keep_last:]
        else:
            self._observations = []

    def to_serializable(self) -> dict:
        return {
            "observations": [
                {"tick": o.tick, "char_name": o.char_name, "action": o.action, "scene_id": o.scene_id}
                for o in self._observations
            ],
        }

    @classmethod
    def from_serializable(cls, data: dict) -> "NarrativeEngine":
        ne = cls()
        for o_data in data.get("observations", []):
            ne._observations.append(ObservationRecord(
                tick=o_data["tick"],
                char_name=o_data["char_name"],
                action=o_data["action"],
                scene_id=o_data.get("scene_id", ""),
            ))
        return ne
