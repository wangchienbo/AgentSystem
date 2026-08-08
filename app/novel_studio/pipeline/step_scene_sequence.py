"""Step: Scene Sequence — 场景序列生成（重构版）

逐个生成场景，每次把前面所有场景带入。
输出：time, location, characters, event, environment_details

合并了 scene_build 的逻辑，不再单独细化环境。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext, build_novel_context

logger = logging.getLogger(__name__)


class SceneSequenceModule(BaseModule):
    """② 场景序列：逐个生成场景"""

    @property
    def name(self) -> str:
        return "scene_sequence"

    @property
    def description(self) -> str:
        return "🎬 场景序列（逐个生成）"

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
                    "time": "",
                    "location": "",
                    "characters": plan.get("suggested_chars", []),
                    "event": plan.get("summary", ""),
                    "environment_details": "",
                }],
                "chapter_number": chapter_number,
            })
            return ctx

        # 逐个生成场景
        scenes = await self._generate_scenes_sequentially(
            ctx, novel, plan, chapter_number, prev_chapter_ending, chars_text
        )

        logger.info("场景序列生成: %d 个场景", len(scenes))

        ctx.set_output(self.name, {
            "scenes": scenes,
            "chapter_number": chapter_number,
        })
        return ctx

    async def _generate_scenes_sequentially(
        self,
        ctx: PipelineContext,
        novel,
        plan: dict,
        chapter_number: int,
        prev_chapter_ending: str,
        chars_text: str,
    ) -> list[dict]:
        """逐个生成场景，每次把前面所有场景带入"""
        scenes = []
        max_scenes = 4  # 最多生成 4 个场景

        for scene_idx in range(max_scenes):
            # 构建前面所有场景的上下文
            prev_scenes_context = self._build_prev_scenes_context(scenes)

            # 生成下一个场景
            scene = await self._generate_one_scene(
                ctx, novel, plan, chapter_number,
                prev_chapter_ending, prev_scenes_context,
                chars_text, scene_idx
            )

            if not scene:
                break

            scenes.append(scene)

            # 检查是否应该停止（根据 chapter_plan 的关键事件是否都已覆盖）
            if self._should_stop(scenes, plan):
                break

        return scenes

    async def _generate_one_scene(
        self,
        ctx: PipelineContext,
        novel,
        plan: dict,
        chapter_number: int,
        prev_chapter_ending: str,
        prev_scenes_context: str,
        chars_text: str,
        scene_idx: int,
    ) -> dict | None:
        """生成一个场景"""
        client = ctx.get_llm_client("novel_writer")
        if not client:
            return None

        prompt = self._build_prompt(
            novel, plan, chapter_number,
            prev_chapter_ending, prev_scenes_context,
            chars_text, scene_idx
        )

        system_prompt = (
            f"你是一位小说场景设计师。为小说《{novel.title}》的第{chapter_number}章设计一个场景。"
            f"只输出 JSON，不要其他文字。"
        )

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.7,
        )
        text = text or ""

        scene = self._parse_scene(text)
        return scene

    def _build_prev_scenes_context(self, scenes: list[dict]) -> str:
        """构建前面所有场景的上下文"""
        if not scenes:
            return "（这是本章第一个场景）"

        lines = ["前面已生成的场景："]
        for i, s in enumerate(scenes, 1):
            lines.append(f"\n场景{i}：")
            lines.append(f"  时间：{s.get('time', '')}")
            lines.append(f"  地点：{s.get('location', '')}")
            lines.append(f"  人物：{', '.join(s.get('characters', []))}")
            lines.append(f"  事件：{s.get('event', '')}")

        return "\n".join(lines)

    def _build_prompt(
        self,
        novel,
        plan: dict,
        chapter_number: int,
        prev_chapter_ending: str,
        prev_scenes_context: str,
        chars_text: str,
        scene_idx: int,
    ) -> str:
        """构建场景生成 prompt"""
        # 关键事件
        key_events = plan.get("key_events", [])
        events_text = "\n".join(f"  {i+1}. {ev}" for i, ev in enumerate(key_events))

        # 本章概要
        summary = plan.get("summary", "")

        # 第1章特殊约束
        first_chapter_rules = ""
        if chapter_number == 1:
            first_chapter_rules = """

## 【第1章特殊约束——必须有过渡】

第1章的核心任务是让读者**感受**这个世界和角色，不是推进剧情。

