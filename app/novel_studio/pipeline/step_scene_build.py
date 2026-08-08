"""Step: Scene Build — 场景构建（多场景版）

接收 scene_sequence 的场景序列，用 LLM 细化每个场景的感官细节：
- sights / sounds / smells / atmosphere
- 注册到 SceneManager
- 分配角色到对应场景
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

logger = logging.getLogger(__name__)


class SceneBuildModule(BaseModule):
    """③ 场景构建：细化场景序列中的所有场景"""

    @property
    def name(self) -> str:
        return "scene_build"

    @property
    def description(self) -> str:
        return "🌍 场景细化"

    @property
    def modifies_storage(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")
        sequence = ctx.get_output("scene_sequence")

        if not plan:
            raise ValueError("缺少章节规划")
        if not sequence:
            logger.warning("没有 scene_sequence 输出，从章节规划生成默认场景")
            scenes_in = [{
                "name": f"第{plan.get('chapter_number', 1)}章场景",
                "location": "",
                "description": plan.get("summary", ""),
                "participants": plan.get("suggested_chars", []),
                "time_period": "",
                "purpose": plan.get("purpose", ""),
                "scene_type": "主角线",
            }]
            chapter_number = plan.get("chapter_number", 1)
        else:
            scenes_in = sequence.get("scenes", [])
            chapter_number = sequence.get("chapter_number", plan.get("chapter_number", 1))

        if not scenes_in:
            logger.warning("场景序列为空，使用降级方案")
            scenes_in = [{
                "name": f"第{chapter_number}章场景",
                "location": "",
                "description": plan.get("summary", ""),
                "participants": plan.get("suggested_chars", []),
                "time_period": "",
            }]

        # 确保所有角色有 Agent
        if novel.characters:
            ctx.ensure_agents(novel.characters)

        # 尝试用 LLM 细化所有场景
        detailed_scenes = await self._detail_all_scenes(ctx, novel, plan, scenes_in, chapter_number)

        # 注册所有场景到 SceneManager 并分配角色
        from app.novel_studio.models import SceneSetting
        registered_scenes = []
        for sd in detailed_scenes:
            scene_id = f"scene_pipeline_{chapter_number}_{sd.get('name', '')[:8]}_{__import__('uuid').uuid4().hex[:6]}"
            new_scene = SceneSetting(
                id=scene_id,
                name=sd.get("name", f"第{chapter_number}章场景"),
            )
            for field in ["description", "location", "atmosphere", "weather", "time_period", "mood"]:
                if field in sd and sd[field]:
                    setattr(new_scene, field, sd[field])
            for field in ["sights", "sounds", "smells", "rules", "crowd"]:
                if field in sd and sd[field]:
                    setattr(new_scene, field, sd[field])

            ctx.add_scene_to_manager(new_scene)

            # 分配角色
            participants = sd.get("participants", [])
            assigned = []
            for char_name in participants:
                agent = ctx.get_agent_by_name(char_name)
                if agent:
                    ctx.place_character_in_scene(agent.character, scene_id)
                    assigned.append(char_name)

            # ★ 自动注入系统角色：当主角在场景中时，系统角色随之存在（意识空间）
            if novel and novel.characters:
                from app.novel_studio.models import CharacterArchetype
                sys_char = next(
                    (c for c in novel.characters.values()
                     if c.archetype == CharacterArchetype.SYSTEM),
                    None
                )
                if sys_char and sys_char.name not in assigned:
                    has_protagonist = any(
                        (c.name in assigned) and (c.archetype == CharacterArchetype.HERO)
                        for c in novel.characters.values()
                    )
                    if has_protagonist:
                        sys_agent = ctx.get_agent_by_name(sys_char.name)
                        if sys_agent:
                            ctx.place_character_in_scene(sys_agent.character, scene_id)
                            assigned.append(sys_char.name)

            # ★ 构建参与者详情
            p_details = {}
            for char_name in assigned:
                char = _find_character_by_name(novel, char_name)
                if char:
                    p_details[char_name] = {
                        "archetype": getattr(char, "archetype", ""),
                        "background": getattr(char, "background", "")[:200],
                        "personality": getattr(char, "personality", []),
                        "goal": getattr(char, "goal", ""),
                        "speech_style": getattr(char, "speech_style", ""),
                    }

            registered_scenes.append({
                "scene_id": scene_id,
                "name": new_scene.name,
                "location": new_scene.location,
                "description": new_scene.description,
                "atmosphere": new_scene.atmosphere,
                "weather": new_scene.weather,
                "time_period": new_scene.time_period,
                "sights": getattr(new_scene, "sights", []),
                "sounds": getattr(new_scene, "sounds", []),
                "smells": getattr(new_scene, "smells", []),
                "crowd": getattr(new_scene, "crowd", ""),
                "mood": getattr(new_scene, "mood", ""),
                "participants": assigned,
                "participant_details": p_details,
                "purpose": sd.get("purpose", ""),
                "scene_type": sd.get("scene_type", ""),
                "transition_from_prev": sd.get("transition_from_prev", ""),
                "key_events_done": sd.get("key_events_done", []),
            })

        logger.info("场景细化完成: %d 个场景", len(registered_scenes))
        ctx.set_output(self.name, {
            "scenes": registered_scenes,
            "chapter_number": chapter_number,
        })
        return ctx

    async def _detail_all_scenes(
        self,
        ctx: PipelineContext,
        novel,
        plan: dict,
        scenes_in: list[dict],
        chapter_number: int,
    ) -> list[dict]:
        """用 LLM 细化所有场景的感官细节"""
        client = ctx.get_llm_client("novel_writer")
        if not client:
            return scenes_in

        # 构建场景信息字符串
        scenes_text = "\n".join(
            f"场景{i+1}：{s.get('name','')}\n"
            f"  地点：{s.get('location','')}\n"
            f"  参与者：{', '.join(s.get('participants',[]))}\n"
            f"  时间：{s.get('time_period','')}\n"
            f"  场景类型：{s.get('scene_type','')}\n"
            f"  目的：{s.get('purpose','')}\n"
            for i, s in enumerate(scenes_in)
        )

        # 角色信息
        chars_text = ""
        if novel.characters:
            for c in novel.characters.values():
                name = getattr(c, "name", "?")
                arch = getattr(c, "archetype", "?")
                chars_text += f"  {name}（{arch}）\n"

        # ★ 上一章人群基线
        prev_scenes = _get_prev_chapter_scenes(novel, chapter_number)
        crowd_baseline_section = _format_prev_crowd_baseline(prev_scenes)

        prompt = f"""请为小说《{novel.title}》的第{chapter_number}章细化以下场景，补充感官细节。

