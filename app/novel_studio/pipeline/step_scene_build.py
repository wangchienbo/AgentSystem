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

from .base import BaseModule, PipelineContext

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
            for field in ["sights", "sounds", "smells", "rules"]:
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
                "mood": getattr(new_scene, "mood", ""),
                "participants": assigned,
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

        prompt = f"""请为小说《{novel.title}》的第{chapter_number}章细化以下场景，补充感官细节。

## 场景序列
{scenes_text}

## 角色
{chars_text}

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
    "purpose": "叙事目的",
    "scene_type": "场景类型",
    "transition_from_prev": "过渡方式"
  }}
]

注意：
- sights/sounds/smells 要是具体的感官描写，不能是抽象概念
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
                              "time_period", "sights", "sounds", "smells", "mood", "rules"]:
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
