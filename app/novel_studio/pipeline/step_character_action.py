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
            impulse_scores = _evaluate_impulses(
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

                # 角色决策（顺序 LLM 调用）
                decision = _decide_character(
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


def _evaluate_impulses(
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
        text, _ = client.chat(
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


def _decide_character(
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
            f"在决定行动前做一次逻辑校验：你做的事是否能达成你期望的效果？"
            f"如果你要卖东西或提供服务，对方真的会为此付钱吗？"
            f"拒绝不合逻辑的行动方案，选择现实中行得通的做法。"
        )

        client = ctx.get_llm_client("novel_writer")
        if not client:
            return {
                "character": char_name,
                "action": "沉默观望",
                "dialogue": "沉默",
                "inner": "",
            }

        text, _ = client.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.8,
        )
        text = text or ""

        # 记录原始 LLM 输出（用于调试）
        raw_preview = text[:300].replace("\n", "\\n")
        logger.warning("🧠 LLM 原始输出 (%s): %s", char_name, raw_preview)

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
    """解析角色决策输出（支持多行值、JSON、标签、纯文本）"""
    result = {
        "character": char_name,
        "action": "",
        "dialogue": "",
        "inner": "",
        "感知": "",
    }

    import re
    # 去掉常见的思考标签 (thinking/reasoning/thought)
    for tag in ['thinking', 'reasoning', 'thought']:
        text_clean = re.sub(
            rf'<{tag}>.*?</{tag}>', '', text, flags=re.DOTALL
        )
    text_clean = text_clean.strip()
    logger.debug("LLM 原始输出 (%s):\n%s", char_name, text_clean[:500])

    # ── 尝试 JSON 解析 ──
    json_patterns = [
        r'\{[\s\S]*?"(?:action|行动|dialogue|对话|inner|内心|perception|感知)"[\s\S]*?\}',
        r'\{[\s\S]*?["\'](?:action|行动|dialogue|对话)["\'][\s\S]*?\}',
    ]
    for jp in json_patterns:
        try:
            m = re.search(jp, text_clean)
            if m:
                data = json.loads(m.group(0))
                result["action"] = data.get("action", "") or data.get("行动", "")
                result["dialogue"] = data.get("dialogue", "") or data.get("对话", "")
                result["inner"] = data.get("inner", "") or data.get("内心", "")
                result["感知"] = data.get("perception", "") or data.get("感知", "")
                if result["action"] or result["dialogue"] != "沉默" or result["对话"] != "沉默":
                    return result
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # ── 逐行解析（双段模式：先收集行，再关联值）──
    lines = text_clean.split("\n")
    # 第一遍：收集所有前缀行
    field_lines = {}  # prefix → list of (line_idx, val_text)
    for i, line in enumerate(lines):
        stripped = line.strip()
        for prefix in ["感知", "行动", "对话", "内心"]:
            # 寻找前缀（支持 **前缀：** 格式）
            for sep in ["：", ":"]:
                m = re.search(rf'\*?\*?{re.escape(prefix)}\s*{re.escape(sep)}\s*', stripped)
                if m:
                    val = stripped[m.end():].strip()
                    field_lines.setdefault(prefix, []).append((i, val))
                    break

    # 第二遍：处理值（空值的尝试向后取行）
    for prefix in ["感知", "行动", "对话", "内心"]:
        if prefix not in field_lines:
            continue
        # 取最后一次出现（覆盖）
        idx, val = field_lines[prefix][-1]
        if not val:
            # 空值：从下一行开始取，直到遇到另一个前缀或末尾
            next_lines = []
            for j in range(idx + 1, len(lines)):
                next_line = lines[j].strip()
                # 检查是否是新前缀开始
                is_new_field = any(
                    re.match(rf'\*?\*?{re.escape(p)}\s*[：:]', next_line)
                    for p in ["感知", "行动", "对话", "内心"]
                )
                if is_new_field:
                    break
                if next_line and not next_line.startswith("#"):
                    next_lines.append(next_line)
            if next_lines:
                val = "\n".join(next_lines)
        val = _clean_value(val)
        if val:
            result[prefix] = val

    # ── 如果逐行解析没找到，尝试正则 ──
    if not result["行动"]:
        patterns = [
            ("感知", r'(?:感知|perception)\s*[：:]\s*([\s\S]*?)(?=\n(?:行动|对话|内心|action|dialogue|inner|$)|\Z)'),
            ("行动", r'(?:行动|action)\s*[：:]\s*([\s\S]*?)(?=\n(?:对话|内心|感知|dialogue|inner|perception|$)|\Z)'),
            ("对话", r'(?:对话|dialogue)\s*[：:]\s*([\s\S]*?)(?=\n(?:内心|感知|行动|inner|perception|action|$)|\Z)'),
            ("内心", r'(?:内心|inner)\s*[：:]\s*([\s\S]*?)(?=\n(?:感知|行动|对话|perception|action|dialogue|$)|\Z)'),
        ]
        for key, pat in patterns:
            if not result.get(key):
                m = re.search(pat, text_clean, re.DOTALL)
                if m:
                    result[key] = _clean_value(m.group(1).strip())

    # ── 降级策略 ──
    if not result["行动"]:
        valid_lines = [l.strip() for l in lines if l.strip()
                       and not l.strip().startswith("输出格式")
                       and not l.strip().startswith("你扮演")
                       and not l.strip().startswith("请以")]
        if valid_lines:
            last = valid_lines[-1]
            if len(last) > 5:
                result["action"] = last[:120]

    return result


def _clean_value(val: str) -> str:
    """清理字段值中的格式噪音"""
    val = val.strip()
    # 去掉包裹的 ** 和 * (markdown)
    val = re.sub(r'^\*+', '', val)
    val = re.sub(r'\*+$', '', val)
    # 去掉首尾空白分隔符
    for ch in ["：", ":", "'", '"', " ", "　"]:
        val = val.strip(ch)
    # 去掉结尾的 \u200b (零宽空格) 等不可见字符
    val = val.strip()
    # 如果只剩标点符号则置空
    if re.match(r'^[\s，。！？、；：""''【】《》（）\.\,\!\?\:\;]+$', val):
        val = ""
    return val
