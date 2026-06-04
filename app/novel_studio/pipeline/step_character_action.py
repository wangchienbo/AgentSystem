"""Step: Character Action — 角色行为决策（顺序冲动评估版）

核心变更（从并行 → 顺序）：
1. 每轮全局评估所有角色的发言冲动（一次 LLM 调用）
2. 冲动最高的角色先行动（独立 LLM 决策）
3. 更新场景事件日志
4. 下一轮（所有角色都有机会行动后结束）

信息隔离：角色 A 不知道角色 B 的内心，只知道 A 能感知到的。
ContextCenter 集成：角色决策结果写入持久化记忆。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseModule, PipelineContext

logger = logging.getLogger(__name__)


class CharacterActionModule(BaseModule):
    """④ 角色行为：顺序冲动评估 + 独立决策"""

    @property
    def name(self) -> str:
        return "character_action"

    @property
    def description(self) -> str:
        return "🎭 角色行为决策（顺序冲动评估）"

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

        scene_context = _build_scene_context_text(scene)
        total_chars = len(occupants)

        # ── 顺序冲动评估循环 ──
        actions: list[dict] = []
        acted_chars: set[str] = set()
        max_rounds = total_chars * 2  # 安全上限

        for round_idx in range(max_rounds):
            remaining = [c for c in occupants if c not in acted_chars]
            if not remaining:
                break  # 所有角色都已行动

            # 1️⃣ 全局冲动评估（一次 LLM 调用评估所有未行动角色）
            impulse_scores = await _evaluate_impulses(
                ctx, remaining, scene_context, scene_id,
                previous_actions=actions,
            )

            # 按冲动得分降序排列
            sorted_chars = sorted(
                impulse_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )

            # 2️⃣ 最高冲动角色行动
            for char_name, _ in sorted_chars:
                if char_name in acted_chars:
                    continue

                agent = ctx.get_agent_by_name(char_name)
                if not agent:
                    acted_chars.add(char_name)
                    continue

                # 获取感知（信息隔离核心）
                perception = ctx.get_perception(agent.character.id)

                # 角色决策（独立 LLM 调用）
                decision = await _decide_character(
                    ctx, agent, char_name, perception, scene_context,
                    previous_actions=actions,
                )
                actions.append(decision)
                acted_chars.add(char_name)

                # 记录到 SceneManager 事件日志
                ctx._scene_manager.apply_action(
                    char_name=char_name,
                    action=decision.get("action", ""),
                    dialogue=decision.get("dialogue", ""),
                    inner=decision.get("inner", ""),
                    scene_id=scene_id,
                )

                # 将记忆写入 ContextCenter（通过 CharacterAgent.add_memory）
                agent.add_memory(
                    content=f"{char_name}{decision.get('action', '沉默观望')}",
                    scene_id=scene_id or "",
                    participants=[c for c in occupants if c != char_name],
                    importance=0.7 if decision.get("dialogue", "沉默") != "沉默" else 0.5,
                    tags=["pipeline_action"],
                )

                # 流式回调
                done_count = len(actions)
                if ctx._character_decided_callback:
                    ctx._character_decided_callback(
                        decision, done_count, total_chars,
                    )

                break  # 本轮只处理一个角色

            if len(acted_chars) >= total_chars:
                break

        logger.info(
            "角色顺序决策完成: %d 个角色, %d 轮",
            len(actions), round_idx + 1,
        )
        ctx.set_output(self.name, {
            "actions": actions,
            "scene_id": scene_id,
            "rounds": round_idx + 1,
        })
        return ctx


# ─── 冲动评估（全局） ───────────────────────────────────


async def _evaluate_impulses(
    ctx: PipelineContext,
    characters: list[str],
    scene_context: str,
    scene_id: str | None,
    previous_actions: list[dict],
) -> dict[str, float]:
    """全局评估未行动角色的发言冲动（一次LLM调用）

    返回 dict {char_name: impulse_score(0-100)}
    """
    if not characters:
        return {}

    # 构建冲动评估 prompt
    char_descs = []
    for char_name in characters:
        agent = ctx.get_agent_by_name(char_name)
        if agent:
            char = agent.character
            personality = "、".join(getattr(char, "personality", []) or [])
            goal = getattr(char, "goal", "") or ""
            speech = getattr(char, "speech_style", "") or ""
            bg = getattr(char, "background", "") or ""
            char_descs.append(
                f"- {char_name}（性格：{personality}，目标：{goal}，"
                f"说话风格：{speech}，背景：{bg[:50]}）"
            )
        else:
            char_descs.append(f"- {char_name}（无详细设定）")

    # 之前的事件摘要
    events_summary = ""
    if previous_actions:
        parts = ["已发生的事件："]
        for a in previous_actions:
            c = a.get("character", "?")
            act = a.get("action", "")
            dia = a.get("dialogue", "")
            if dia and dia != "沉默":
                parts.append(f"  {c} {act}，说「{dia[:60]}」")
            else:
                parts.append(f"  {c} {act}")
        events_summary = "\n".join(parts)

    prompt = f"""你是一个小说角色冲动评估系统。你需要分析当前场景中所有角色的"发言冲动"——谁最应该在这个戏剧性时刻采取行动。