## 场景序列
{scenes_text}

## 角色
{chars_text}
{crowd_baseline_section}

## 本章概要
{plan.get("summary", "")}

请为每个场景补充完整的感官细节。输出 JSON 数组（只输出 JSON）：
[
  {{
    "name": "场景名称",
    "location": "具体地点描述",
    "description": "场景详细描述（80-150字）",
    "atmosphere": "氛围（如'紧张'、'肃杀'、'欢快'）",
    "weather": "天气（如'阴雨'、'烈日'）",
    "time_period": "时间（如'傍晚'）",
    "sights": ["看到的细节1", "看到的细节2", "看到的细节3"],
    "sounds": ["听到的1", "听到的2"],
    "smells": ["闻到的1"],
    "mood": "情绪基调",
    "participants": ["参与的角色名"],
    "rules": ["场景行为限制，如果有的话"],
    "crowd": "背景人群描述（50-100字）",
    "purpose": "叙事目的",
    "scene_type": "场景类型",
    "transition_from_prev": "过渡方式"
  }}
]

注意：
- sights/sounds/smells 要是具体的感官描写，不能是抽象概念
- crowd 必须基于场景地点合理推断背景人群，不能为空（除非密室/荒野）
- 每个场景的参与者只包含真正在该场景的角色
- 场景顺序不变，保持原有的先后关系"""

        system_prompt = f"你正在为小说《{novel.title}》设计场景。只输出 JSON。场景设计必须物理合理。"

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7,
        )
        text = text or ""

        detailed = self._parse_json_array(text)
        if detailed and len(detailed) == len(scenes_in):
            # 保留原始场景中的字段，合并 LLM 生成的细节
            result = []
            for i, orig in enumerate(scenes_in):
                merged = dict(orig)
                if i < len(detailed):
                    for k in ["location", "description", "atmosphere", "weather",
                              "time_period", "sights", "sounds", "smells", "mood", "rules", "crowd"]:
                        if detailed[i].get(k):
                            merged[k] = detailed[i][k]
                result.append(merged)
            return result

        # 降级
        logger.warning("场景细化 JSON 解析失败，使用原始场景")
        return scenes_in

    def _parse_json_array(self, text: str) -> list[dict] | None:
        import re
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                pass
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None


# ─── 单场景细化函数（供 scene_loop 调用） ─────────────────

# 大纲阻断标记：场景细化只包含环境/感官信息，不包含剧情暗示
_SCENE_BUILD_BLOCKED = object()


def _find_character_by_name(novel, name: str):
    """从小说角色字典中按名称查找角色对象。"""
    if not novel or not hasattr(novel, "characters"):
        return None
    chars = novel.characters
    if isinstance(chars, dict):
        for c in chars.values():
            cname = getattr(c, "name", "") if hasattr(c, "name") else c.get("name", "")
            if cname == name:
                return c
    return None


def _get_prev_chapter_scenes(novel, chapter_number: int) -> list[dict]:
    """从上一章已持久化的 scenes 数据中提取人群基线。

    直接读取 Chapter.scenes 结构化数据，不做任何正则解析。
    返回上一章所有场景的 crowd 字段列表。
    """
    if chapter_number <= 1:
        return []

    chapters = getattr(novel, "chapters", None) or []
    for ch in chapters:
        num = getattr(ch, "number", 0) if hasattr(ch, "number") else ch.get("number", 0)
        if num == chapter_number - 1:
            scenes = getattr(ch, "scenes", []) if hasattr(ch, "scenes") else ch.get("scenes", [])
            return scenes if isinstance(scenes, list) else []

    return []


def _format_prev_crowd_baseline(prev_scenes: list[dict]) -> str:
    """将上一章场景数据格式化为 LLM 可读的人群基线文本。"""
    if not prev_scenes:
        return ""

    lines = ["## ⚠️ 上一章人群基线（crowd 必须与此连续）"]
    for i, s in enumerate(prev_scenes):
        name = s.get("name", f"场景{i+1}")
        crowd = s.get("crowd", "")
        participants = s.get("participants", [])
        if crowd or participants:
            lines.append(f"\n场景「{name}」：")
            if crowd:
                lines.append(f"  背景人群：{crowd}")
            if participants:
                lines.append(f"  参与者：{'、'.join(participants)}")

    lines.append("\n【关键】crowd 字段中的人数、构成、状态必须与上一章基线保持连续。")
    lines.append("- 人数不能凭空增减（除非本章明确发生了死亡/离开/新加入事件）")
    lines.append("- 如果上一章说「庙内约二十人」，本章不能说「几十人」或「上百人」")
    return "\n".join(lines)


async def detail_one_scene(
    ctx: PipelineContext,
    novel,
    plan: dict[str, Any],
    scene_skeleton: dict[str, Any],
    chapter_number: int,
    prev_scene_state: dict[str, Any] | None = None,
    character_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """细化单个场景的环境/感官细节（大纲阻断版 + 世界背景注入）

    新参数：
        prev_scene_state: 上一场景的 SceneState，用于场景衔接
        character_groups: 人物群体列表，含会话历史
    """
    client = ctx.get_llm_client("novel_writer")

    # 确保角色 Agent 已注册
    if novel.characters:
        ctx.ensure_agents(novel.characters)

    # ★ 提取上一章场景数据（用于跨章人群一致性锚定）
    prev_scenes = _get_prev_chapter_scenes(novel, chapter_number)
    crowd_baseline = _format_prev_crowd_baseline(prev_scenes)

    # 尝试用 LLM 细化
    if client:
        detailed = await _detail_single_scene_llm(
            ctx, novel, plan, scene_skeleton, chapter_number,
            prev_crowd_baseline=crowd_baseline,
            prev_scene_state=prev_scene_state,
            character_groups=character_groups,
        )
    else:
        detailed = scene_skeleton

    # 注册到 SceneManager
    from app.novel_studio.models import SceneSetting
    import uuid

    scene_id = (
        f"scene_pipeline_{chapter_number}_"
        f"{detailed.get('name', '')[:8]}_{uuid.uuid4().hex[:6]}"
    )
    new_scene = SceneSetting(
        id=scene_id,
        name=detailed.get("name", f"第{chapter_number}章场景"),
    )
    for field in ["description", "location", "atmosphere", "weather",
                   "time_period", "mood"]:
        if field in detailed and detailed[field]:
            setattr(new_scene, field, detailed[field])
    for field in ["sights", "sounds", "smells", "rules", "crowd"]:
        if field in detailed and detailed[field]:
            setattr(new_scene, field, detailed[field])

    ctx.add_scene_to_manager(new_scene)

    # 分配角色
    participants = detailed.get("participants", [])
    assigned = []
    for char_name in participants:
        agent = ctx.get_agent_by_name(char_name)
        if agent:
            ctx.place_character_in_scene(agent.character, scene_id)
            assigned.append(char_name)

    # ★ 自动注入系统角色：当主角在场景中时，系统角色随之存在（意识空间）
    if novel and novel.characters:
        from app.novel_studio.models import CharacterArchetype
        sys_char = next(
            (c for c in novel.characters.values()
             if c.archetype == CharacterArchetype.SYSTEM),
            None
        )
        if sys_char and sys_char.name not in assigned:
            has_protagonist = any(
                (c.name in assigned) and (c.archetype == CharacterArchetype.HERO)
                for c in novel.characters.values()
            )
            if has_protagonist:
                sys_agent = ctx.get_agent_by_name(sys_char.name)
                if sys_agent:
                    ctx.place_character_in_scene(sys_agent.character, scene_id)
                    assigned.append(sys_char.name)

    logger.info("场景细化完成: %s (%s)", detailed.get("name", "?"), scene_id)

    # ★ 构建参与者详情（供 character_action 和 narrative 使用）
    participant_details = {}
    for char_name in assigned:
        char = _find_character_by_name(novel, char_name)
        if char:
            participant_details[char_name] = {
                "archetype": getattr(char, "archetype", ""),
                "background": getattr(char, "background", "")[:200],
                "personality": getattr(char, "personality", []),
                "goal": getattr(char, "goal", ""),
                "speech_style": getattr(char, "speech_style", ""),
            }

    registered = {
        "scene_id": scene_id,
        "name": new_scene.name,
        "location": new_scene.location,
        "description": new_scene.description,
        "atmosphere": new_scene.atmosphere,
        "weather": new_scene.weather,
        "time_period": new_scene.time_period,
        "sights": getattr(new_scene, "sights", []),
        "sounds": getattr(new_scene, "sounds", []),
        "smells": getattr(new_scene, "smells", []),
        "crowd": getattr(new_scene, "crowd", ""),
        "mood": getattr(new_scene, "mood", ""),
        "participants": assigned,
        "participant_details": participant_details,
        "purpose": detailed.get("purpose", ""),
        "scene_type": detailed.get("scene_type", ""),
        "transition_from_prev": detailed.get("transition_from_prev", ""),
        "key_events_done": detailed.get("key_events_done", []),
    }
    return registered


async def _detail_single_scene_llm(
    ctx: PipelineContext,
    novel,
    plan: dict[str, Any],
    scene: dict[str, Any],
    chapter_number: int,
    prev_crowd_baseline: str = "",
    prev_scene_state: dict[str, Any] | None = None,
    character_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """用 LLM 细化单场景的环境/感官细节，注入世界背景"""
    client = ctx.get_llm_client("novel_writer")
    if not client:
        return scene

    # 构建角色信息
    chars_text = ""
    if novel.characters:
        for c in novel.characters.values():
            name = getattr(c, "name", "?")
            arch = getattr(c, "archetype", "?")
            chars_text += f"  {name}（{arch}）\n"

    scene_text = (
        f"场景名称：{scene.get('name', '')}\n"
        f"地点：{scene.get('location', '')}\n"
        f"参与者：{', '.join(scene.get('participants', []))}\n"
        f"时间：{scene.get('time_period', '')}\n"
        f"场景类型：{scene.get('scene_type', '')}\n"
        f"目的：{scene.get('purpose', '')}"
    )

    # ★ 上一章人群基线（跨章一致性锚定）
    crowd_baseline_section = prev_crowd_baseline or ""

    # ★ 新增：世界历史背景
    world_section = _build_world_context_section(novel)

    # ★ 新增：历史人物介绍
    hist_fig_section = _build_historical_figures_section(novel)

    # ★ 新增：人物群体（含会话历史）
    groups_section = _build_character_groups_section(character_groups or [])

    # ★ 新增：空间衔接
    space_section = _build_space_continuity_section(prev_scene_state)

    prompt = f"""请为小说《{novel.title}》的第{chapter_number}章细化以下场景的**环境/感官细节**。

