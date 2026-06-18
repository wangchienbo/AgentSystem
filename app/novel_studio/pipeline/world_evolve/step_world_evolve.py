"""Step: World Evolve — 世界演化引擎

每章在 world_check 之后、chapter_plan 之前执行。
职责（全部由 LLM 驱动，零硬编码）：
1. 扫描事件池，判断触发条件是否满足
2. 推进已激活事件的阶段
3. 生成涟漪事件（NPC 反应、传闻扩散）
4. 更新势力关系、区域威胁
5. 归档完成的事件到历史
6. 更新角色世界观
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt

logger = logging.getLogger(__name__)

WORLD_EVOLVE_SYSTEM = load_prompt("world_evolve", "world_evolve.md")


class WorldEvolveModule(BaseModule):
    """世界演化引擎 — 每章推进世界状态（全 LLM 驱动）"""

    @property
    def name(self) -> str:
        return "world_evolve"

    @property
    def description(self) -> str:
        return "🌊 世界演化"

    @property
    def modifies_storage(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            logger.warning("世界演化跳过：无小说数据")
            return ctx

        world = getattr(novel, "world", None)
        if not world:
            logger.warning("世界演化跳过：无世界设定")
            return ctx

        chapter_number = self._get_chapter_number(ctx, novel)
        logger.info("开始世界演化 — 第%d章", chapter_number)

        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM 不可用，跳过世界演化")
            ctx.set_output(self.name, {})
            return ctx

        # 一次 LLM 调用完成全部：触发判断 + 阶段推进 + 涟漪 + 状态更新
        result = await self._llm_evolve(client, world, novel, chapter_number)

        # 应用结果到数据
        self._apply_evolve(world, novel, result, chapter_number)
        ctx.save_novel()

        triggered = len(result.get("triggered_events", []))
        advanced = len(result.get("advanced_events", []))
        completed = len(result.get("completed_events", []))
        ripples = len(result.get("ripple_events", []))
        logger.info(
            "✅ 世界演化完成：触发%d 推进%d 完成%d 涟漪%d",
            triggered, advanced, completed, ripples,
        )

        ctx.set_output(self.name, result)
        return ctx

    # ─── LLM 调用（一次完成全部） ─────────────────────────────

    async def _llm_evolve(self, client, world, novel, chapter_number: int) -> dict:
        """LLM 判断触发条件 + 推进阶段 + 生成涟漪"""
        world_text = self._build_world_text(world, chapter_number)
        last_chapter_text = self._build_last_chapter_text(novel)
        custom_prompt = getattr(novel, "custom_prompt", "") or ""

        user_prompt = f"""## 世界当前状态

{world_text}

## 上一章角色行动摘要

{last_chapter_text}

## 作者意图

{custom_prompt if custom_prompt else '（未定义）'}