【当前场景】
{scene_context}

【场景中的角色】
{chr(10).join(char_descs)}

{events_summary}

请评估每个角色此刻采取行动的冲动程度（0-100分）。
考虑因素：
- 谁的性格最容易在这种情境下有强烈反应？
- 谁在场景中有最强的目标/动机？
- 谁还没做出反应？
- 戏剧性：谁的行动会最有看点？

输出 JSON 格式，只输出数字评分：
{{"impulses": {{"角色名": 分数, ...}}}}
"""
    system_prompt = "你是一个小说戏剧性评估系统。只需输出 JSON。"

    client = ctx.get_llm_client("novel_writer")
    if not client:
        # 降级：所有角色均等冲动
        return {c: 50.0 for c in characters}

    try:
        text, _ = await client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        text = (text or "").strip()
        # 尝试解析 JSON
        scores = _parse_impulse_json(text, characters)
        logger.debug("冲动评估: %s", scores)
        return scores
    except Exception as e:
        logger.warning("冲动评估失败: %s", e)
        return {c: 50.0 for c in characters}


def _parse_impulse_json(text: str, characters: list[str]) -> dict[str, float]:
    """从 LLM 输出解析冲动分数 JSON"""
    import re
    # 尝试直接解析
    try:
        data = json.loads(text)
        impulses = data.get("impulses", data)
        if isinstance(impulses, dict):
            return {k: float(v) for k, v in impulses.items()
                    if k in characters}
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 尝试从文本中提取 JSON
    m = re.search(r'\{[^}]+\}', text)
    if m:
        try:
            data = json.loads(m.group(0))
            impulses = data.get("impulses", data)
            if isinstance(impulses, dict):
                return {k: float(v) for k, v in impulses.items()
                        if k in characters}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # 降级
    return {c: 50.0 for c in characters}


# ─── 角色决策（独立） ───────────────────────────────────


async def _decide_character(
    ctx, agent, char_name: str, perception, scene_context: str,
    previous_actions: list[dict],
) -> dict:
    """单个角色的决策（独立 LLM 调用）"""
    try:
        prompt = _build_decision_prompt(
            agent, char_name, perception, scene_context,
            previous_actions=previous_actions,
        )
        system_prompt = (
            f"你正在扮演{char_name}。先判断自己知道什么，再行动。不要跳角色。"
            f"保持角色性格绝对一致。"
        )

        client = ctx.get_llm_client("novel_writer")
        if not client:
            return {
                "character": char_name,
                "action": "沉默观望",
                "dialogue": "沉默",
                "inner": "",
            }

        text, _ = await client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.8,
        )
        text = text or ""

        decision = _parse_decision(text, char_name)
        decision["character"] = char_name
        return decision

    except Exception as e:
        logger.warning("角色 %s 决策失败: %s", char_name, e)
        return {
            "character": char_name,
            "action": "沉默观望",
            "dialogue": "沉默",
            "inner": "",
        }


def _build_decision_prompt(
    agent, char_name: str, perception, scene_context: str,
    previous_actions: list[dict],
) -> str:
    """构建角色决策 prompt（只包含角色知道的信息 + 之前事件）"""
    char = agent.character
    parts = [f"你扮演的角色是{char_name}。\n"]

    # 角色面板
    parts.append(
        char.sheet_block() if hasattr(char, "sheet_block")
        else f"性格：{'、'.join(getattr(char, 'personality', []) or [])}"
    )

    # 特殊能力
    if getattr(char, "special_ability", None):
        parts.append(f"\n⚠️ 你的特殊能力：{char.special_ability}")
        parts.append("在决策时，这个能力会改变你能感知到的信息和你的思维方式。")

    # 穿越者提示
    bg = getattr(char, "background", "") or ""
    if "穿越" in bg or "现代" in bg:
        parts.append("\n【重要】你不是这个时代的人。你的灵魂来自四百多年后的现代世界。")
        parts.append("你的思维方式、语言习惯、知识结构与周围人完全不同，你必须时刻伪装。")
        parts.append("你拥有现代人的知识储备——历史进程、科学常识、社会运作逻辑——")
        parts.append("但你绝不能直接暴露这些。所有的建议和行动都要包装成合理解释。")

    # 关系（只提在场角色）
    visible_names = getattr(perception, "visible_chars", []) or []
    if visible_names:
        rels = []
        relationships = getattr(char, "relationships", {}) or {}
        for vn in visible_names:
            if vn in relationships:
                rels.append(f"{vn}（{relationships[vn]}）")
            else:
                rels.append(vn)
        parts.append(f"\n你身边的人：{'、'.join(rels)}")

    # 场景感知
    parts.append(f"\n当前场景：{scene_context}")
    desc = getattr(perception, "scene_description", None) or ""
    if desc:
        parts.append(f"你看到：{desc}")
    sounds = getattr(perception, "sounds", []) or []
    if sounds:
        parts.append(f"你听到：{'；'.join(sounds[:3])}")
    smells = getattr(perception, "smells", []) or []
    if smells:
        parts.append(f"你闻到：{'；'.join(smells[:2])}")
    mood = getattr(perception, "mood", None) or ""
    if mood:
        parts.append(f"氛围：{mood}")

    # 之前发生的事件（角色知道的事）
    if previous_actions:
        parts.append("\n【你刚刚目睹的事】")
        for a in previous_actions:
            c = a.get("character", "?")
            act = a.get("action", "")
            dia = a.get("dialogue", "")
            inner = a.get("inner", "")
            line = f"  {c}{act}"
            if dia and dia != "沉默":
                line += f"，说「{dia[:80]}」"
            if inner and char_name in visible_names:
                # 角色能感知到对方的外在表现，但读心需特殊能力
                pass
            parts.append(line)
        parts.append("")

    # 记忆（角色知道的事）— 从 ContextCenter 获取
    knowing = agent.get_knowing_summary(5)
    parts.append(f"\n{knowing}")

    # 说话风格
    speech_style = getattr(char, "speech_style", None) or ""
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
    """解析角色决策输出（支持多种格式：JSON、标签、纯文本）"""
    result = {
        "character": char_name,
        "action": "",
        "dialogue": "",
        "inner": "",
        "感知": "",
    }

    # 去掉 deepseek 的 标记
    import re
    text_clean = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text_clean = text_clean.strip()

    # ── 尝试 JSON 解析（LLM 可能直接输出 JSON）──
    try:
        # 尝试在大文本中找 JSON 对象
        m = re.search(r'\{[\s\S]*"action"[\s\S]*\}', text_clean)
        if m:
            data = json.loads(m.group(0))
            result["action"] = data.get("action", "") or data.get("行动", "")
            result["dialogue"] = data.get("dialogue", "") or data.get("对话", "")
            result["inner"] = data.get("inner", "") or data.get("内心", "")
            result["感知"] = data.get("perception", "") or data.get("感知", "")
            if result["action"]:
                return result
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # ── 按行解析（支持 感知/行动/对话/内心 前缀）──
    for line in text_clean.split("\n"):
        line = line.strip()
        for prefix in ["感知", "行动", "对话", "内心"]:
            for sep in ["：", ":", "：\n"]:
                pattern = f"{prefix}{sep}"
                idx = line.find(pattern)
                if idx >= 0:
                    val = line[idx + len(pattern):].strip()
                    val = val.strip("：").strip(":").strip("'\"").strip("**")
                    if val:
                        result[prefix] = val
                        break

    # ── 如果逐行解析没找到，尝试正则 ──
    if not result["行动"]:
        patterns = {
            "感知": r"(?:感知|perception)[：:]\s*(.+?)(?=\n(?:行动|对话|内心|action|dialogue|inner|$))",
            "行动": r"(?:行动|action)[：:]\s*(.+?)(?=\n(?:对话|内心|感知|dialogue|inner|perception|$))",
            "对话": r"(?:对话|dialogue)[：:]\s*(.+?)(?=\n(?:内心|感知|行动|inner|perception|action|$))",
            "内心": r"(?:内心|inner)[：:]\s*(.+?)(?=\n(?:感知|行动|对话|perception|action|dialogue|$))",
        }
        for key, pattern in patterns.items():
            if not result.get(key) and key != "character":
                m = re.search(pattern, text_clean, re.DOTALL)
                if m:
                    result[key] = m.group(1).strip()

    # ── 最后的降级策略 ──
    if not result["行动"]:
        lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
        if lines:
            last = lines[-1]
            skips = ["请以", "输出格式", "第一步", "第二步", "感知",
                     "你扮演", "谢谢", "好的", "明白了", "让我", "作为"]
            if not any(s in last for s in skips):
                result["action"] = last[:100]

    return result
