"""Step: World Design — 世界观事件池 + 历史背景设计

在 world_check 之前执行（仅首次，或用户手动触发）。
LLM 驱动：基于已有世界观设定，设计事件池、结构化历史、初始世界状态。

与 world_evolve 的区别：
- world_design：一次性设计，创建事件池和历史
- world_evolve：每章运行，触发事件 + 推进 + 涟漪 + 归档
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt

logger = logging.getLogger(__name__)

WORLD_DESIGN_SYSTEM = load_prompt("world_design", "world_design.md")


class WorldDesignModule(BaseModule):
    """世界观设计 — 事件池 + 历史 + 初始状态"""

    @property
    def name(self) -> str:
        return "world_design"

    @property
    def description(self) -> str:
        return "🎨 世界观事件池设计"

    @property
    def modifies_storage(self) -> bool:
        return True  # 写入 pending_events / history_eras / state

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            logger.warning("世界观设计跳过：无小说数据")
            return ctx

        world = getattr(novel, "world", None)
        if not world:
            logger.warning("世界观设计跳过：无世界设定")
            return ctx

        # 检查是否已有事件池（避免重复设计）
        existing = getattr(world, "pending_events", None) or []
        if existing:
            logger.info("事件池已存在（%d 个事件），跳过 world_design", len(existing))
            ctx.set_output(self.name, {"skipped": True, "reason": "事件池已存在"})
            return ctx

        logger.info("开始世界观事件池设计...")

        # 构建输入
        world_text = self._build_world_text(world)
        custom_prompt = getattr(novel, "custom_prompt", "") or ""

        # LLM 设计
        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM客户端不可用，跳过世界观设计")
            ctx.set_output(self.name, {"skipped": True, "reason": "LLM不可用"})
            return ctx

        result = await self._llm_design(client, world_text, custom_prompt)

        # 写回数据
        if result:
            self._apply_design(world, result)
            ctx.save_novel()
            logger.info(
                "✅ 世界观设计完成：%d 个事件，%d 个历史时代",
                len(result.get("pending_events", [])),
                len(result.get("history_eras", [])),
            )

        ctx.set_output(self.name, result)
        return ctx

    # ─── 输入构建 ────────────────────────────────────────────

    def _build_world_text(self, world) -> str:
        """构建世界设定文本"""
        parts = [f"【世界名称】{getattr(world, 'name', '')}"]

        overview = getattr(world, "overview", "")
        if overview:
            parts.append(f"【概述】{overview}")

        magic = getattr(world, "magic_system", "") or ""
        if magic:
            parts.append(f"【修炼体系】{magic}")

        factions = getattr(world, "factions", None) or []
        if factions:
            parts.append("【势力】")
            for f in factions:
                if isinstance(f, dict):
                    parts.append(f"  - {f.get('name', '?')}: {f.get('description', '')}")
                else:
                    parts.append(f"  - {f}")

        geography = getattr(world, "geography", "") or ""
        if geography:
            parts.append(f"【地理】{geography}")

        culture = getattr(world, "culture", "") or ""
        if culture:
            parts.append(f"【文化】{culture}")

        old_history = getattr(world, "history", "") or ""
        if old_history:
            parts.append(f"【已有历史（旧版）】{old_history}")

        return "\n\n".join(parts)

    # ─── LLM 调用 ────────────────────────────────────────────

    async def _llm_design(self, client, world_text: str, custom_prompt: str) -> dict:
        """LLM 设计事件池和历史"""
        user_prompt = f"""## 世界设定

{world_text}

## 作者意图

{custom_prompt if custom_prompt else '（未定义）'}

请基于以上设定，设计事件池、结构化历史和初始世界状态。"""

        try:
            text, _ = client.chat(
                [
                    {"role": "system", "content": WORLD_DESIGN_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,
                temperature=0.4,
            )
            return self._parse_response(text or "")
        except Exception as e:
            logger.error("世界观设计 LLM 调用失败: %s", e)
            return {}

    def _parse_response(self, text: str) -> dict:
        """解析 LLM 返回的 JSON"""
        text = text.strip()
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("无法解析世界观设计结果: %s", text[:200])
            return {}

    # ─── 数据写回 ────────────────────────────────────────────

    def _apply_design(self, world, result: dict) -> None:
        """将 LLM 设计结果写回 WorldSetting"""
        from app.novel_studio.models import (
            PendingEvent, PendingEventStage,
            WorldHistoryEra, WorldHistoryEvent,
            FactionRelation, RegionalThreat, WorldState,
        )

        # 事件池
        for pe_data in result.get("pending_events", []):
            stages = [
                PendingEventStage(**s)
                for s in pe_data.pop("stages", [])
            ]
            pe = PendingEvent(**pe_data, stages=stages)
            world.pending_events.append(pe)

        # 结构化历史
        for era_data in result.get("history_eras", []):
            events = [
                WorldHistoryEvent(**e)
                for e in era_data.pop("events", [])
            ]
            era = WorldHistoryEra(**era_data, events=events)
            world.history_eras.append(era)

        # 初始世界状态
        state_data = result.get("state", {})
        if state_data:
            relations = [
                FactionRelation(**r)
                for r in state_data.get("faction_relations", [])
            ]
            threats = [
                RegionalThreat(**t)
                for t in state_data.get("regional_threats", [])
            ]
            world.state = WorldState(
                faction_relations=relations,
                regional_threats=threats,
                current_chapter=0,
            )
