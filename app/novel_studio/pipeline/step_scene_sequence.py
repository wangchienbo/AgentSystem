"""Step: Scene Sequence — 场景序列生成

根据章节规划和 4 原则（非主角在场场景/重要事件/主角线/重要时间点）
生成一章内多个场景的序列。每个场景知道与前后场景的衔接关系。

场景序列的输出被 scene_build 和 narrative 使用。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

logger = logging.getLogger(__name__)


class SceneSequenceModule(BaseModule):
    """② 场景序列：按 4 原则生成多场景序列"""

    @property
    def name(self) -> str:
        return "scene_sequence"

    @property
    def description(self) -> str:
        return "🎬 场景序列（4原则多场景）"

    @property
    def modifies_storage(self) -> bool:
        return False

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")
        if not plan:
            raise ValueError("缺少章节规划，请先执行 chapter_plan 模块")

        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # 获取上一章的最后场景信息（用于连续性）
        prev_chapter_ending = self._get_prev_chapter_ending(novel)

        # 获取角色列表
        chars_text = self._build_chars_context(novel.characters)

        client = ctx.get_llm_client("novel_writer")
        if not client:
            # 降级：生成一个默认场景
            ctx.set_output(self.name, {
                "scenes": [{
                    "name": f"第{chapter_number}章场景",
                    "location": "",
                    "description": plan.get("summary", ""),
                    "participants": plan.get("suggested_chars", []),
                    "time_period": "",
                    "purpose": plan.get("purpose", ""),
                    "scene_type": "主角线",
                    "key_events": plan.get("key_events", []),
                }],
                "chapter_number": chapter_number,
            })
            return ctx

        prompt = self._build_prompt(novel, plan, chapter_number, prev_chapter_ending, chars_text)
        system_prompt = (
            f"你是一位小说场景序列设计师。为小说《{novel.title}》的第{chapter_number}章设计场景序列。"
            f"只输出 JSON，不要其他文字。"
        )

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        text = text or ""

        scenes = self._parse_scenes(text, plan)
        logger.info("场景序列生成: %d 个场景", len(scenes))

        ctx.set_output(self.name, {
            "scenes": scenes,
            "chapter_number": chapter_number,
        })
        return ctx

    def _get_prev_chapter_ending(self, novel) -> str:
        """获取上一章最后的场景和时间线"""
        chapters = getattr(novel, "chapters", []) or []
        if not chapters:
            return "（尚无已写章节）"

        prev = chapters[-1]
        content = getattr(prev, "content", "") or ""
        if not content:
            return "（上一章无内容）"

        # 取最后 1500 字作为上下文
        ending = content[-1500:] if len(content) > 1500 else content
        return (
            f"上一章《{getattr(prev, 'title', '')}》结尾：\n"
            f"{ending}"
        )

    def _build_chars_context(self, characters) -> str:
        """构建角色上下文（实例方法，委托给模块级函数）"""
        return build_chars_context(characters)


def build_chars_context(characters) -> str:
    """构建角色上下文（模块级函数，供 scene_loop 内部调用）"""
    if not characters:
        return "（尚无角色）"
    lines = []
    for c in characters.values():
        name = getattr(c, "name", "?")
        arch = getattr(c, "archetype", "?")
        personality = "、".join(getattr(c, "personality", []) or [])
        bg = getattr(c, "background", "") or ""
        lines.append(f"  - {name}（{arch}）{personality}")
        if bg:
            lines.append(f"    背景：{bg[:100]}")
    return "\n".join(lines)

    def _build_prompt(
        self,
        novel,
        plan: dict,
        chapter_number: int,
        prev_chapter_ending: str,
        chars_text: str,
    ) -> str:
        # 从世界观提取已有场景
        world = getattr(novel, "world", None)
        existing_scenes_text = ""
        if world:
            scenes = getattr(world, "scenes", {}) or {}
            if scenes:
                scene_list = []
                for sid, s in list(scenes.items())[:5]:
                    scene_list.append(f"  {getattr(s, 'name', '?')}：{getattr(s, 'location', '')}")
                existing_scenes_text = "\n".join(scene_list)

        # 关键事件
        key_events = plan.get("key_events", [])
        events_text = "\n".join(f"  {i+1}. {ev}" for i, ev in enumerate(key_events))

        return f"""为小说《{novel.title}》的第{chapter_number}章设计场景序列。

## 本章规划
标题：{plan.get("title", "")}
概要：{plan.get("summary", "")}
故事作用：{plan.get("purpose", "")}
关键事件：
{events_text}

## 上一章结尾（必须从此处接续）
{prev_chapter_ending}

## 已有场景
{existing_scenes_text or "尚无场景"}

## 角色
{chars_text}