### 必须包含的过渡场景
- **醒来/适应**：主角穿越后必须有"醒来→观察→困惑→适应"的过程（至少1个场景）
- **环境探索**：主角观察周围环境，通过细节感受时代背景（至少1个场景）
- **日常挣扎**：展示角色在这个世界的基本生存状态（至少1个场景）

### 禁止的事件类型
- 生死决斗、权力夺位、大规模冲突、核心矛盾爆发
- 主角立即获得能力/系统/金手指
- 主角立即解决核心问题（找水、找食物、找到安全处所）

### 场景节奏
- 每个场景应该**慢**，有足够的环境描写和心理活动
- 不要急于推进剧情，让读者感受这个世界的氛围
"""

        return f"""为小说《{novel.title}》的第{chapter_number}章生成一个场景。

## 本章规划
标题：{plan.get("title", "")}
概要：{summary}
关键事件：
{events_text}

## 上一章结尾（必须从此处接续）
{prev_chapter_ending}

## {prev_scenes_context}

## 角色
{chars_text}

## 场景生成要求

请生成一个场景，**必须包含以下5个字段**：

1. **time**：具体时间（如"正午"、"黄昏"、"深夜"）
2. **location**：具体地点（如"破庙外的干涸河滩"）
3. **characters**：参与的角色名数组（如["陈实", "铁柱"]）
4. **event**：这个场景中发生的具体事件（50-100字，描述**发生了什么**，人物做了什么）
5. **environment_details**：场景的环境细节（50-100字，描述感官细节： sights, sounds, smells, atmosphere）

### 场景生成原则

- **逻辑顺序**：新场景必须从前面场景的结尾自然接续（时间连续、地点连续）
- **事件推进**：每个场景必须有具体事件，不能只是环境描写
- **人物行动**：事件中的人物必须有具体行动和互动
- **避免重复**：如果前面场景已经发生过类似的事件，新场景应该推进到下一个阶段
- **节奏控制**：第1章必须有"过渡"场景（醒来→观察→适应），不要急于推进剧情
{first_chapter_rules}

### 示例输出

```json
{{
  "time": "正午",
  "location": "破庙外的干涸河滩",
  "characters": ["陈实", "铁柱", "老孙头"],
  "event": "三人发现河滩水洼干涸，老孙头怀疑铁柱偷喝了水，铁柱威胁要动手，陈实拦住",
  "environment_details": "河床裸露，土地干裂，空气中弥漫着干土味，几株枯死的庄稼秆在惨白的阳光下无力地耷拉着"
}}
```

**重要：必须输出上述 JSON 格式，包含 time、location、characters、event、environment_details 五个字段。**"""

    def _parse_scene(self, text: str) -> dict | None:
        """解析场景 JSON"""
        import re

        # 尝试提取 JSON
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

        # 如果解析失败，用 LLM 生成的文本再试
        try:
            scene = json.loads(text)
            if isinstance(scene, dict):
                return scene
        except (json.JSONDecodeError, ValueError):
            pass

        logger.warning("场景 JSON 解析失败")
        return None

    def _should_stop(self, scenes: list[dict], plan: dict) -> bool:
        """检查是否应该停止生成场景"""
        # 检查关键事件是否都已覆盖
        key_events = plan.get("key_events", [])
        if not key_events:
            return False

        # 简单检查：如果场景数量 >= 关键事件数量，停止
        return len(scenes) >= len(key_events)

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
        """构建角色上下文"""
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


# ─── 单场景生成函数（供 scene_loop 调用） ────────────────────


async def generate_one_scene(
    ctx: PipelineContext,
    novel,
    plan: dict[str, Any],
    current_prediction: dict[str, Any],
    scene_index: int,
    prev_scenes: list[dict[str, Any]],
    prev_scene_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """基于当前预测状态生成一个场景（兼容旧接口）

    这个函数是为了兼容 scene_loop 的调用，内部调用 SceneSequenceModule 的逻辑
    """
    module = SceneSequenceModule()

    # 构建前面场景的上下文
    prev_scenes_context = module._build_prev_scenes_context(prev_scenes)

    # 获取上一章结尾
    prev_chapter_ending = module._get_prev_chapter_ending(novel)

    # 获取角色上下文
    chars_text = module._build_chars_context(novel.characters)

    # 生成场景
    scene = await module._generate_one_scene(
        ctx, novel, plan, plan.get("chapter_number", 1),
        prev_chapter_ending, prev_scenes_context,
        chars_text, scene_index
    )

    if not scene:
        # 降级
        return {
            "time": "",
            "location": "",
            "characters": plan.get("suggested_chars", []),
            "event": plan.get("summary", ""),
            "environment_details": "",
        }

    return scene
