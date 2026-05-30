"""Novel Studio — 上下文构建器

统一管理 Novel Studio 的会话注册与上下文构建，
消除 api.py 中各端点手工拼接上下文的重复代码。

功能：
- 小说会话注册（ContextCenter SessionNode + 上下文注入）
- 角色对话子会话管理（每个角色对话独立上下文窗口）
- 集中式小说系统 prompt 构建（取代各端点的硬编码 ctx）
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.models.context import SessionContextRecord, SessionNode

logger = logging.getLogger(__name__)

# ─── 会话命名空间 ──────────────────────────────────────────────────

SESSION_USER = "novel_studio"
SESSION_CHANNEL = "asset:novel_studio:v1"

NOVEL_SESSION_PREFIX = "novel:"
DIALOGUE_SESSION_PREFIX = "novel:dialogue:"


def novel_session_id(novel_id: str) -> str:
    """小说主会话 ID"""
    return f"{NOVEL_SESSION_PREFIX}{novel_id}"


def dialogue_session_id(novel_id: str, char1: str, char2: str) -> str:
    """两个角色之间的对话子会话 ID"""
    names = sorted([char1, char2])
    return f"{DIALOGUE_SESSION_PREFIX}{novel_id}:{names[0]}:{names[1]}"


# ─── 会话注册 ──────────────────────────────────────────────────────


def get_or_create_novel_session(
    novel_id: str,
    context_center: Any,
    user_id: str = SESSION_USER,
) -> str:
    """获取或创建小说主会话（如果 context_center 不存在则静默跳过）"""
    if not context_center:
        return novel_session_id(novel_id)

    sid = novel_session_id(novel_id)
    try:
        existing = context_center.get_session_node(sid)
        if existing is not None:
            return sid
    except Exception:
        pass

    try:
        node = SessionNode(
            session_id=sid,
            user_id=user_id,
            channel=SESSION_CHANNEL,
            kind="root",
            actor="app",
            topic_key=f"novel:{novel_id}",
            root_session_id=sid,
        )
        context_center.register_session_node(node)
        logger.debug("Registered novel session: %s", sid)
    except Exception as e:
        logger.warning("Failed to register novel session %s: %s", sid, e)

    return sid


def get_or_create_dialogue_session(
    novel_id: str,
    char1: str,
    char2: str,
    context_center: Any,
    user_id: str = SESSION_USER,
) -> str:
    """获取或创建角色对话子会话"""
    if not context_center:
        return dialogue_session_id(novel_id, char1, char2)

    sid = dialogue_session_id(novel_id, char1, char2)
    parent_sid = novel_session_id(novel_id)

    try:
        existing = context_center.get_session_node(sid)
        if existing is not None:
            return sid
    except Exception:
        pass

    try:
        node = SessionNode(
            session_id=sid,
            user_id=user_id,
            channel=SESSION_CHANNEL,
            kind="child",
            actor="app",
            topic_key=f"dialogue:{novel_id}",
            root_session_id=parent_sid,
            parent_session_id=parent_sid,
        )
        context_center.register_session_node(node)
        logger.debug("Registered dialogue session: %s (parent=%s)", sid, parent_sid)
    except Exception as e:
        logger.warning("Failed to register dialogue session %s: %s", sid, e)

    return sid


# ─── 上下文注入 ────────────────────────────────────────────────────


def log_context_record(
    session_id: str,
    content: str,
    context_center: Any,
    role: str = "system",
    kind: str = "system_note",
) -> None:
    """向 ContextCenter 写入一条上下文记录（静默跳过 None）"""
    if not context_center:
        return
    try:
        record = SessionContextRecord(
            session_id=session_id,
            kind=kind,
            role=role,
            content=content,
        )
        context_center.append_context(record)
    except Exception as e:
        logger.debug("Failed to write context record: %s", e)


def log_novel_context_records(
    novel,
    context_center: Any,
    session_id: str | None = None,
) -> None:
    """将整本小说的结构化数据写入 ContextCenter

    每次写入均以单独记录写入，便于后续按 kind/role 检索。
    """
    if not context_center:
        return

    sid = session_id or novel_session_id(novel.id)

    log_context_record(sid, f"# {novel.title}", context_center)
    if novel.genre:
        log_context_record(sid, f"类型：{novel.genre}", context_center)
    log_context_record(sid, f"状态：{novel.status}", context_center)

    # 大纲
    if novel.outline and novel.outline.summary:
        log_context_record(
            sid,
            f"大纲摘要：{novel.outline.summary}",
            context_center,
        )
    if novel.outline and novel.outline.chapters:
        chapters_plan = [
            f"  第{c.number}章 {c.title}" for c in novel.outline.chapters
        ]
        log_context_record(
            sid,
            "章节规划：\n" + "\n".join(chapters_plan),
            context_center,
        )

    # 角色
    if novel.characters:
        char_lines = ["角色："]
        for c in novel.characters.values():
            char_lines.append(
                f"  - {c.name}({c.archetype.value}): {'、'.join(c.personality)}"
            )
            if c.goal:
                char_lines.append(f"    目标：{c.goal}")
        log_context_record(sid, "\n".join(char_lines), context_center)

    # 世界观
    if novel.world:
        log_context_record(
            sid,
            f"世界观：{novel.world.name} - {novel.world.overview}",
            context_center,
        )
        if novel.world.rules:
            for r in novel.world.rules:
                log_context_record(sid, f"  - {r}", context_center)

    # 已完成章节（最近3章）
    if novel.chapters:
        chapter_lines = ["已完成章节："]
        for ch in novel.chapters[-3:]:
            chapter_lines.append(
                f"  第{ch.number}章 {ch.title}（{len(ch.content)}字）"
            )
        log_context_record(sid, "\n".join(chapter_lines), context_center)

    logger.debug("Novel context records written for session %s (%d chars)", sid, len(str(novel)))


# ─── 系统 Prompt 构建 ──────────────────────────────────────────────


def build_novel_system_prompt(novel) -> str:
    """从 Novel 对象集中构建系统 prompt（替代 api.py 中的手写 ctx 块）

    所有端点自此统一走此函数。
    """
    ctx_parts = [f"# {novel.title}"]
    if novel.genre:
        ctx_parts.append(f"类型：{novel.genre}")
    ctx_parts.append(f"状态：{novel.status}")
    if novel.outline and novel.outline.summary:
        ctx_parts.append(f"大纲摘要：{novel.outline.summary}")
    if novel.outline and novel.outline.chapters:
        chapters_plan = [
            f"  第{c.number}章 {c.title}" for c in novel.outline.chapters
        ]
        ctx_parts.append("大纲章节规划（未写，仅规划）：\n" + "\n".join(chapters_plan))
    if novel.characters:
        ctx_parts.append("角色：")
        for c in novel.characters.values():
            ctx_parts.append(
                f"  - {c.name}({c.archetype.value}): {'、'.join(c.personality)}"
            )
            if c.goal:
                ctx_parts.append(f"    目标：{c.goal}")
    if novel.world:
        ctx_parts.append(f"世界观：{novel.world.name} - {novel.world.overview}")
    if novel.chapters:
        ctx_parts.append("已完成章节（共{}章）：".format(len(novel.chapters)))
        # Show last 10 chapters with detail, and all chapter titles compactly
        if len(novel.chapters) > 10:
            ctx_parts.append("  全部章节列表：")
            for ch in novel.chapters:
                ctx_parts.append(
                    f"    第{ch.number}章 {ch.title}"
                )
            ctx_parts.append("")
        ctx_parts.append("  最近章节（第{}-{}章）：".format(
            max(1, len(novel.chapters) - 9), len(novel.chapters)))
        for ch in novel.chapters[-10:]:
            ctx_parts.append(
                f"    第{ch.number}章 {ch.title}（{len(ch.content)}字）"
            )

    full_context = "\n".join(ctx_parts)
    return f"""你是一位专业的小说创作助手，正在帮助用户创作小说《{novel.title}》。