## 场景设计原则
请按以下 4 条原则设计 2-4 个场景：

1️⃣ **主角线** — 主角（沈逸之）在场的场景，推动主角的故事线
2️⃣ **非主角在场场景** — 其他角色单独行动的副线场景（张献忠、李定国等在没有主角时做什么）
3️⃣ **重要事件** — 剧情关键节点必须有对应的场景
4️⃣ **重要时间点** — 时间变化标志（晨/午/昏/夜，或日期推进）

### 场景衔接要求
- 第1个场景必须从上一章结尾处直接开始（时间连续、地点连续）
- 每个场景之间要有自然的过渡（时间流逝或空间转移）
- 场景顺序必须合理（不能出现时间倒流）

### 每个场景的参与者
- 写清楚谁在这个场景中
- 不在场的人不能参与场景
- 一个角色可以出现在多个场景中

输出 JSON 数组（只输出 JSON，不要其他文字）：
[
  {{
    "name": "场景名称（如'破庙避雨'）",
    "location": "具体地点",
    "description": "场景的详细描述（50-100字）",
    "participants": ["参与的角色名数组"],
    "time_period": "时间（如'黄昏'）",
    "purpose": "这个场景要达成什么叙事目的",
    "scene_type": "主角线/非主角场/重要事件/重要时间点",
    "transition_from_prev": "如何从上一场景/上一章过渡到此场景",
    "key_events_done": ["此场景中完成的关键事件索引"]
  }}
]"""

    def _parse_scenes(self, text: str, plan: dict) -> list[dict]:
        """从 LLM 输出解析场景序列"""
        import re

        # 尝试提取 JSON
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                scenes = json.loads(m.group())
                if isinstance(scenes, list):
                    return scenes
            except (json.JSONDecodeError, ValueError):
                pass

        # 如果解析失败，用 LLM 生成的文本再试
        try:
            scenes = json.loads(text)
            if isinstance(scenes, list):
                return scenes
        except (json.JSONDecodeError, ValueError):
            pass

        # 降级：生成一个默认场景
        logger.warning("场景序列 JSON 解析失败，使用降级方案")
        return [{
            "name": f"第{plan.get('chapter_number', '?')}章场景",
            "location": "",
            "description": plan.get("summary", "") or text[:200],
            "participants": plan.get("suggested_chars", []),
            "time_period": "",
            "purpose": plan.get("purpose", ""),
            "scene_type": "主角线",
            "transition_from_prev": "",
            "key_events_done": [],
        }]


# ─── 单场景生成函数（供 scene_loop 调用） ────────────────────

# 大纲阻断标记：场景骨架不包含关键事件/剧情暗示
# 此处暴露给 scene_loop 的函数，调用方负责决定是否传入预测上下文
_OUTLINE_BLOCKED_MARKER = object()


async def generate_one_scene(
    ctx: PipelineContext,
    novel,
    plan: dict[str, Any],
    current_prediction: dict[str, Any],
    scene_index: int,
    prev_scenes: list[dict[str, Any]],
    prev_scene_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """基于当前预测状态生成一个场景（不暴露后续剧情给 LLM）

    Args:
        ctx: 管道上下文
        novel: 小说数据
        plan: 原始 chapter_plan 输出
        current_prediction: 当前预测状态（来自 outline_update 或初始 chapter_plan）
        scene_index: 本场景序号（0-based）
        prev_scenes: 之前已生成的场景列表
        prev_scene_actions: 之前场景的角色行动列表

    Returns:
        单个场景骨架字典（格式同原有 scenes 数组中的单个元素）
    """
    chapter_number = plan.get("chapter_number", 1)

    # 获取上一场景结尾（用于连续性）
    prev_scene_ending = _build_prev_scene_context(prev_scenes, prev_scene_actions, scene_index)

    # 获取初始预测信息（但不泄漏未发生的剧情！）
    prediction_summary = current_prediction.get("summary", plan.get("summary", ""))
    prediction_purpose = current_prediction.get("purpose", plan.get("purpose", ""))
    deviation = current_prediction.get("deviation_report", "")
    # ★ 新：显式提取 next_scene_hint（原本被生成但从未被使用！）
    next_scene_hint = current_prediction.get("next_scene_hint", "")
    prediction_status = current_prediction.get("prediction_status", "confirmed")
    # ★ 新：提取未解决线索（outline_update 新输出）
    unresolved_threads = current_prediction.get("unresolved_threads", [])

    # 角色上下文
    chars_text = build_chars_context(novel.characters)
    # 已有场景上下文
    existing_scenes_text = _build_existing_scenes_context(prev_scenes)

    client = ctx.get_llm_client("novel_writer")
    if not client:
        # 降级
        return _fallback_scene(plan, scene_index)

    prompt = _build_single_scene_prompt(
        novel, plan, chapter_number,
        prediction_summary, prediction_purpose, deviation, next_scene_hint,
        prediction_status, unresolved_threads,
        scene_index, prev_scene_ending, existing_scenes_text,
        chars_text, prev_scenes, prev_scene_actions,
    )

    system_prompt = (
        f"你是一位小说场景设计师。为小说《{novel.title}》的第{chapter_number}章设计一个场景。"
        f"只输出 JSON。注意：你设计的不是剧情，而是角色们将要在什么环境中行动。"
    )

    text, _ = client.chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.7,
    )
    text = text or ""

    scene = _parse_single_scene(text, plan, scene_index)
    return scene


# ─── 单场景 Prompt 构建（大纲阻断版） ────────────


def _choose_scene_type(
    scene_index: int,
    prediction_status: str,
    unresolved_threads: list[str],
) -> str:
    """动态选择场景类型：基于偏差状态 + 未解决线索，而非固定4原则循环

    核心逻辑：
    - 第1个场景始终为「主角线」（角色需要先登场）
    - 有 fully_deviation → 选「重要事件」来重新校准
    - 有未解决线索涉及非主角 → 选「非主角场」
    - 时间已过半天 → 选「重要时间点」
    - 其余情况按4原则循环但以需求优先
    """
    if scene_index == 0:
        return "主角线"

    # 如果完全偏离，需要重新校准
    if prediction_status == "fully_deviated":
        return "重要事件"

    # 如果有关键未解决线索
    if unresolved_threads:
        # 检查是否包含非主角线索（对手、事件等）
        thread_text = "\n".join(unresolved_threads)
        non_protagonist_keywords = ["对手", "反派", "威胁", "盯上", "敌人", "势力", "追兵"]
        if any(kw in thread_text for kw in non_protagonist_keywords):
            return "非主角场"
        return "重要事件"

    # 按4原则轮转，但更灵活
    scene_types = ["主角线", "非主角场", "重要事件", "重要时间点"]
    return scene_types[scene_index % len(scene_types)]


def _build_single_scene_prompt(
    novel,
    plan: dict[str, Any],
    chapter_number: int,
    prediction_summary: str,
    prediction_purpose: str,
    deviation: str,
    next_scene_hint: str,
    prediction_status: str,
    unresolved_threads: list[str],
    scene_index: int,
    prev_scene_ending: str,
    existing_scenes_text: str,
    chars_text: str,
    prev_scenes: list[dict[str, Any]],
    prev_scene_actions: list[dict[str, Any]],
) -> str:
    """构建单场景 prompt —— 只描述环境，不暗示剧情"""

    # 动态场景类型选择：基于偏差状态 + 未解决线索，而非固定循环
    scene_type = _choose_scene_type(scene_index, prediction_status, unresolved_threads)

    # 是否有前一场景的信息
    prev_context = prev_scene_ending or "（这是本章第一个场景）"

    # 偏差信息（仅作为方向提示，不包含具体剧情）
    deviation_hint = ""
    if deviation and scene_index > 0:
        deviation_hint = f"\n方向提示：{deviation}"

    # ★ 新：next_scene_hint（来自 outline_update 的精准方向建议）
    hint_section = ""
    if next_scene_hint and scene_index > 0:
        hint_section = f"\n📍 预测建议：{next_scene_hint}"

    # ★ 新：未解决线索（松散叙事线，需要在未来场景中延续）
    threads_section = ""
    if unresolved_threads and scene_index > 0:
        thread_lines = [f"  - {t}" for t in unresolved_threads]
        threads_section = "\n📌 需延续的叙事线：\n" + "\n".join(thread_lines)

    # 偏差程度提示
    status_note = ""
    if prediction_status == "fully_deviated" and scene_index > 0:
        status_note = "\n⚠️ 注意：上一场景结果大幅偏离了预期，此方向需要重新调整。"
    elif prediction_status == "confirmed" and scene_index > 0:
        status_note = "\n✅ 故事发展符合预期方向，可按计划推进。"

    return f"""为小说《{novel.title}》的第{chapter_number}章设计一个场景。

