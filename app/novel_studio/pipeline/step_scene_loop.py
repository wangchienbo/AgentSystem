"""Step: Scene Loop — 场景级循环编排器

这是 Pipeline 改造 Phase 2 的核心模块：
取代原来的 scene_sequence + scene_build + character_action 顺序执行，
改为"预测→环境→角色→重预测"的**场景级循环**：

chapter_plan(预测) →
  loop × N:
    ① predict_scene(基于当前预测 → 一个场景骨架)
    ② build_environment(纯环境/感官细节)
    ③ character_action(角色自由行动)
    ④ outline_update(对比实际 vs 预测 → 更新预测)
  narrative(叙事抽象) →
  memory_update

数据流：
- 输入：chapter_plan 的输出（预测状态）
- 每次迭代：生成一个场景 → 注册到 SceneManager → 角色决策 → 更新预测
- 输出：所有场景 + 所有行动 + 最终预测状态
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseModule, PipelineContext
from .step_scene_sequence import generate_one_scene
from .character_action.step_character_action import run_scene_actions
from .step_outline_update import compare_and_update_prediction

logger = logging.getLogger(__name__)

# 场景循环次数范围
MIN_SCENES = 2
MAX_SCENES = 6


class SceneLoopModule(BaseModule):
    """② 场景级循环：预测→环境→角色→重预测 → 循环 N 轮"""

    @property
    def name(self) -> str:
        return "scene_loop"

    @property
    def description(self) -> str:
        return "🔄 场景级循环（预测→环境→角色→重预测 ×N）"

    @property
    def modifies_storage(self) -> bool:
        return True  # 注册场景到 SceneManager

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        if not novel:
            raise ValueError("小说不存在")

        plan = ctx.get_output("chapter_plan")
        if not plan:
            raise ValueError("缺少章节规划，请先执行 chapter_plan 模块")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # ── 确定场景数量 ──
        num_scenes = _determine_scene_count(novel, plan)
        logger.info(
            "场景循环启动: 第%d章「%s」, %d 个场景",
            chapter_number, plan.get("title", ""), num_scenes,
        )

        # ── 初始预测（来自 chapter_plan） ──
        current_prediction = dict(plan)  # 复制，后续会被更新

        # ── 循环状态 ──
        all_scenes: list[dict[str, Any]] = []
        all_actions: list[dict[str, Any]] = []
        scene_actions_map: dict[str, dict[str, Any]] = {}
        prediction_updates: list[dict[str, Any]] = []
        prev_scene_state: dict[str, Any] | None = None  # 上一场景的 SceneState

        # ── 人物群体（从 novel 读取，循环中更新会话历史） ──
        novel_groups = getattr(novel, "character_groups", None) or []
        scene_groups = _groups_to_dicts(novel_groups)

        # ── 确保角色 Agent 已注册 ──
        if novel.characters:
            ctx.ensure_agents(novel.characters)

        # ── 场景级循环（while 循环支持动态数量调整） ──
        scene_idx = 0
        while scene_idx < num_scenes:
            # 发送进度事件
            ctx.record_step(
                self.name, "running",
                f"场景 {scene_idx + 1}/{num_scenes}：预测→环境→角色→更新",
            )

            # ── ① 生成场景（包含事件和环境细节） ──
            scene = await generate_one_scene(
                ctx=ctx,
                novel=novel,
                plan=plan,
                current_prediction=current_prediction,
                scene_index=scene_idx,
                prev_scenes=all_scenes,
                prev_scene_actions=all_actions,
            )

            # ── ② 角色在场景中围绕事件行动 ──
            scene_id = scene.get("scene_id", f"scene_loop_{scene_idx}")
            scene_actions = await run_scene_actions(
                ctx=ctx,
                scene=scene,
                scene_id=scene_id,
            )

            # 记录该场景的行动
            scene_actions_map[scene_id] = {
                "scene_name": scene.get("time", ""),
                "actions": scene_actions,
            }
            all_actions.extend(scene_actions)
            all_scenes.append(scene)

            # ── ③ 更新预测（对比实际 vs 预测） ──
            updated_prediction = await compare_and_update_prediction(
                ctx=ctx,
                novel=novel,
                original_prediction=current_prediction,
                scene=scene,
                scene_actions=scene_actions,
                scene_index=scene_idx,
                total_scenes_planned=num_scenes,
            )

            prediction_updates.append({
                "scene_index": scene_idx,
                "before": {
                    "key_events": current_prediction.get("key_events", []),
                    "summary": current_prediction.get("summary", ""),
                },
                "after": {
                    "key_events": updated_prediction.get("key_events", []),
                    "summary": updated_prediction.get("summary", ""),
                    "deviation_report": updated_prediction.get("deviation_report", ""),
                    "prediction_status": updated_prediction.get("prediction_status", ""),
                },
            })
            current_prediction = updated_prediction

            # ── ⑤ 动态场景数量调整（基于偏差烈度） ──
            status = updated_prediction.get("prediction_status", "confirmed")
            remaining = num_scenes - scene_idx - 1

            # 大幅偏离 → 增加场景展开新局面
            if status == "fully_deviated" and num_scenes < MAX_SCENES and remaining <= 1:
                num_scenes += 1
                logger.info(
                    "预测大幅偏离（fully_deviated）→ 增加1个场景展开新局面, 总数为 %d",
                    num_scenes,
                )

            # 确认且已过MIN_SCENES → 若即将结束则不再追加
            if status == "confirmed" and scene_idx + 1 >= MIN_SCENES:
                # 如果剩余场景 > 1 且预测稳定，缩短
                if remaining > 1:
                    num_scenes = scene_idx + 2  # 再来一个场景就收尾
                    logger.info(
                        "预测已确认 → 缩短剩余场景, 最终将为 %d 个场景",
                        num_scenes,
                    )

            logger.info(
                "场景 %d/%d 完成: 「%s」, %d 个角色行动, 预测状态=%s",
                scene_idx + 1, num_scenes,
                scene.get("time", "?"),
                len(scene_actions),
                updated_prediction.get("prediction_status", "?"),
            )

            scene_idx += 1

        # ── 输出 ──
        ctx.set_output(self.name, {
            "scenes": all_scenes,
            "actions": all_actions,
            "scene_actions": scene_actions_map,
            "scene_count": len(all_scenes),
            "prediction_updates": prediction_updates,
            "final_prediction": current_prediction,
            "chapter_number": chapter_number,
        })

        logger.info(
            "场景循环完成: %d 个场景, %d 个行动, %d 轮预测更新",
            len(all_scenes), len(all_actions), len(prediction_updates),
        )
        return ctx


# ─── 辅助函数 ───────────────────────────────


def _determine_scene_count(novel, plan: dict[str, Any]) -> int:
    """确定本章的场景数量（初始值，循环中会动态调整）

    逻辑：
    - 基于关键事件数量和小说历史场景数综合判断
    - 第1章强制使用更多场景（4-6个），确保有足够过渡
    - 其他章节初始值偏低（2-4），后续根据偏差情况动态增减
    """
    key_events = plan.get("key_events", [])
    chapter_number = plan.get("chapter_number", 1)

    # 第1章强制使用更多场景，确保有足够过渡
    if chapter_number == 1:
        return max(5, len(key_events))  # 至少5个场景

    # 基于关键事件数量决定初始场景数
    # 故意留有余地（low end），因为动态调整会按需增加
    if len(key_events) >= 5:
        return 4
    elif len(key_events) >= 3:
        return 3
    elif len(key_events) >= 1:
        return max(MIN_SCENES, len(key_events) + 1)
    elif len(key_events) == 0:
        return 3

    return 3


def _groups_to_dicts(groups) -> list[dict[str, Any]]:
    """将 CharacterGroup 对象列表转为 dict 列表"""
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
                "conversation_history": getattr(g, "conversation_history", []),
            })
    return result
