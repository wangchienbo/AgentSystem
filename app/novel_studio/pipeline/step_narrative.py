"""Step: Narrative Synthesis — 叙事合成（多场景+连续性版）

接收场景序列 + 角色行为 + 上一章结尾，合成为一章完整的叙事。
每章可包含多个场景，从上一章结尾处自然接续。
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

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

        client = ctx.get_llm_client("novel_writer")
        if not client:
            raise RuntimeError("LLM 客户端未配置")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # 获取上一章全文结尾（关键连续性信息）
        prev_chapter_ending = self._get_prev_chapter_ending(novel)
        prev_chapter_content = self._get_prev_chapter_full(novel)
        prev_chapter_title = self._get_prev_chapter_title(novel)

        # 构建上下文字符串
        prompt = self._build_prompt(
            novel, plan, scenes, actions, scene_actions,
            prev_chapter_ending, prev_chapter_content, prev_chapter_title,
            prediction_updates=prediction_updates,
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
        new_chapter = Chapter(
            number=chapter_number,
            title=plan.get("title", f"第{chapter_number}章"),
            content=text,
        )

        try:
            ctx._storage.add_chapter(ctx.novel_id, new_chapter)
            logger.info("第%d章已保存: %s (%d字)", chapter_number, new_chapter.title, len(text))
        except Exception as e:
            logger.error("保存章节失败: %s", e)
            if hasattr(novel, 'chapters') and novel.chapters is not None:
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
        return (
            f"你是一位中国古典小说作家，正在创作小说《{novel.title}》。\n\n"
            f"写作要求：\n"
            f"1. 只输出纯小说正文，不包含任何推理、分析笔记、逻辑校验等元内容\n"
            f"2. 使用第三人称有限视角，不要写出「角色感到」「角色看到」这样的说明\n"
            f"3. 角色的对话使用中文引号「」\n"
            f"4. 叙事要有画面感和沉浸感\n"
            f"5. 使用中文写作，采用明清白话小说风格\n"
            f"6. 常识合理性：每个角色行为的动机和结果都必须合理\n"
            f"7. 因果逻辑：角色做A事，必须有合理的原因导致B结果\n"
            f"8. 社会合理性：考虑故事时代背景下的社会规则\n"
            f"9. 动机关联：每个情节转折必须由角色动机驱动\n"
        )

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
    ) -> str:
        chapter_number = plan.get("chapter_number", "?")
        chapter_title = plan.get("title", f"第{chapter_number}章")

        lines = [f"请创作第{chapter_number}章「{chapter_title}」。"]

        # ─── 小说核心设定 ───
        novel_ctx = build_novel_context(novel)
        if novel_ctx:
            lines.append(novel_ctx)

        # ─── 上一章结尾（最关键：从哪里开始写） ───
        if prev_chapter_ending and "第一章" not in prev_chapter_ending:
            lines.append(f"\n## ⚠️ 上一章结尾（本章必须从这里直接开始写）")
            lines.append(f"上一章《{prev_chapter_title}》结尾处：")
            lines.append(f"{prev_chapter_ending}")
            lines.append(f"\n【重要】本章开头必须从上一章结尾处自然接续，不能有时间跳跃，不能重新介绍人物！")
            lines.append(f"上一章结束时主角在哪里、在做什么，本章就从那里继续写。")
        else:
            lines.append(f"\n## 本章是第一章，从主角穿越到明末开始写。")

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
        lines.append(f"\n## 场景序列（本章将有 {len(scenes)} 个场景）")
        for i, scene in enumerate(scenes):
            participants = scene.get("participants", [])
            lines.append(f"\n### 场景{i+1}：{scene.get('name', '')}")
            lines.append(f"  地点：{scene.get('location', '')}")
            lines.append(f"  时间：{scene.get('time_period', '')}")
            lines.append(f"  参与者：{'、'.join(participants)}")
            if scene.get("atmosphere"):
                lines.append(f"  氛围：{scene['atmosphere']}")
            if scene.get("weather"):
                lines.append(f"  天气：{scene['weather']}")
            if scene.get("description"):
                lines.append(f"  描述：{scene['description']}")
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
                lines.append(f"  {char}：")
                if act:
                    lines.append(f"    行动：{act}")
                if diag and diag != "沉默":
                    lines.append(f"    说：「{diag}」")
                if inner:
                    lines.append(f"    内心：{inner}")

        # ─── 写作要求 ───
        lines.append(f"""
## 写作要求
- 本章包含 {len(scenes)} 个场景，写作时按场景顺序自然过渡
- 场景之间用时间流逝或空间转换自然衔接，不要硬切换
- 第1个场景必须从上一章结尾处直接开始
- 继承前文的语言风格和叙事节奏
- 叙事要有画面感和沉浸感
- 输出完整的章节正文（不含标题和元信息）
- 不要包含「第X章 完」之类的结尾标记""")

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