小说ID（novel_id = "{novel.id}"）—— 使用 call_asset_method 时，params 中必须传入此 novel_id。

当前上下文：
{full_context}

你的身份：小说工作室资产（asset:novel_studio:v1）
你可以通过 call_asset_method 工具调用自己的能力来操作小说数据（添加角色、保存大纲、更新场景等）。

你的能力：
1. 根据用户指令生成大纲、角色、世界观、章节等内容
2. 回答关于故事的问题，提供创作建议
3. 帮助用户规划剧情、分析角色、完善世界观
4. 直接生成小说章节正文（当用户要求写时）

规则：
- 保持角色性格和情节逻辑一致
- 语言自然流畅
- 直接回答问题，不要返回 JSON 格式
- 如果用户要求生成章节大纲，输出大纲内容即可，不要自动保存为章节
- 如果用户要求生成章节正文，直接写出章节正文内容，**只有当用户明确说"保存"或"写入"时，才使用 write_chapter 工具保存**
- 交互层不要自动调用 write_chapter/update_chapter 来保存每次对话输出；大多数对话是讨论、修改意见、大纲，不是最终章节
- 如果用户要求生成大纲，按"梗概 → 三幕 → 章节规划"的顺序输出
- 需要查询数据时，使用 call_asset_method 工具调用对应方法
- 注意区分「大纲规划」（未写）和「已完成章节」（已写），不要混淆
- 这是一部长篇连载小说，目标至少 300 章。写章节时保持节奏感，每章 1500-3000 字
- 需要了解自己的系统架构、数据模型、代码位置或完整能力清单时，调用 `get_system_info` 方法动态获取，不要凭空猜测
---"""


