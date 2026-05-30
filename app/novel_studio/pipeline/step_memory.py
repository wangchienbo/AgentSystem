"""Step: Memory Update — 记忆更新

将本轮生成的角色行为结果保存到每个角色的记忆（_memories）中。
角色 A 只记住自己看到、听到、说过的和想的。
角色 B 不知道角色 A 的内心想法。
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class MemoryUpdateModule(BaseModule):
    """⑥ 记忆更新：角色行为 → Agent 记忆持久化"""

    @property
    def name(self) -> str:
        return "memory_update"

    @property
    def description(self) -> str:
        return "💾 角色记忆更新"

    @property
    def modifies_storage(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        scene = ctx.get_output("scene_build")
        actions = ctx.get_output("character_action", {}).get("actions", [])
        chapter_info = ctx.get_output("narrative", {})

        chapter_number = chapter_info.get("chapter_number",
            ctx.get_output("chapter_plan", {}).get("chapter_number", "?"))

        if not actions:
            logger.warning("没有角色行为需要记忆保存")
            ctx.set_output(self.name, {"memories_saved": 0})
            return ctx

        # 为每个角色构建记忆
        total_saved = 0
        for action in actions:
            char_name = action.get("character", "")
            agent = ctx.get_agent_by_name(char_name)
            if not agent:
                continue

            # 只记住自己能知道的信息
            perception = action.get("感知", "")
            act = action.get("action", "")
            diag = action.get("dialogue", "")
            inner = action.get("inner", "")

            memory_parts = []
            if perception:
                memory_parts.append(f"你注意到：{perception}")
            if act:
                memory_parts.append(f"你做了：{act}")
            if diag and diag != "沉默":
                memory_parts.append(f"你说了：{diag}")

            if memory_parts:
                memory_text = f"[第{chapter_number}章] " + "；".join(memory_parts)
                agent.remember(memory_text)
                total_saved += 1

            # 角色也知道同场景其他角色做了什么（但不包括内心）
            for other in actions:
                if other.get("character") == char_name:
                    continue
                o_action = other.get("action", "")
                o_diag = other.get("dialogue", "")
                o_parts = []
                if o_action:
                    o_parts.append(f"{other['character']}做了：{o_action}")
                if o_diag and o_diag != "沉默":
                    o_parts.append(f"{other['character']}说：{o_diag}")
                if o_parts:
                    others_text = f"[第{chapter_number}章] " + "；".join(o_parts)
                    agent.remember(others_text)
                    total_saved += 1

        # 全局记忆也保存
        self._save_global_memory(ctx, scene, actions, chapter_number)

        logger.info("记忆更新完成: %d 条记忆", total_saved)
        ctx.set_output(self.name, {"memories_saved": total_saved})
        return ctx

    def _save_global_memory(self, ctx, scene, actions, chapter_number):
        """保存全局叙事事件（供世界模块使用）"""
        wm = ctx.world_module
        if not wm:
            return
        try:
            summary = f"第{chapter_number}章在{scene.get('name','?')}发生"
            if actions:
                chars = [a.get("character","") for a in actions if a.get("character")]
                summary += f"，涉及{'、'.join(chars)}"
            if hasattr(wm, 'record_history_event'):
                wm.record_history_event(summary)
        except Exception as e:
            logger.warning("全局记忆记录失败: %s", e)
