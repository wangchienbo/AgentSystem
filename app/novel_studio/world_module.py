"""WorldModule — 世界状态容器

管理世界大事件时间线、地理场景、规则。
角色只能通过感知和社交间接了解世界信息。
"""
from __future__ import annotations

import logging
from typing import Any

from app.novel_studio.models import (
    SceneSetting, WorldEvent, WorldSetting,
)

logger = logging.getLogger(__name__)


class WorldModule:
    """世界模块——管理客观世界状态"""

    def __init__(self, world_setting: WorldSetting | None = None):
        self._setting = world_setting or WorldSetting(name="默认世界")
        # 时间线（世界级大事件，非角色私人事件）
        self._timeline: list[WorldEvent] = []
        # 当前故事时间
        self._current_time: int = 0

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def setting(self) -> WorldSetting:
        return self._setting

    def advance_time(self, steps: int = 1) -> int:
        """推进世界时间"""
        self._current_time += steps
        return self._current_time

    def add_event(self, event: WorldEvent) -> None:
        """添加世界大事件"""
        if not event.timestamp:
            event.timestamp = self._current_time
        self._timeline.append(event)
        self._timeline.sort(key=lambda e: e.timestamp)
        logger.info("世界事件: %s (@t=%d)", event.title, event.timestamp)

    def get_public_events(self, up_to_time: int | None = None) -> list[WorldEvent]:
        """获取公开的大事件列表（角色可查的公共知识）"""
        t = up_to_time if up_to_time is not None else self._current_time
        return [e for e in self._timeline if e.timestamp <= t and e.public_knowledge]

    def get_event_summary(self, up_to_time: int | None = None) -> str:
        """世界大事件摘要（供叙事引擎/角色Agent注入）"""
        events = self.get_public_events(up_to_time)
        if not events:
            return "世界尚未发生值得铭记的大事件。"
        lines = [f"【世界时间线（当前时刻 t={self._current_time}）】"]
        for e in events:
            lines.append(f"  t={e.timestamp} {e.title}：{e.description[:100]}")
        return "\n".join(lines)

    def get_world_context(self) -> str:
        """世界背景摘要"""
        parts = [f"世界背景：{self._setting.overview}"]
        if self._setting.rules:
            parts.append(f"规则：{'；'.join(self._setting.rules[:3])}")
        if self._setting.factions:
            parts.append(f"势力：{', '.join(f.get('name','?') for f in self._setting.factions[:3])}")
        return "\n".join(parts)

    def set_from_novel_world(self, novel_world: WorldSetting) -> None:
        """从 Novel.world 导入世界观设定"""
        self._setting = novel_world

    def to_serializable(self) -> dict:
        return {
            "current_time": self._current_time,
            "setting": self._setting.model_dump(mode="json") if hasattr(self._setting, "model_dump") else {},
            "timeline": [e.model_dump(mode="json") if hasattr(e, "model_dump") else {} for e in self._timeline],
        }

    @classmethod
    def from_serializable(cls, data: dict) -> "WorldModule":
        wm = cls()
        wm._current_time = data.get("current_time", 0)
        if data.get("setting"):
            wm._setting = WorldSetting(**data["setting"])
        for e_data in data.get("timeline", []):
            wm._timeline.append(WorldEvent(**e_data))
        return wm
