"""Step: Outline Update — 预测对比&更新模块

场景级循环的核心模块：
在每个场景的角色行动结束后，对比"原来预测会发生什么" vs "实际发生了什么"，
更新预测状态，为下一个场景的生成提供方向。

关键设计约束：
- 大纲阻断：预测信息不会泄露给角色的决策过程
- 预测是假设，不是剧本：模型知道预测可能被推翻
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

logger = logging.getLogger(__name__)


class OutlineUpdateModule(BaseModule):
    """预测更新：对比实际 vs 预测，更新预测状态
    注意：此模块不作为独立 pipeline 步骤使用，而是由 scene_loop 内部调用
    """

    @property
    def name(self) -> str:
        return "outline_update"

    @property
    def description(self) -> str:
        return "🔄 预测更新（对比实际 vs 预测）"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        raise NotImplementedError(
            "outline_update 是 scene_loop 的内部模块，不独立使用。"
            "请使用 compare_and_update_prediction() 函数。"
        )


# ─── 核心函数（供 scene_loop 调用） ──────────────────────────────


async def compare_and_update_prediction(
    ctx: PipelineContext,
    novel,
    original_prediction: dict[str, Any],
    scene: dict[str, Any],
    scene_actions: list[dict[str, Any]],
    scene_index: int,
    total_scenes_planned: int,
) -> dict[str, Any]:
    """对比预测 vs 实际，更新预测状态

    Args:
        original_prediction: 进入本场景前的预测状态
            （来自 chapter_plan 或上次 outline_update 的输出）
        scene: 本次场景的详细数据（环境、感官）
        scene_actions: 场景中发生的所有角色行动
        scene_index: 当前是第几个场景（0-based）
        total_scenes_planned: 计划本场循环总次数

    Returns:
        更新后的预测字典，包含原始预测字段 +:
        - deviation_report: 偏差描述文本
        - prediction_status: "confirmed" | "partially_deviated" | "fully_deviated"
        - next_scene_hint: 对下一场景的建议（可选）
    """
    client = ctx.get_llm_client("novel_writer")
    if not client:
        return {
            **original_prediction,
            "deviation_report": "（LLM 不可用，维持原预测）",
            "prediction_status": "confirmed",
            "next_scene_hint": "",
        }

    prompt = _build_comparison_prompt(
        novel, original_prediction, scene, scene_actions,
        scene_index, total_scenes_planned,
    )

    system_prompt = (
        f"你是一位小说叙事分析师。你的任务不是写故事，而是对比「预测」和「实际」的差距，"
        f"更新对后续故事的预测。注意：这些预测是内部状态，不会透露给角色。"
        f"只输出 JSON。"
    )

    text, _ = client.chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.7,
    )
    text = text or ""

    update = _parse_update(text, original_prediction)

    logger.info(
        "预测更新 [场景%d/%d]: status=%s",
        scene_index + 1, total_scenes_planned,
        update.get("prediction_status", "?"),
    )

    return update


# ─── Prompt 构建 ──────────────────────────────────────


def _build_comparison_prompt(
    novel,
    prediction: dict[str, Any],
    scene: dict[str, Any],
    scene_actions: list[dict[str, Any]],
    scene_index: int,
    total_scenes_planned: int,
) -> str:
    """构建对比 prompt"""
    # —— 原预测 ——
    orig_key_events = prediction.get("key_events", [])
    orig_summary = prediction.get("summary", "")
    orig_purpose = prediction.get("purpose", "")
    events_text = "\n".join(f"  {i+1}. {ev}" for i, ev in enumerate(orig_key_events)) if orig_key_events else "  （无具体事件预测）"

    # —— 实际场景 ——
    scene_name = scene.get("name", "?")
    scene_desc = scene.get("description", "")
    scene_loc = scene.get("location", "")

    # —— 实际角色行动 ——
    actions_text = ""
    if scene_actions:
        lines = []
        for a in scene_actions:
            c = a.get("character", "?")
            act = a.get("action", "")
            dia = a.get("dialogue", "")
            if dia and dia != "沉默":
                lines.append(f"  {c} {act}，说「{dia[:80]}」")
            else:
                lines.append(f"  {c} {act}")
        actions_text = "\n".join(lines)
    else:
        actions_text = "  （场景中无人行动）"

    # 提取 scene 中的 key_events_done（如果场景骨架有的话）
    scene_events_done = scene.get("key_events_done", [])

    remaining = total_scenes_planned - scene_index - 1

    return f"""你正在为小说《{novel.title}》分析第 {scene_index + 1} 个场景。

{build_novel_context(novel)}

## 你之前的预测（进入此场景前）
概要：{orig_summary}
故事作用：{orig_purpose}
预测的关键事件：
{events_text}

## 实际发生的场景
场景名称：{scene_name}
地点：{scene_loc}
描述：{scene_desc}

### 角色实际行动
{actions_text}

## 你的任务
请对比「预测」和「实际」：
1. 实际发生的事里，哪些在预测之内？
2. 哪些出乎预料？——角色有没有做出你没想到的选择？
3. 基于实际结果，更新对后续故事的预测

    注意：
    - 这是内部预测更新，不会透露给角色
    - 预测是灵活的假设，不是死剧本
    - 还剩 {remaining} 个场景待生成

输出 JSON（只输出 JSON）：
{{
  "key_events": ["修正后的事件列表（保留尚未发生+新增的）"],
  "summary": "更新后的本章概要",
  "deviation_report": "一段文字描述实际 vs 预测的差距（50-100字）",
  "prediction_status": "confirmed 或 partially_deviated 或 fully_deviated",
  "next_scene_hint": "对下一个场景的建议（基于当前情势判断，写具体一些，比如建议下一个场景应该侧重什么、选在哪、谁在场）",
  "purpose": "本章在整体故事中的作用（如有需要可调整）",
  "unresolved_threads": ["未解决的叙事线索列表，每条写一件事需要在未来场景中延续，如'赵无极派人在搜查药铺后院'"]}}
"""


# ─── JSON 解析 ──────────────────────────────────────


def _parse_update(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """从 LLM 输出中解析更新后的预测"""
    import re

    # 先尝试找 JSON
    # ```json ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            result = dict(fallback)  # 保留原预测的字段
            for k in ["key_events", "summary", "deviation_report",
                       "prediction_status", "next_scene_hint", "purpose",
                       "unresolved_threads"]:
                if k in data and data[k]:
                    result[k] = data[k]
            return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 降级
    logger.warning("预测更新 JSON 解析失败，维持原预测")
    return {
        **fallback,
        "deviation_report": "（解析失败）",
        "prediction_status": "confirmed",
        "next_scene_hint": "",
    }
