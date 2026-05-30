"""Step: Character Action — 角色行为决策（多 Agent 核心）

对场景中的每个角色，独立调用 CharacterAgent 进行决策。
信息隔离：角色 A 不知道角色 B 的内心，只知道 A 能感知到的。
多个角色并行决策（asyncio.gather）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class CharacterActionModule(BaseModule):
    """④ 角色行为：每个角色独立决策"""

    @property
    def name(self) -> str:
        return "character_action"

    @property
    def description(self) -> str:
        return "🎭 角色行为决策"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        scene = ctx.get_output("scene_build")
        if not scene:
            raise ValueError("缺少场景定义，请先执行 scene_build 模块")

        scene_id = scene.get("scene_id")
        occupants = scene.get("occupants", [])

        if not occupants:
            logger.warning("场景 %s 中没有角色", scene_id or "?")
            ctx.set_output(self.name, {"actions": [], "scene_id": scene_id})
            return ctx

        # 确保角色的 Agent 存在
        novel = ctx.novel
        if novel.characters:
            ctx.ensure_agents(novel.characters)

        # 为每个角色构建独立的上下文
        scene_context = _build_scene_context_text(scene)

        # 并行执行所有角色的决策
        tasks = []
        for char_name in occupants:
            agent = ctx.get_agent_by_name(char_name)
            if not agent:
                logger.warning("角色 Agent 不存在: %s", char_name)
                continue

            # 获取感知（信息隔离核心）
            perception = ctx.get_perception(agent.character.id)

            tasks.append(_decide_character(ctx, agent, char_name, perception, scene_context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        actions = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("角色决策异常: %s", r)
                actions.append({
                    "character": "?",
                    "action": "沉默观望",
                    "dialogue": "沉默",
                    "inner": "",
                    "error": str(r),
                })
            else:
                actions.append(r)

        logger.info("角色决策完成: %d 个角色", len(actions))
        ctx.set_output(self.name, {"actions": actions, "scene_id": scene_id})
        return ctx


async def _decide_character(ctx, agent, char_name, perception, scene_context) -> dict:
    """单个角色的决策（独立 LLM 调用）"""
    try:
        # 构造基于当前场景的决策 prompt
        prompt = _build_decision_prompt(agent, char_name, perception, scene_context)
        system_prompt = (
            f"你正在扮演{char_name}。先判断自己知道什么，再行动。不要跳角色。"
            f"保持角色性格绝对一致。"
        )

        client = ctx.get_llm_client("novel_writer")
        if not client:
            return {"character": char_name, "action": "沉默观望", "dialogue": "沉默", "inner": ""}

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.8,
        )
        text = text or ""

        decision = _parse_decision(text, char_name)
        decision["character"] = char_name
        return decision

    except Exception as e:
        logger.warning("角色 %s 决策失败: %s", char_name, e)
        return {"character": char_name, "action": "沉默观望", "dialogue": "沉默", "inner": ""}


def _build_decision_prompt(agent, char_name, perception, scene_context) -> str:
    """构建角色决策 prompt（只包含角色知道的信息）"""
    char = agent.character
    parts = [f"你扮演的角色是{char_name}。\n"]

    # 角色面板
    parts.append(char.sheet_block() if hasattr(char, 'sheet_block') else f"性格：{'、'.join(getattr(char, 'personality', []) or [])}")

    # 特殊能力
    if getattr(char, 'special_ability', None):
        parts.append(f"\n⚠️ 你的特殊能力：{char.special_ability}")
        parts.append("在决策时，这个能力会改变你能感知到的信息和你的思维方式。")

    # 穿越者提示
    bg = getattr(char, 'background', '') or ''
    if "穿越" in bg or "现代" in bg:
        parts.append(f"\n【重要】你不是这个时代的人。你的灵魂来自四百多年后的现代世界。")
        parts.append("你的思维方式、语言习惯、知识结构与周围人完全不同，你必须时刻伪装。")
        parts.append("你拥有现代人的知识储备——历史进程、科学常识、社会运作逻辑——")
        parts.append("但你绝不能直接暴露这些。所有的建议和行动都要包装成合理解释。")

    # 关系（只提在场角色）
    visible_names = getattr(perception, 'visible_chars', []) or []
    if visible_names:
        rels = []
        relationships = getattr(char, 'relationships', {}) or {}
        for vn in visible_names:
            if vn in relationships:
                rels.append(f"{vn}（{relationships[vn]}）")
            else:
                rels.append(vn)
        parts.append(f"\n你身边的人：{'、'.join(rels)}")

    # 场景感知
    parts.append(f"\n当前场景：{scene_context}")
    desc = getattr(perception, 'scene_description', None) or ""
    if desc:
        parts.append(f"你看到：{desc}")
    sounds = getattr(perception, 'sounds', []) or []
    if sounds:
        parts.append(f"你听到：{'；'.join(sounds[:3])}")
    smells = getattr(perception, 'smells', []) or []
    if smells:
        parts.append(f"你闻到：{'；'.join(smells[:2])}")
    mood = getattr(perception, 'mood', None) or ""
    if mood:
        parts.append(f"氛围：{mood}")

    # 记忆（角色知道的事）
    knowing = agent.get_knowing_summary(5)
    parts.append(f"\n{knowing}")

    # 说话风格
    speech_style = getattr(char, 'speech_style', None) or ""
    if speech_style:
        parts.append(f"\n说话风格：{speech_style}")

    # 决策指令
    parts.append(f"""\n请以 {char_name} 的身份做出决策。

