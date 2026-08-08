"""Step: Narrative Synthesis — 叙事合成（多场景+连续性版）

接收场景序列 + 角色行为 + 上一章结尾，合成为一章完整的叙事。
每章可包含多个场景，从上一章结尾处自然接续。
"""
from __future__ import annotations

import logging
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt, build_novel_context

logger = logging.getLogger(__name__)


class NarrativeModule(BaseModule):
    """⑤ 叙事合成：多场景 + 上一章结尾 → 完整章节"""

    @property
    def name(self) -> str:
        return "narrative"

    @property
    def description(self) -> str:
        return "✍️ 叙事合成（多场景连续）"

    @property
    def modifies_storage(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")

        if not plan:
            raise ValueError("缺少章节规划")

        # ── 数据源：优先 scene_loop，向后兼容旧 pipeline ──
        loop_data = ctx.get_output("scene_loop", {})
        if loop_data.get("scenes"):
            scenes = loop_data.get("scenes", [])
            scene_actions = loop_data.get("scene_actions", {})
            actions = loop_data.get("actions", [])
            prediction_updates = loop_data.get("prediction_updates", [])
        else:
            scenes_data = ctx.get_output("scene_build", {})
            char_actions = ctx.get_output("character_action", {})
            scenes = scenes_data.get("scenes", [])
            actions = char_actions.get("actions", [])
            scene_actions = char_actions.get("scene_actions", {})
            prediction_updates = []

        if not scenes:
            raise ValueError("缺少场景定义")

        client = ctx.get_llm_client("narrative_writer")
        if not client:
            raise RuntimeError("LLM 客户端未配置")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # 获取上一章全文结尾（关键连续性信息）
        prev_chapter_ending = self._get_prev_chapter_ending(novel)
        prev_chapter_content = self._get_prev_chapter_full(novel)
        prev_chapter_title = self._get_prev_chapter_title(novel)

        # ★ 人物群体（含会话历史）
        character_groups = _get_character_groups(novel)

        # ★ 构建世界上下文（历史+地理+历史人物）
        world_context = _build_world_context(novel)

        # 构建上下文字符串
        prompt = self._build_prompt(
            novel, plan, scenes, actions, scene_actions,
            prev_chapter_ending, prev_chapter_content, prev_chapter_title,
            prediction_updates=prediction_updates,
            regeneration_feedback=ctx.regeneration_feedback,
            character_groups=character_groups,
            world_context=world_context,
        )
        system_prompt = self._build_system_prompt(novel)

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7,
        )
        text = text or ""

        text = self._clean_output(text)

        # 保存章节
        from app.novel_studio.models import Chapter
        import re
        raw_title = plan.get("title", f"第{chapter_number}章")
        # 去掉可能重复的 "第N章：" 前缀
        clean_title = re.sub(r'^第[一二三四五六七八九十\d]+章[：:．\.\s]*', '', raw_title).strip()
        if not clean_title:
            clean_title = raw_title
        new_chapter = Chapter(
            number=chapter_number,
            title=clean_title,
            content=text,
            scenes=scenes,  # ★ 持久化场景数据（crowd/感官/参与者）
        )

        try:
            ctx._storage.add_chapter(ctx.novel_id, new_chapter)
            logger.info("第%d章已保存: %s (%d字)", chapter_number, new_chapter.title, len(text))
        except Exception as e:
            logger.error("保存章节失败: %s", e)
            if hasattr(novel, 'chapters') and novel.chapters is not None:
                # 检查同号章节是否已存在，存在则替换（防止重写时重复追加）
                existing_idx = None
                for i, ch in enumerate(novel.chapters):
                    if getattr(ch, 'number', None) == chapter_number:
                        existing_idx = i
                        break
                if existing_idx is not None:
                    novel.chapters[existing_idx] = new_chapter
                    logger.info("第%d章已替换（重写）: %s (%d字)", chapter_number, new_chapter.title, len(text))
                else:
                    novel.chapters.append(new_chapter)
            else:
                novel.chapters = [new_chapter]

        ctx.set_output(self.name, {
            "chapter_number": chapter_number,
            "title": plan.get("title", f"第{chapter_number}章"),
            "content": text,
            "word_count": len(text),
            "scenes_used": [s.get("name", "") for s in scenes],
        })
        return ctx

    def _get_prev_chapter_ending(self, novel) -> str:
        """获取上一章结尾1500字（关键：用于连续性接续）"""
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            return "（这是第一章，尚无前文）"
        prev = chapters[-1]
        content = getattr(prev, "content", "") or ""
        if not content:
            return "（上一章无内容）"
        ending = content[-1500:] if len(content) > 1500 else content
        return ending

    def _get_prev_chapter_full(self, novel) -> str:
        """获取上一章全文（作为风格参考）"""
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            return ""
        prev = chapters[-1]
        content = getattr(prev, "content", "") or ""
        if len(content) > 2000:
            return content[:1000] + "\n...（中间省略）...\n" + content[-500:]
        return content

    def _get_prev_chapter_title(self, novel) -> str:
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            return ""
        prev = chapters[-1]
        return getattr(prev, "title", "") or ""

    def _build_system_prompt(self, novel) -> str:
        template = load_prompt("narrative", "system_writer.md")
        custom = getattr(novel, "custom_prompt", "") or ""
        return template.format(novel_title=novel.title, custom_prompt=custom)

    def _build_prompt(
        self,
        novel,
        plan: dict,
        scenes: list[dict],
        actions: list[dict],
        scene_actions: dict,
        prev_chapter_ending: str,
        prev_chapter_content: str,
        prev_chapter_title: str,
        prediction_updates: list[dict] | None = None,
        regeneration_feedback: str | None = None,
        character_groups: list[dict] | None = None,
        world_context: str = "",
    ) -> str:
        chapter_number = plan.get("chapter_number", "?")
        chapter_title = plan.get("title", f"第{chapter_number}章")

        lines = [f"请创作第{chapter_number}章「{chapter_title}」。"]

        # ─── 第一章：开篇场景（必须在最前面，优先于场景序列） ───
        is_first_chapter = chapter_number == 1
        if is_first_chapter:
            prologue_template = load_prompt("narrative", "prologue.md")
            protagonist = getattr(novel, 'protagonist', None) or {}
            if hasattr(protagonist, 'to_dict'):
                protagonist = protagonist.to_dict()
            custom = (novel.custom_prompt or '')
            prologue_section = prologue_template.format(
                genre=novel.genre or '未知',
                novel_title=novel.title,
                prot_name=protagonist.get('name', '主角'),
                prot_personality=protagonist.get('personality', ''),
                prot_background=protagonist.get('background', ''),
                prologue_scene_rules=custom,
                prologue_rules_section=custom,
            )
            lines.append(f"\n## ⚠️ 第一章硬性要求：必须先写开篇场景\n{prologue_section}")
            lines.append("\n【关键】你必须先从主角的开篇场景开始写（400-600字），让读者充分认识主角是谁、有什么遗憾、是什么样的人。然后再过渡到下面的场景序列。不要跳过开篇场景直接写正文！")

        # ─── 小说核心设定 ───
        novel_ctx = build_novel_context(novel)
        if novel_ctx:
            lines.append(novel_ctx)

        # ─── 世界背景 ───
        if world_context:
            lines.append(f"\n## 世界背景（历史+地理+时代人物）\n{world_context}")

        # ─── 人物群体（含会话历史） ───
        if character_groups:
            lines.append(f"\n## 人物群体")
            for g in character_groups:
                lines.append(f"\n### {g.get('name', '?')}")
                if g.get('description'):
                    lines.append(f"概述：{g['description']}")
                if g.get('dynamics'):
                    lines.append(f"内部关系：{g['dynamics']}")
                if g.get('member_profiles'):
                    lines.append("成员简介：")
                    for mname, mdesc in g['member_profiles'].items():
                        lines.append(f"  - {mname}：{mdesc}")
                if g.get('conversation_history'):
                    lines.append("会话历史：")
                    for h in g['conversation_history']:
                        speaker = h.get('speaker', '?')
                        content = h.get('content', '')
                        action = h.get('action', '')
                        entry = f"  {speaker}：{content}"
                        if action:
                            entry += f"（{action}）"
                        lines.append(entry)

        # ─── 上一章结尾（最关键：从哪里开始写） ───
        if not is_first_chapter and prev_chapter_ending and "第一章" not in prev_chapter_ending:
            lines.append(f"\n## ⚠️ 上一章结尾（本章必须从这里直接开始写）")
            lines.append(f"上一章《{prev_chapter_title}》结尾处：")
            lines.append(f"{prev_chapter_ending}")
            lines.append(f"\n【重要】本章开头必须从上一章结尾处自然接续，不能有时间跳跃，不能重新介绍人物！")
            lines.append(f"上一章结束时主角在哪里、在做什么，本章就从那里继续写。")

        # ─── 上一章全文参考 ───
        if prev_chapter_content and "第一章" not in prev_chapter_content:
            lines.append(f"\n## 上一章全文参考（保持风格一致）")
            lines.append(prev_chapter_content)

        # ─── 本章规划 ───
        lines.append(f"\n## 本章概要")
        lines.append(plan.get("summary", "") or "")
        if plan.get("purpose"):
            lines.append(f"故事作用：{plan['purpose']}")

        if plan.get("key_events"):
            lines.append(f"关键事件：")
            for ev in plan["key_events"]:
                lines.append(f"  • {ev}")

        # ─── 预测更新历程（scene_loop 模式的上下文） ───
        if prediction_updates:
            lines.append(f"\n## 场景演化历程（预测 vs 实际）")
            for pu in prediction_updates:
                si = pu.get("scene_index", 0) + 1
                before = pu.get("before", {})
                after = pu.get("after", {})
                before_events = before.get("key_events", [])
                after_events = after.get("key_events", [])
                status = after.get("prediction_status", "")
                deviation = after.get("deviation_report", "")

                lines.append(f"场景{si}后：")
                if deviation:
                    lines.append(f"  偏差：{deviation}")
                if status:
                    lines.append(f"  状态：{status}")
                if before_events or after_events:
                    if before_events != after_events:
                        lines.append(f"  预测已更新：{after_events}")
        else:
            # 旧模式没有 prediction_updates，但 key_events 仍然可用
            pass

        # ─── 场景序列 ───
        scene_label = "正文场景序列" if is_first_chapter else "场景序列"
        lines.append(f"\n## {scene_label}（本章将有 {len(scenes)} 个场景）")
        for i, scene in enumerate(scenes):
            participants = scene.get("characters", [])
            lines.append(f"\n### 场景{i+1}：{scene.get('name', '')}")
            lines.append(f"  地点：{scene.get('location', '')}")
            lines.append(f"  时间：{scene.get('time', '')}")
            lines.append(f"  参与者：{'、'.join(participants)}")
            p_details = scene.get("participant_details", {})
            if p_details:
                for pname, pinfo in p_details.items():
                    lines.append(f"    {pname}：{pinfo.get('archetype','')} | {pinfo.get('background','')[:80]} | 说话风格：{pinfo.get('speech_style','')}")
            if scene.get("atmosphere"):
                lines.append(f"  氛围：{scene['atmosphere']}")
            if scene.get("weather"):
                lines.append(f"  天气：{scene['weather']}")
            if scene.get("description"):
                lines.append(f"  描述：{scene['description']}")
            if scene.get("crowd"):
                lines.append(f"  ⚠️ 背景人群：{scene['crowd']}")
            if scene.get("transition_from_prev"):
                lines.append(f"  过渡：{scene['transition_from_prev']}")

        # ─── 角色行为（按场景分组） ───
        lines.append(f"\n## 角色行为")
        for scene_info in scenes:
            sid = scene_info.get("scene_id", "")
            sname = scene_info.get("name", "?")
            s_actions = scene_actions.get(sid, {}).get("actions", []) if sid else []

            # 如果没有按 scene_id 分组，用全局 actions
            if not s_actions:
                s_actions = [a for a in actions
                             if a.get("scene_id") == sid]

            if not s_actions:
                continue

            lines.append(f"\n### 场景「{sname}」中的行动")
            for action in s_actions:
                char = action.get("character", "?")
                act = action.get("action", "")
                diag = action.get("dialogue", "")
                inner = action.get("inner", "")
                panel = action.get("面板", "")
                lines.append(f"  {char}：")
                if act:
                    lines.append(f"    行动：{act}")
                if diag and diag != "沉默":
                    lines.append(f"    说：「{diag}」")
                if panel:
                    lines.append(f"    面板：\n{panel}")
                if inner:
                    lines.append(f"    内心：{inner}")

        # ─── 重生成反馈（如果前序 step 触发了重生成） ───
        if regeneration_feedback:
            lines.append(f"\n## ⚠️ 重写要求（必须修正以下问题）")
            lines.append(regeneration_feedback)
            lines.append("请根据以上反馈重新创作本章，确保修正所有指出的问题。")

        # ─── 写作要求 ───
        lines.append(f"""
## 写作要求
- 本章包含 {len(scenes)} 个场景，写作时按场景顺序自然过渡
- 场景之间用时间流逝或空间转换自然衔接，不要硬切换
- 第1个场景必须从上一章结尾处直接开始
- 继承前文的语言风格和叙事节奏
- 叙事要有画面感和沉浸感
- 输出完整的章节正文（不含标题和元信息）
- 不要包含「第X章 完」之类的结尾标记

## ⚠️ 背景人群不蒸发（硬性约束）
- 每个场景的「背景人群」是场景的一部分，必须出现在叙事中
- 即使场景焦点在主角身上，背景人群仍然存在——咳嗽声、低语声、排队的嘈杂声
- 当场景发生重大事件（如官兵搜查、冲突爆发）时，背景人群必须有反应：惊慌、躲避、被驱赶、或继续麻木地躺着
- 不能让几十个人凭空消失——他们可以躲、可以跑、可以被忽略，但不能不存在""")

        return "\n".join(lines)

    def _clean_output(self, text: str) -> str:
        import re
        text = re.sub(r"```(?:markdown|text|plain)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()
        # 去掉LLM可能加的章节标题行
        text = re.sub(r"^第[一二三四五六七八九十\d]+章[：:．\.\s].*\n?", "", text)
        # 去掉「第X章 完」之类标记
        text = re.sub(r"\n?（?第[一二三四五六七八九十\d]+章[完|]）?\n?", "", text)
        return text.strip()


# ─── 辅助函数 ───────────────────────────────

def _get_character_groups(novel) -> list[dict]:
    """从 novel 中提取人物群体列表"""
    groups = getattr(novel, "character_groups", None) or []
    result = []
    for g in groups:
        if hasattr(g, "model_dump"):
            result.append(g.model_dump())
        elif isinstance(g, dict):
            result.append(g)
        else:
            result.append({
                "name": getattr(g, "name", "?"),
                "description": getattr(g, "description", ""),
                "dynamics": getattr(g, "dynamics", ""),
                "member_profiles": getattr(g, "member_profiles", {}),
                "conversation_history": _conv_hist_to_dicts(getattr(g, "conversation_history", [])),
            })
    return result


def _conv_hist_to_dicts(history) -> list[dict]:
    """将会话历史条目转为 dict"""
    result = []
    for h in history:
        if hasattr(h, "model_dump"):
            result.append(h.model_dump())
        elif isinstance(h, dict):
            result.append(h)
        else:
            result.append({
                "speaker": getattr(h, "speaker", "?"),
                "content": getattr(h, "content", ""),
                "action": getattr(h, "action", ""),
            })
    return result


def _build_world_context(novel) -> str:
    """构建世界背景文本（历史+地理+历史人物）"""
    world = getattr(novel, "world", None)
    if not world:
        return ""
    parts = []
    history = getattr(world, "history", "") or ""
    geography = getattr(world, "geography", "") or ""
    overview = getattr(world, "overview", "") or ""
    if history:
        parts.append(f"## 世界历史\n{history}")
    if geography:
        parts.append(f"## 地理位置\n{geography}")
    if overview:
        parts.append(f"## 时代背景\n{overview}")
    # 历史人物
    figures = getattr(world, "historical_figures", []) or []
    if figures:
        parts.append("## 时代重要人物")
        for f in figures:
            name = f.get("name", f.name) if hasattr(f, "get") else getattr(f, "name", "?")
            title = f.get("title", "") if hasattr(f, "get") else getattr(f, "title", "")
            desc = f.get("description", "") if hasattr(f, "get") else getattr(f, "description", "")
            loc = f.get("current_location", "") if hasattr(f, "get") else getattr(f, "current_location", "")
            parts.append(f"\n### {name}（{title}）")
            parts.append(f"位置：{loc}")
            parts.append(f"简介：{desc}")
    return "\n\n".join(parts)
