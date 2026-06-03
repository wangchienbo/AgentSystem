"""ModelInputBuilder — 上下文视图层 (Path B)

职责：
  - 在 ContextCenter 的 append-only 存储之上建立视图层
  - 控制显示给 LLM 的窗口轮数 (window_turns)
  - 超出阈值时自动压缩早期对话生成摘要
  - 提供 expand_context 接口供 LLM 请求更多历史
  - 纯读取，不修改原始记录

与 ContextCenter 的关系：
  ContextCenter = 存储层 (append-only, disk persistence)
  ModelInputBuilder = 视图层 (窗口 + 压缩, 纯计算)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.models.context import SessionContextRecord
from app.services.context_center import ContextCenter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class ModelInputView:
    """构建完成的模型输入视图，包含压缩元数据。"""
    # 最终给 LLM 的上下文文本
    context_text: str = ""
    # 总对话轮数（一轮 = user + assistant 一对）
    total_turns: int = 0
    # 被压缩的早期轮数
    compressed_turns: int = 0
    # 保留的原始轮数
    raw_turns: int = 0
    # 压缩后的摘要文本（仅在 compressed=True 时有效）
    summary_text: str = ""
    # 是否发生了压缩
    compressed: bool = False
    # 是否可以调用 expand_context 扩展
    can_expand: bool = True
    # LLM 可见的 expand 指令
    expand_hint: str = ""
    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_TURNS = 10       # 默认保留最近 N 轮原始对话
DEFAULT_MAX_TURNS = 30          # 超过此阈值开始压缩
MAX_RECORDS_PER_SESSION = 500   # 每个会话最大记录数 (GC 阈值)


# ---------------------------------------------------------------------------
# 核心服务
# ---------------------------------------------------------------------------

class ModelInputBuilder:
    """在 ContextCenter 上构建 LLM 模型输入视图。

    用法::

        builder = ModelInputBuilder(context_center)
        view = builder.build(session_id="...", window_turns=10)
        print(view.context_text)

        # LLM 需要更多上下文时:
        expanded = builder.expand(session_id="...", expand_turns=5)
    """

    def __init__(
        self,
        context_center: ContextCenter,
        window_turns: int = DEFAULT_WINDOW_TURNS,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self._cc = context_center
        self._default_window = window_turns
        self._default_max = max_turns

    # ── 主入口 ──────────────────────────────────────────────────────────

    def build(
        self,
        session_id: str,
        *,
        window_turns: int | None = None,
        max_turns: int | None = None,
        include_kinds: set[str] | None = None,
    ) -> ModelInputView:
        """构建模型输入视图。

        Parameters
        ----------
        session_id : str
            会话 ID
        window_turns : int, optional
            保留的最近原始轮数，默认 self._default_window
        max_turns : int, optional
            压缩触发的阈值轮数，默认 self._default_max
        include_kinds : set[str], optional
            包含的记录类型，默认 {"message"}

        Returns
        -------
        ModelInputView
        """
        window_turns = window_turns or self._default_window
        max_turns = max_turns or self._default_max
        include_kinds = include_kinds or {"message"}

        # 1. 从 ContextCenter 读取所有记录
        raw_window = self._cc.read_context(session_id, limit=MAX_RECORDS_PER_SESSION)
        all_records = raw_window.records

        if not all_records:
            return ModelInputView(
                context_text="新会话，无历史上下文",
                total_turns=0,
                compressed=False,
                can_expand=False,
                metadata={"session_id": session_id, "record_count": 0},
            )

        # 2. 筛选对话级别记录并计算轮数
        message_records = [r for r in all_records if r.kind in include_kinds]
        total_records = len(message_records)

        # 计算对话轮数 user+assistant 视为一轮
        # 如果最后一条是 user 消息，则仍在进行中的轮不算完整
        pairs, remainder = divmod(total_records, 2)
        total_turns = pairs + (1 if remainder > 0 else 0)

        # 3. 检查是否需要压缩
        if total_turns <= window_turns or total_turns <= max_turns:
            # 不压缩 — 直接格式化全部记录
            context_text = self._format_records(message_records)
            return ModelInputView(
                context_text=context_text,
                total_turns=total_turns,
                compressed_turns=0,
                raw_turns=total_turns,
                compressed=False,
                can_expand=False,
                expand_hint="",
                metadata={
                    "session_id": session_id,
                    "record_count": total_records,
                    "total_turns": total_turns,
                },
            )

        # 4. 需要压缩：早期对话压缩为摘要，保留最近 N 轮原始
        compress_turns = total_turns - window_turns
        compress_records = compress_turns * 2  # 压缩的 record 数

        old_records = message_records[:compress_records]
        recent_records = message_records[compress_records:]

        # 生成或检索摘要
        summary = self._get_or_build_summary(session_id, old_records)

        # 构建压缩后的上下文
        context_text = self._build_compressed_context(
            summary=summary,
            recent_records=recent_records,
            window_turns=window_turns,
            can_expand=True,
        )

        expand_hint = (
            "💡 如需查看更多历史上下文，可调用 expand_context 工具获取更多早期对话。"
        )

        return ModelInputView(
            context_text=context_text,
            total_turns=total_turns,
            compressed_turns=compress_turns,
            raw_turns=window_turns,
            summary_text=summary,
            compressed=True,
            can_expand=True,
            expand_hint=expand_hint,
            metadata={
                "session_id": session_id,
                "record_count": total_records,
                "total_turns": total_turns,
                "compressed_turns": compress_turns,
                "raw_turns": window_turns,
            },
        )

    # ── 扩展接口 ────────────────────────────────────────────────────────

    def expand(
        self,
        session_id: str,
        *,
        expand_turns: int = 5,
        include_kinds: set[str] | None = None,
    ) -> ModelInputView:
        """展开更多上下文给 LLM 查看。

        在已完成压缩的会话上，额外返回更多原始记录。
        返回的 view 中包含最近 window_turns + expand_turns 轮的原始记录。

        Parameters
        ----------
        session_id : str
            会话 ID
        expand_turns : int
            额外展开的轮数
        include_kinds : set[str], optional
        """
        include_kinds = include_kinds or {"message"}
        raw_window = self._cc.read_context(session_id, limit=MAX_RECORDS_PER_SESSION)
        all_records = raw_window.records
        message_records = [r for r in all_records if r.kind in include_kinds]
        total_records = len(message_records)

        # 展开后的窗口 = 原始 window_turns + expand_turns
        expanded_window_records = expand_turns * 2 + self._default_window * 2
        expanded_records = message_records[-expanded_window_records:]

        # 检查是否还有更早的记录
        remaining = len(message_records) - len(expanded_records)
        can_expand_more = remaining > 0

        context_text = self._format_records_with_summary(
            expanded_records,
            total_records,
            remaining,
        )

        return ModelInputView(
            context_text=context_text,
            total_turns=(total_records + 1) // 2,
            compressed_turns=max(0, (total_records - len(expanded_records) + 1) // 2),
            raw_turns=(len(expanded_records) + 1) // 2,
            compressed=remaining > 0,
            can_expand=can_expand_more,
            expand_hint="💡 如仍需查看更多历史，可继续调用 expand_context 工具。"
            if can_expand_more
            else "",
            metadata={
                "session_id": session_id,
                "record_count": total_records,
                "expanded_records": len(expanded_records),
                "can_expand_more": can_expand_more,
            },
        )

    # ── GC ──────────────────────────────────────────────────────────────

    def gc_session(
        self,
        session_id: str,
        max_records: int = MAX_RECORDS_PER_SESSION,
    ) -> dict[str, int]:
        """对指定会话执行 GC，清理早期记录。

        只清理 "message" 类型的记录（对话内容），
        保留 "summary", "system_note", "tool_result" 等记录。

        Returns
        -------
        dict 包含 {removed, kept}
        """
        raw = self._cc.read_context(session_id, limit=MAX_RECORDS_PER_SESSION)
        records = raw.records

        if len(records) <= max_records:
            return {"removed": 0, "kept": len(records)}

        # 计算需要移除的早期 message 记录
        surplus = len(records) - max_records
        message_indices = [
            i for i, r in enumerate(records) if r.kind == "message"
        ]

        # 如果 message 记录数不超过 max_records 的一半，不清理
        if len(message_indices) <= max_records // 2:
            return {"removed": 0, "kept": len(records)}

        remove_count = min(surplus, len(message_indices) // 2)

        if remove_count <= 0:
            return {"removed": 0, "kept": len(records)}

        # 移除最早的部分 message 记录
        remove_indices = set(message_indices[:remove_count])
        kept = [r for i, r in enumerate(records) if i not in remove_indices]

        # 更新内存记录
        self._cc._records[session_id] = kept

        logger.info(
            "ModelInputBuilder GC: session=%s removed=%d kept=%d",
            session_id, remove_count, len(kept),
        )
        return {"removed": remove_count, "kept": len(kept)}

    # ── 内部方法 ────────────────────────────────────────────────────────

    def _format_records(self, records: list[SessionContextRecord]) -> str:
        """格式化记录列表为 LLM 可读的文本。"""
        lines = ["【对话历史】"]
        for r in records:
            content = (r.content or "").strip()
            if not content:
                continue
            role_label = "用户" if r.role == "user" else "助手" if r.role == "assistant" else r.role
            lines.append(f"  {role_label}: {content}")
        return "\n".join(lines)

    def _format_records_with_summary(
        self,
        records: list[SessionContextRecord],
        total_records: int,
        remaining: int,
    ) -> str:
        """格式化记录，包含摘要说明。"""
        parts = []
        if remaining > 0:
            parts.append(
                f"【上下文摘要】以下为最近 {len(records)} 条记录。"
                f"还有 {remaining} 条更早的记录已省略。"
            )
        else:
            parts.append("【完整对话历史】")
        parts.append(self._format_records(records))
        return "\n".join(parts)

    def _get_or_build_summary(
        self,
        session_id: str,
        old_records: list[SessionContextRecord],
    ) -> str:
        """获取已有摘要或生成临时摘要。"""
        # 优先读取已持久化的 summary 事件
        try:
            summary_events = self._cc.read_summary_events(session_id, limit=5)
            if summary_events:
                # 取最新的 summary
                latest = summary_events[-1]
                summary_text = latest.message.strip()
                if summary_text and len(summary_text) > 20:
                    return summary_text
        except Exception:
            pass

        # 没有可用摘要，就地生成临时摘要
        return self._build_quick_summary(old_records)

    def _build_quick_summary(self, records: list[SessionContextRecord]) -> str:
        """从记录列表快速生成文本摘要（不调用 LLM）。"""
        topics = []
        for r in records[-20:]:  # 只看最近的一部分
            content = (r.content or "").strip()
            if not content:
                continue
            truncated = content[:100].replace("\n", " ")
            role = "用户" if r.role == "user" else "助手"
            topics.append(f"[{role}] {truncated}{'...' if len(content) > 100 else ''}")

        if not topics:
            return "（早期对话摘要：无可用的对话内容）"

        summary = "早期对话摘要（以下为关键对话要点）：\n"
        summary += "\n".join(topics)
        summary += f"\n（共 {len(records)} 条早期记录，以上为最近部分摘要）"
        return summary

    def _build_compressed_context(
        self,
        summary: str,
        recent_records: list[SessionContextRecord],
        window_turns: int,
        can_expand: bool,
    ) -> str:
        """构建压缩后的上下文文本。"""
        lines = [
            "═══════════════════════════════════════",
            "【早期对话摘要】（以下为已压缩的早期历史）",
            summary,
            "",
            f"【最近对话 - 最近 {window_turns} 轮】（完整记录）",
            "═══════════════════════════════════════",
        ]
        for r in recent_records:
            content = (r.content or "").strip()
            if not content:
                continue
            role_label = "用户" if r.role == "user" else "助手" if r.role == "assistant" else r.role
            lines.append(f"  {role_label}: {content}")

        if can_expand:
            lines.append("")
            lines.append("💡 如需查看更多历史上下文，可调用 expand_context 工具。")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# expand_context 工具定义
# ---------------------------------------------------------------------------

EXPAND_CONTEXT_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "expand_context",
        "description": "展开更多历史上下文。当对话早期内容被压缩后，调用此工具可以获取更多原始对话记录。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "当前会话 ID",
                },
                "expand_turns": {
                    "type": "integer",
                    "description": "额外展开的轮数（默认5）",
                    "default": 5,
                },
            },
            "required": ["session_id"],
        },
    },
}