{world_section}
{hist_fig_section}
{groups_section}
{space_section}

## 场景信息
{scene_text}

## 角色
{chars_text}
{crowd_baseline_section}

## 输出要求
请为这个场景补充完整的**感官细节**。只描述环境——
角色在这个场景中能看到什么、听到什么、闻到什么、感受到什么氛围。

### ⚠️ 重要：不要包含任何剧情事件或故事走向暗示
你只设计「在哪里」「什么时间」「什么环境」，而不是「要发生什么」。

输出 JSON（只输出 JSON）：
{{
  "name": "场景名称（保留原始名称）",
  "location": "具体地点描述（扩展细节）",
  "description": "场景详细描述（80-150字，纯环境/感官）",
  "atmosphere": "氛围（如'阴森'、'安静'、'热闹'）",
  "weather": "天气（如'阴雨绵绵'、'烈日当空'）",
  "time_period": "时间（如'傍晚'）",
  "sights": ["眼睛能看到的细节1", "细节2", "细节3"],
  "sounds": ["耳朵能听到的1", "声音2"],
  "smells": ["鼻子能闻到的1"],
  "mood": "情绪基调",
  "rules": ["场景行为限制（如果有的话）"],
  "crowd": "背景人群描述（50-100字，如'角落里横七竖八躺着三十多个人，有的在哼唧，有的已经不动了。外面窝棚里还挤着十几个人取暖。远处空地排着长队。'）",
  "participants": ["保留原始参与者"],
  "purpose": "保留原始叙事目的",
  "scene_type": "保留原始场景类型",
  "transition_from_prev": "保留原始过渡信息"
}}

