"""SceneManager — 场景调度与感知管理

管理谁在哪个场景、谁能感知到什么。
核心功能：信息隔离——角色只能感知到当前场景内的事物。
"""
from __future__ import annotations

import logging
from typing import Any

from app.novel_studio.models import (
    Character, SceneSetting, CharacterPerception,
)

logger = logging.getLogger(__name__)


class SceneManager:
    """场景管理器——维护场景内角色、计算感知"""

    def __init__(self):
        # scene_id → {char_id: Character}
        self._occupants: dict[str, dict[str, Character]] = {}
        # scene_id → SceneSetting
        self._scenes: dict[str, SceneSetting] = {}
        # char_id → scene_id
        self._locations: dict[str, str] = {}
        # 事件日志（跨 pipeline 调用累积）
        self._event_log: list[dict] = []

    def sync_scenes(self, scenes: dict) -> None:
        """从 novel.world.scenes 同步场景定义（不重置）"""
        for sid, scene in scenes.items():
            if sid not in self._scenes:
                if isinstance(scene, dict):
                    # 从 dict 构造 SceneSetting
                    from app.novel_studio.data_models import SceneSetting
                    s = SceneSetting(
                        id=sid,
                        name=scene.get("name", sid),
                        location=scene.get("location", ""),
                        atmosphere=scene.get("atmosphere", ""),
                        description=scene.get("description", ""),
                        weather=scene.get("weather", ""),
                        time_period=scene.get("time_period", ""),
                    )
                    self.add_scene(s)
                else:
                    self.add_scene(scene)

    def clear_events(self):
        """清除事件日志，准备新一轮"""
        self._event_log = []

    def get_event_log(self) -> list[dict]:
        """获取当前场景事件日志"""
        return list(self._event_log)

    def apply_action(self, char_name: str, action: str, dialogue: str = "",
                     inner: str = "", scene_id: str = "") -> None:
        """记录角色行动到场景事件日志"""
        event = {
            "char_name": char_name,
            "action": action,
            "dialogue": dialogue,
            "inner": inner,
            "scene_id": scene_id or "",
        }
        self._event_log.append(event)

    def get_event_summary(self, max_events: int = 5) -> str:
        """获取最近的场景事件摘要"""
        if not self._event_log:
            return "之前没有任何事件发生。"
        events = self._event_log[-max_events:]
        lines = ["【之前发生的事件】"]
        for ev in events:
            parts = [f"  {ev['char_name']}{ev['action']}"]
            if ev['dialogue'] and ev['dialogue'] != "沉默":
                parts.append(f"，说「{ev['dialogue'][:80]}」")
            if ev['inner']:
                parts.append(f"（内心：{ev['inner'][:40]}）")
            lines.append("".join(parts))
        return "\n".join(lines)

    def get_scene(self, scene_id: str) -> SceneSetting | None:
        """获取场景定义"""
        return self._scenes.get(scene_id)

    def add_scene(self, scene: SceneSetting) -> None:
        """注册场景"""
        self._scenes[scene.id] = scene
        if scene.id not in self._occupants:
            self._occupants[scene.id] = {}
        logger.debug("场景注册: %s (%s)", scene.name, scene.id)

    def place_character(self, char: Character, scene_id: str) -> None:
        """将角色放入场景"""
        # 从旧场景移除
        old_scene = self._locations.get(char.id)
        if old_scene and old_scene in self._occupants:
            self._occupants[old_scene].pop(char.id, None)

        # 加入新场景
        if scene_id not in self._occupants:
            self._occupants[scene_id] = {}
        self._occupants[scene_id][char.id] = char
        self._locations[char.id] = scene_id

        # 更新角色数据
        char.current_scene = scene_id
        logger.debug("角色入场景: %s → %s", char.name, 
                     self._scenes.get(scene_id, SceneSetting(name="?")).name)

    def get_scene_for_char(self, char_id: str) -> str | None:
        """获取角色当前所在场景ID"""
        return self._locations.get(char_id)

    def get_occupants(self, scene_id: str) -> list[Character]:
        """获取场景内所有角色"""
        occ = self._occupants.get(scene_id, {})
        return list(occ.values())

    def get_visible_chars(self, char_id: str) -> list[Character]:
        """角色在当前场景能看到哪些其他角色"""
        scene_id = self._locations.get(char_id)
        if not scene_id:
            return []
        return [
            c for cid, c in self._occupants.get(scene_id, {}).items()
            if cid != char_id
        ]

    def get_perception(self, char_id: str) -> CharacterPerception:
        """计算角色在当前场景的感知"""
        scene_id = self._locations.get(char_id)
        if not scene_id:
            return CharacterPerception(
                scene_description="角色不在任何场景中。"
            )

        scene = self._scenes.get(scene_id)
        visible = self.get_visible_chars(char_id)

        if not scene:
            return CharacterPerception(
                visible_chars=[c.name for c in visible],
                scene_description="未知场景",
            )

        return CharacterPerception(
            visible_chars=[c.name for c in visible],
            scene_description=scene.description or scene.name,
            sounds=scene.sounds.copy(),
            smells=scene.smells.copy(),
            mood=scene.mood,
        )

    def get_scene_summary(self, scene_id: str) -> str:
        """场景摘要（给叙事引擎用）"""
        scene = self._scenes.get(scene_id)
        if not scene:
            return "未知场景"
        chars = self.get_occupants(scene_id)
        char_names = ", ".join(c.name for c in chars) if chars else "空无一人"
        parts = [
            f"地点：{scene.name}",
            f"人物：{char_names}",
        ]
        if scene.atmosphere:
            parts.append(f"氛围：{scene.atmosphere}")
        return " | ".join(parts)

    def remove_character(self, char_id: str) -> None:
        """将角色从场景移除"""
        scene_id = self._locations.pop(char_id, None)
        if scene_id and scene_id in self._occupants:
            self._occupants[scene_id].pop(char_id, None)

    def list_scenes(self) -> list[dict[str, Any]]:
        """列出所有场景及其角色"""
        result = []
        for sid, scene in self._scenes.items():
            occupants = self.get_occupants(sid)
            result.append({
                "id": sid,
                "name": scene.name,
                "occupants": [c.name for c in occupants],
                "occupant_count": len(occupants),
            })
        return result