{build_novel_context(novel)}

## 本章概要（预测方向）
{prediction_summary or "（待定）"}
故事作用：{prediction_purpose or "（待定）"}{deviation_hint}{hint_section}{status_note}{threads_section}

## 场景上下文
{prev_context}

## 已有场景
{existing_scenes_text or "（尚无场景）"}

## 角色
{chars_text}

## 设计约束
这是本章的第 {scene_index + 1} 个场景。
场景类型建议：{scene_type}

### ⚠️ 重要规则
- **不要包含剧情事件或关键情节暗示** —— 你只设计场景的环境和氛围
- 场景应该物理合理、有沉浸感
- 描述感官细节：角色能看到什么？听到什么？闻到什么？
- 天气、光线、温度、气味、氛围 —— 这些才是你的输出内容
- 不要暗示"要发生什么"，只说"有什么"

### 场景衔接要求
- 如果是本章第1个场景：从上一章结尾处或上一个场景的结尾自然接续
- 如果是第2个及以后的场景：从前一个场景的结尾时间/地点自然过渡
- 场景中的角色：写清楚谁在场

### 🔗 叙事延续要求
- 之前场景中出现过的角色和冲突线，应当在本场景中有所体现
- 如果某角色在之前场景中采取了行动，其后果应适时在本场景中显现
- 如果某冲突尚未解决（如威胁正在逼近），本场景应感知到它的存在