## ⚠️ 关键：crowd（背景人群）
crowd 字段记录场景中除参与者之外的**背景人群**——路人、围观者、同处一地的其他人。
- 必须基于场景地点和上下文合理推断
- 不能为空（除非场景确实无人，如密室/荒野）
- 这是叙事合成时防止「人群蒸发」的关键信息
- 如果提供了「上一章人群基线」，crowd 必须与基线保持数量/构成连续"""

    system_prompt = (
        f"你正在为小说《{novel.title}》设计场景环境。"
        f"只输出 JSON。只描述环境，不写剧情。"
    )

    text, _ = client.chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.7,
    )
    text = text or ""

    import re
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            detailed = json.loads(m.group())
            if isinstance(detailed, dict):
                result = dict(scene)
                for k in ["location", "description", "atmosphere", "weather",
                          "time_period", "sights", "sounds", "smells", "mood",
                          "rules", "crowd"]:
                    if detailed.get(k):
                        result[k] = detailed[k]
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("单场景细化 JSON 解析失败，使用原始场景")
    return scene


# ─── 世界背景构建函数 ───────────────────────────────

def _build_world_context_section(novel) -> str:
    """构建世界历史背景文本"""
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
    return "\n\n".join(parts)


def _build_historical_figures_section(novel) -> str:
    """构建历史人物介绍文本"""
    world = getattr(novel, "world", None)
    if not world:
        return ""
    figures = getattr(world, "historical_figures", []) or []
    if not figures:
        return ""
    lines = ["## 时代重要人物"]
    for f in figures:
        name = f.get("name", f.name) if hasattr(f, "get") else getattr(f, "name", "?")
        title = f.get("title", "") if hasattr(f, "get") else getattr(f, "title", "")
        desc = f.get("description", "") if hasattr(f, "get") else getattr(f, "description", "")
        loc = f.get("current_location", "") if hasattr(f, "get") else getattr(f, "current_location", "")
        status = f.get("current_status", "") if hasattr(f, "get") else getattr(f, "current_status", "")
        lines.append(f"\n### {name}（{title}）")
        lines.append(f"位置：{loc}")
        lines.append(f"简介：{desc}")
        if status:
            lines.append(f"当前动向：{status}")
    return "\n".join(lines)


def _build_character_groups_section(groups: list[dict[str, Any]]) -> str:
    """构建人物群体文本（含会话历史）"""
    if not groups:
        return ""
    lines = ["## 人物群体"]
    for g in groups:
        name = g.get("name", "?")
        desc = g.get("description", "")
        dynamics = g.get("dynamics", "")
        members = g.get("member_profiles", {})
        history = g.get("conversation_history", [])
        lines.append(f"\n### {name}")
        if desc:
            lines.append(f"概述：{desc}")
        if dynamics:
            lines.append(f"内部关系：{dynamics}")
        if members:
            lines.append("成员简介：")
            for mname, mdesc in members.items():
                lines.append(f"  - {mname}：{mdesc}")
        if history:
            lines.append("会话历史：")
            for h in history:
                speaker = h.get("speaker", "?")
                content = h.get("content", "")
                action = h.get("action", "")
                entry = f"  {speaker}：{content}"
                if action:
                    entry += f"（{action}）"
                lines.append(entry)
    return "\n".join(lines)


def _build_space_continuity_section(prev_scene_state: dict[str, Any] | None) -> str:
    """构建空间衔接文本"""
    if not prev_scene_state:
        return ""
    pos = prev_scene_state.get("position_landmark", "")
    desc = prev_scene_state.get("position_description", "")
    time_of_day = prev_scene_state.get("time_of_day", "")
    chars = prev_scene_state.get("characters_present", [])
    conflict = prev_scene_state.get("conflict", "")
    emotion = prev_scene_state.get("emotional_temperature", "")
    if not pos and not desc:
        return ""
    lines = ["## 上一场景结束状态"]
    if pos:
        lines.append(f"位置：{pos}")
    if desc:
        lines.append(f"描述：{desc}")
    if time_of_day:
        lines.append(f"时间：{time_of_day}")
    if chars:
        lines.append(f"在场人物：{', '.join(chars)}")
    if conflict:
        lines.append(f"当前冲突：{conflict}")
    if emotion:
        lines.append(f"情绪温度：{emotion}")
    lines.append("\n【关键】新场景的位置必须与上一场景结束位置衔接。场景转换需要明确移动过程和时间流逝。")
    return "\n".join(lines)