输出格式（每行一个字段）：
感知：<你注意到/知道的事>
行动：<你此刻的行动>
对话：<你要说的话，如果没有就写沉默>
内心：<你的内心想法>（可选）""")

    return "\n".join(parts)


def _build_scene_context_text(scene: dict) -> str:
    """把场景定义转为描述文本"""
    parts = []
    if scene.get("name"):
        parts.append(scene["name"])
    if scene.get("location"):
        parts.append(f"位于{scene['location']}")
    if scene.get("atmosphere"):
        parts.append(f"氛围{scene['atmosphere']}")
    if scene.get("weather"):
        parts.append(f"天气{scene['weather']}")
    if scene.get("time_period"):
        parts.append(f"时间{scene['time_period']}")
    if scene.get("description"):
        parts.append(scene["description"])
    return "，".join(parts)


def _parse_decision(text: str, char_name: str) -> dict[str, str]:
    """解析角色决策输出（支持多种格式）"""
    result = {
        "character": char_name,
        "action": "",
        "dialogue": "",
        "inner": "",
        "感知": "",
    }

    # ── 逐行解析 ──
    for line in text.split("\n"):
        line = line.strip()
        for prefix in ["感知", "行动", "对话", "内心"]:
            # 支持 感知：内容 / 感知:内容 / **感知**：内容 / 感知:内容
            for sep in ["：", ":", "：\n"]:
                idx = line.find(f"{prefix}{sep}")
                if idx >= 0:
                    val = line[idx + len(prefix) + len(sep):].strip()
                    val = val.strip("：").strip(":").strip('"\'"').strip("**")
                    if val:
                        result[prefix] = val
                        break

    # ── 如果逐行解析没找到，尝试正则（适应更混乱的格式） ──
    if not result["行动"]:
        import re
        patterns = {
            "感知": r"(?:感知|perception)[：:]\s*(.+?)(?=\n(?:行动|对话|内心|$))",
            "行动": r"(?:行动|action)[：:]\s*(.+?)(?=\n(?:对话|内心|感知|$))",
            "对话": r"(?:对话|dialogue)[：:]\s*(.+?)(?=\n(?:内心|感知|行动|$))",
            "内心": r"(?:内心|inner)[：:]\s*(.+?)(?=\n(?:感知|行动|对话|$))",
        }
        for key, pattern in patterns.items():
            if not result.get(key) and key != "character":
                m = re.search(pattern, text, re.DOTALL)
                if m:
                    result[key] = m.group(1).strip()

    # ── 最后的降级策略 ──
    if not result["行动"]:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            # 取最后一行非空作为行动
            last = lines[-1]
            # 跳过明显不是行动的句子
            skips = ["请以", "输出格式", "第一步", "第二步", "感知", "你扮演"]
            if not any(s in last for s in skips):
                result["行动"] = last[:100]

    return result
