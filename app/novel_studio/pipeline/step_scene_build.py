"""Step: Scene Build — 场景构建

根据章节规划选择/生成场景，分配角色到场景。
场景中包含：地点、氛围、感官细节（看到的/听到的/闻到的）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class SceneBuildModule(BaseModule):
    """③ 场景构建：定地点、氛围、参与者"""

    @property
    def name(self) -> str:
        return "scene_build"

    @property
    def description(self) -> str:
        return "🌍 场景构建"

    @property
    def modifies_storage(self) -> bool:
        return True  # 会向 world.scenes 添加新场景

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        novel = ctx.novel
        plan = ctx.get_output("chapter_plan")
        if not plan:
            raise ValueError("缺少章节规划，请先执行 chapter_plan 模块")

        # 确保所有角色有 Agent
        if novel.characters:
            ctx.ensure_agents(novel.characters)

        suggested_chars = plan.get("suggested_chars", [])
        chapter_number = plan.get("chapter_number", len(novel.chapters) + 1)

        # 尝试从现有场景选一个合适的
        existing_scenes = novel.world.scenes if novel.world and novel.world.scenes else {}

        # 如果有已有场景并且有角色分配，复用
        if existing_scenes:
            scene = _pick_existing_scene(existing_scenes, suggested_chars, novel.characters, ctx)
            if scene:
                logger.info("复用已有场景: %s", scene.name)
                # 确保场景注册到 SceneManager
                if not ctx.get_occupants(scene.id):
                    ctx.add_scene_to_manager(scene)
                # 分配角色到场景（如果还没分配）
                occupants = ctx.get_occupants(scene.id)
                if not occupants:
                    chars_to_assign = suggested_chars or list(novel.characters.keys())[:3]
                    for char_name in chars_to_assign:
                        for cid, char in novel.characters.items():
                            if char.name == char_name:
                                ctx.place_character_in_scene(char, scene.id)
                                break
                    occupants = ctx.get_occupants(scene.id)
                # 返回包含 occupants 的 scene 输出
                output = _scene_to_output(scene, novel)
                output["occupants"] = [c.name for c in occupants] if occupants else chars_to_assign[:3]
                ctx.set_output(self.name, output)
                return ctx

        # 没有合适场景 → 让 LLM 生成场景
        client = ctx.get_llm_client("novel_writer")
        if not client:
            raise RuntimeError("LLM 客户端未配置")

        existing_scenes_text = _build_scenes_context(existing_scenes)
        chars_text = _build_chars_context(novel.characters, suggested_chars)

        prompt = f"""你是一位小说场景设计师。请为小说《{novel.title}》的第{chapter_number}章设计场景。

## 本章规划
标题：{plan.get("title","")}
概要：{plan.get("summary","")}
关键事件：{", ".join(plan.get("key_events",[]))}

## 已有场景
{existing_scenes_text or "尚无场景"}

## 参与角色
{chars_text}

请设计一个符合本章需求的场景。输出 JSON：
{{
  "name": "场景名称（如'京城正阳门外'）",
  "location": "具体地点描述",
  "description": "场景的详细描述（供角色感知用）",
  "atmosphere": "氛围（如'紧张'、'欢快'）",
  "weather": "天气",
  "time_period": "时间（如'傍晚'）",
  "sights": ["看到的1", "看到的2"],
  "sounds": ["听到的1", "听到的2"],
  "smells": ["闻到的1"],
  "mood": "情绪基调",
  "occupants": ["参与的角色名列表"],
  "rules": ["场景特殊规则，如果有的话"]
}}"""

        system_prompt = f"你正在为小说《{novel.title}》设计场景。只输出 JSON。"
        text, _ = client.chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.8,
        )
        text = text or ""

        scene_data = _parse_json_output(text)
        if not scene_data:
            scene_data = {
                "name": f"场景-第{chapter_number}章",
                "location": "",
                "description": text[:500],
                "atmosphere": "",
                "occupants": suggested_chars[:3],
            }

        # 保存到 Novel.world.scenes
        from app.novel_studio.models import SceneSetting
        scene_id = f"scene_pipeline_{chapter_number}_{__import__('uuid').uuid4().hex[:8]}"
        new_scene = SceneSetting(
            id=scene_id,
            name=scene_data.get("name", f"第{chapter_number}章场景"),
        )
        for field in ["description", "location", "atmosphere", "weather", "time_period", "mood"]:
            if field in scene_data and scene_data[field]:
                setattr(new_scene, field, scene_data[field])
        for field in ["sights", "sounds", "smells", "rules"]:
            if field in scene_data and scene_data[field]:
                setattr(new_scene, field, scene_data[field])

        ctx.add_scene_to_manager(new_scene)

        # 分配角色到场景
        occupants = scene_data.get("occupants", suggested_chars)
        assigned_chars = []
        for char_name in occupants:
            agent = ctx.get_agent_by_name(char_name)
            if agent:
                ctx.place_character_in_scene(agent.character, scene_id)
                assigned_chars.append(char_name)

        logger.info("新建场景: %s (%s), %d个角色进入", new_scene.name, scene_id, len(assigned_chars))
        ctx.set_output(self.name, {
            "scene_id": scene_id,
            "name": new_scene.name,
            "location": new_scene.location,
            "description": new_scene.description,
            "atmosphere": new_scene.atmosphere,
            "weather": new_scene.weather,
            "time_period": new_scene.time_period,
            "sights": new_scene.sights,
            "sounds": new_scene.sounds,
            "smells": new_scene.smells,
            "mood": new_scene.mood,
            "occupants": assigned_chars,
        })
        return ctx


def _pick_existing_scene(existing_scenes, suggested_chars, novel_chars, ctx) -> any:
    """尝试从已有场景中选一个合适的"""
    # 策略：选一个角色最多的场景，或者跟参与角色关联的场景
    best = None
    best_score = 0
    for sid, scene in existing_scenes.items():
        occupants = ctx.get_occupants(sid)
        score = 0
        if occupants and suggested_chars:
            occupant_names = set(c.name for c in occupants)
            score = sum(1 for n in suggested_chars if n in occupant_names)
        if score > best_score:
            best_score = score
            best = scene
    return best


def _build_scenes_context(scenes: dict) -> str:
    if not scenes:
        return ""
    lines = []
    for sid, scene in list(scenes.items())[:5]:
        lines.append(f"  {scene.name}：{scene.location or ''} {scene.description[:80] if scene.description else ''}")
    return "\n".join(lines)


def _build_chars_context(characters: dict, suggested: list[str]) -> str:
    if not characters:
        return "（尚无角色）"
    lines = []
    for c in characters.values():
        personality = "、".join(getattr(c, "personality", []) or [])
        tag = " ← 建议参与" if c.name in suggested else ""
        lines.append(f"  {c.name}（{getattr(c, 'archetype', '?')}）{personality}{tag}")
    return "\n".join(lines)


def _scene_to_output(scene, novel) -> dict:
    return {
        "scene_id": scene.id,
        "name": scene.name,
        "location": scene.location,
        "description": scene.description,
        "atmosphere": scene.atmosphere,
        "weather": scene.weather,
        "time_period": scene.time_period,
        "sights": scene.sights,
        "sounds": scene.sounds,
        "smells": scene.smells,
        "mood": scene.mood,
    }


def _parse_json_output(text: str) -> dict | None:
    import re
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None