输出 JSON（只输出 JSON）：
{{
  "name": "场景名称（如'雨夜小巷'）",
  "location": "具体地点描述",
  "description": "场景的物理/感官描述（80-150字，纯环境，不包含剧情）",
  "participants": ["参与的角色名数组"],
  "time_period": "时间（如'深夜'）",
  "purpose": "这个场景在叙事上的作用",
  "scene_type": "{scene_type}",
  "transition_from_prev": "如何从前一场景或前一章结尾过渡到此"
}}"""""


# ─── 辅助函数 ────────────────────────────────


def _build_prev_scene_context(
    prev_scenes: list[dict[str, Any]],
    prev_actions: list[dict[str, Any]],
    scene_index: int,
) -> str:
    """构建前一场景的结尾上下文"""
    if scene_index == 0 or not prev_scenes:
        return ""

    prev = prev_scenes[-1]
    name = prev.get("name", "?")
    loc = prev.get("location", "")
    desc = prev.get("description", "")
    time_p = prev.get("time_period", "")

    # 提取前一场景的角色行动摘要（最多150字）
    actions_summary = ""
    scene_actions = []
    if scene_index <= len(prev_scenes):
        # 简单匹配：取每个场景对应的 actions（按场景划分）
        for a in prev_actions:
            if a.get("scene_id", "").endswith(f"_{scene_index - 1}"):
                scene_actions.append(a)
    if scene_actions:
        lines = []
        for a in scene_actions[:3]:  # 最多3个行动
            c = a.get("character", "?")
            act = a.get("action", "")
            dia = a.get("dialogue", "")
            if dia and dia != "沉默":
                lines.append(f"{c}{act}，说「{dia[:60]}」")
            else:
                lines.append(f"{c}{act}")
        if lines:
            actions_summary = "\n".join(lines)

    parts = [f"上一场景「{name}」"]
    if time_p:
        parts.append(f"（{time_p}）")
    if loc:
        parts.append(f"位于{loc}")
    parts.append(f"：{desc[:100]}")
    if actions_summary:
        parts.append(f"\n场景中发生的事：\n{actions_summary}")

    return "".join(parts)


def _build_existing_scenes_context(prev_scenes: list[dict[str, Any]]) -> str:
    """构建已有场景列表"""
    if not prev_scenes:
        return ""
    lines = []
    for i, s in enumerate(prev_scenes):
        name = s.get("name", "?")
        loc = s.get("location", "")
        time_p = s.get("time_period", "")
        participants = "、".join(s.get("participants", []))
        lines.append(f"  场景{i+1}：{name}（{loc}，{time_p}，参与者：{participants}）")
    return "\n".join(lines)


def _fallback_scene(plan: dict[str, Any], scene_index: int) -> dict[str, Any]:
    """降级场景"""
    scene_types = ["主角线", "非主角场", "重要事件", "重要时间点"]
    return {
        "name": f"第{plan.get('chapter_number', '?')}章场景{scene_index + 1}",
        "location": "",
        "description": plan.get("summary", ""),
        "participants": plan.get("suggested_chars", []),
        "time_period": "",
        "purpose": plan.get("purpose", ""),
        "scene_type": scene_types[scene_index % 4],
        "transition_from_prev": "",
    }


def _parse_single_scene(text: str, plan: dict[str, Any], scene_index: int) -> dict[str, Any]:
    """从 LLM 输出解析单场景"""
    import re

    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            scene = json.loads(m.group())
            if isinstance(scene, dict):
                return scene
        except (json.JSONDecodeError, ValueError):
            pass

    try:
        scene = json.loads(text)
        if isinstance(scene, dict):
            return scene
    except (json.JSONDecodeError, ValueError):
        pass

    logger.warning("单场景 JSON 解析失败，使用降级方案")
    return _fallback_scene(plan, scene_index)