请逐项完成：
1. 检查事件池中 pending 事件的触发条件是否满足（基于当前章节数、势力关系紧张度、区域威胁等级等）
2. 推进 active 事件的阶段（remaining_chapters 归零则进入下一阶段）
3. 生成涟漪事件
4. 更新势力关系和区域威胁
5. 更新角色世界观"""

        try:
            text, _ = client.chat(
                [
                    {"role": "system", "content": WORLD_EVOLVE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=3000,
                temperature=0.3,
            )
            return self._parse_response(text or "")
        except Exception as e:
            logger.error("世界演化 LLM 调用失败: %s", e)
            return {}

    def _parse_response(self, text: str) -> dict:
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
            logger.warning("无法解析世界演化结果: %s", text[:200])
            return {}

    # ─── 输入构建 ────────────────────────────────────────────

    def _get_chapter_number(self, ctx: PipelineContext, novel) -> int:
        chapters = getattr(novel, "chapters", None) or []
        return len(chapters) + 1

    def _build_world_text(self, world, chapter_number: int) -> str:
        """构建世界状态文本（含事件池完整信息供 LLM 判断触发条件）"""
        parts = [f"【当前章节】第{chapter_number}章"]

        # 事件池（含触发条件，LLM 自行判断）
        pending = getattr(world, "pending_events", []) or []
        if pending:
            parts.append("\n【事件池】")
            for pe in pending:
                stages_desc = " → ".join(
                    f"{s.name}({s.duration_chapters}章)"
                    for s in pe.stages
                )
                parts.append(
                    f"  [{pe.status}] {pe.name} (类型:{pe.type})\n"
                    f"    触发条件: {pe.trigger_condition}\n"
                    f"    阶段链: {stages_desc}\n"
                    f"    当前阶段: {pe.current_stage}/{len(pe.stages)} 剩余: {pe.remaining_chapters}章\n"
                    f"    涉及势力: {', '.join(pe.factions_involved) if pe.factions_involved else '无'}\n"
                    f"    影响区域: {', '.join(pe.regions_affected) if pe.regions_affected else '无'}\n"
                    f"    内部设定: {pe.internal_setting[:120] if pe.internal_setting else '无'}"
                )

        # 势力关系
        state = getattr(world, "state", None)
        if state:
            relations = getattr(state, "faction_relations", []) or []
            if relations:
                parts.append("\n【势力关系】")
                for r in relations:
                    parts.append(f"  {r.faction_a} ↔ {r.faction_b}: {r.status} (紧张度:{r.tension})")

            threats = getattr(state, "regional_threats", []) or []
            if threats:
                parts.append("\n【区域威胁】")
                for t in threats:
                    parts.append(f"  {t.region}: 等级{t.level} 来源:{t.source} 趋势:{t.trend}")

        # 结构化历史（最近）
        history_eras = getattr(world, "history_eras", []) or []
        if history_eras:
            parts.append("\n【历史背景】")
            for era in history_eras[-2:]:
                parts.append(f"  [{era.era}]")
                for e in era.events[-3:]:
                    parts.append(f"    {e.name} ({e.year}): {e.description[:80]}")

        return "\n".join(parts)

    def _build_last_chapter_text(self, novel) -> str:
        chapters = getattr(novel, "chapters", None) or []
        if not chapters:
            return "（故事尚未开始）"

        last = chapters[-1]
        title = getattr(last, "title", "") if hasattr(last, "title") else last.get("title", "")
        content = getattr(last, "content", "") if hasattr(last, "content") else last.get("content", "")
        summary = content[:500] + "..." if len(content) > 500 else content
        return f"第{len(chapters)}章「{title}」\n{summary}"

    # ─── 数据写回 ────────────────────────────────────────────

    def _apply_evolve(self, world, novel, result: dict, chapter_number: int) -> None:
        """将 LLM 演化结果写回 WorldSetting 和角色"""
        from app.novel_studio.models import (
            WorldHistoryEvent, WorldHistoryEra,
            FactionRelation, RegionalThreat,
            ChapterTimeline, ChapterTimelineEvent,
        )

        # ── 1. 应用触发事件：更新 pending_events 状态 ──
        triggered_names = {te.get("event_name", "") for te in result.get("triggered_events", [])}
        advanced_names = {ae.get("event_name", "") for ae in result.get("advanced_events", [])}
        completed_names = {ce.get("event_name", "") for ce in result.get("completed_events", [])}

        for pe in world.pending_events:
            if pe.name in triggered_names:
                pe.status = "active"
                pe.current_stage = 0
                pe.activated_chapter = chapter_number
                if pe.stages:
                    pe.remaining_chapters = pe.stages[0].duration_chapters
            elif pe.name in advanced_names:
                pe.current_stage += 1
                if pe.current_stage < len(pe.stages):
                    pe.remaining_chapters = pe.stages[pe.current_stage].duration_chapters
                else:
                    pe.status = "completed"
            elif pe.name in completed_names:
                pe.status = "completed"

        # ── 2. 归档完成的事件到历史 ──
        for ce in result.get("completed_events", []):
            archive = ce.get("archive_to_history", {})
            if archive:
                hist_event = WorldHistoryEvent(**archive)
                contemporary = None
                for era in world.history_eras:
                    if era.era == "当代":
                        contemporary = era
                        break
                if contemporary is None:
                    contemporary = WorldHistoryEra(era="当代", events=[])
                    world.history_eras.append(contemporary)
                contemporary.events.append(hist_event)

        # ── 3. 章节事件时间线 ──
        timeline_events = []

        for te in result.get("triggered_events", []):
            timeline_events.append(ChapterTimelineEvent(
                name=te.get("event_name", ""),
                type="触发",
                description=f"事件「{te.get('event_name', '')}」触发，进入阶段「{te.get('stage_name', '')}」",
                distance_to_protagonist="L3",
            ))

        for ae in result.get("advanced_events", []):
            timeline_events.append(ChapterTimelineEvent(
                name=ae.get("event_name", ""),
                type="推进",
                description=f"事件「{ae.get('event_name', '')}」从「{ae.get('from_stage', '')}」推进到「{ae.get('to_stage', '')}」",
                distance_to_protagonist="L3",
            ))

        for re in result.get("ripple_events", []):
            timeline_events.append(ChapterTimelineEvent(
                name=re.get("name", ""),
                type=re.get("type", "涟漪"),
                description=re.get("description", ""),
                affected=re.get("affected", []),
                distance_to_protagonist=re.get("distance_to_protagonist", "L3"),
            ))

        if timeline_events:
            world.chapter_timeline.append(ChapterTimeline(
                chapter=chapter_number,
                events=timeline_events,
            ))

        # ── 4. 更新世界状态 ──
        state_updates = result.get("state_updates", {})
        if state_updates:
            new_relations = state_updates.get("faction_relations", [])
            if new_relations:
                world.state.faction_relations = [
                    FactionRelation(**r) for r in new_relations
                ]
            new_threats = state_updates.get("regional_threats", [])
            if new_threats:
                world.state.regional_threats = [
                    RegionalThreat(**t) for t in new_threats
                ]

        world.state.current_chapter = chapter_number

        # ── 5. 更新角色世界观 ──
        worldview_updates = result.get("worldview_updates", {})
        if worldview_updates:
            chars = getattr(novel, "characters", None) or {}
            for char_name, updates in worldview_updates.items():
                target = None
                for cid, c in (chars.items() if isinstance(chars, dict) else {}):
                    name = getattr(c, "name", "") if hasattr(c, "name") else c.get("name", "")
                    if name == char_name:
                        target = c
                        break
                if target is None:
                    continue

                wv = getattr(target, "worldview", None)
                if wv is None:
                    continue

                for fact in updates.get("add_known_facts", []):
                    if fact not in wv.known_facts:
                        wv.known_facts.append(fact)
                for belief in updates.get("add_beliefs", []):
                    if belief not in wv.beliefs:
                        wv.beliefs.append(belief)
                for old_belief in updates.get("correct_beliefs", []):
                    if old_belief in wv.beliefs:
                        wv.beliefs.remove(old_belief)

                wv.last_updated_chapter = chapter_number
