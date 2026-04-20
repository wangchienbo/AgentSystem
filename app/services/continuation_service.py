"""ContinuationService — 统一的多轮交互状态管理。

替代 LightBrainInterpreter 中分散的 _pending_runtime_asset_clarifications 等私有字典，
提供可持久化、可查询、可 TTL 清理的统一 continuation 存储。
"""
from __future__ import annotations

import threading
from typing import Any

from app.models.continuation import (
    ContinuationKind,
    ContinuationState,
    ContinuationResult,
    ContinuationResumeRequest,
    MissingParamSpec,
)
from app.models.chat import InterpretedCommand


class ContinuationService:
    """管理所有 intent 的 continuation 状态，支持内存存储（后续可扩展持久化）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # continuation_id (通常即 session_id) -> ContinuationState
        self._states: dict[str, ContinuationState] = {}

    def create_missing_parameter_continuation(
        self,
        session_id: str,
        original_intent: str,
        original_params: dict[str, Any],
        missing_params: list[MissingParamSpec],
    ) -> ContinuationState:
        """创建缺参数的 continuation。"""
        with self._lock:
            state = ContinuationState(
                continuation_id=session_id,
                kind=ContinuationKind.MISSING_PARAMETER,
                original_intent=original_intent,
                original_params=original_params,
                missing_params=missing_params,
                status="pending",
            )
            self._states[session_id] = state
            return state

    def create_confirmation_continuation(
        self,
        session_id: str,
        original_intent: str,
        original_params: dict[str, Any],
        confirmation_prompt: str,
        confirmation_action_id: str,
    ) -> ContinuationState:
        """创建需要确认的 continuation。"""
        with self._lock:
            state = ContinuationState(
                continuation_id=session_id,
                kind=ContinuationKind.CONFIRMATION,
                original_intent=original_intent,
                original_params=original_params,
                confirmation_prompt=confirmation_prompt,
                confirmation_action_id=confirmation_action_id,
                status="pending",
            )
            self._states[session_id] = state
            return state

    def get(self, session_id: str) -> ContinuationState | None:
        """获取当前 continuation 状态。"""
        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                return None
            # TODO: TTL 检查
            return state

    def resume(
        self,
        request: ContinuationResumeRequest,
    ) -> ContinuationResult:
        """尝试恢复 continuation。

        将用户的 follow-up 输入合并到原始参数中，检查是否满足所有缺失参数。
        """
        with self._lock:
            state = self._states.get(request.session_id)
            if state is None:
                return ContinuationResult(
                    status="expired",
                    message="会话已过期或不存在，请重新开始。",
                )

            if state.kind != ContinuationKind.MISSING_PARAMETER:
                # TODO: 处理其他类型
                return ContinuationResult(
                    status="cancelled",
                    message="不支持的 continuation 类型。",
                )

            # 合并用户新提供的参数
            merged_params = dict(state.original_params)
            # 从自然语言中提取参数（简化版，实际应由 interpreter 处理）
            # 这里假设 filled_params 已经由调用方解析好了
            merged_params.update(request.filled_params)

            # 检查是否还有缺失
            still_missing: list[MissingParamSpec] = []
            for mp in state.missing_params:
                if mp.param_name not in merged_params or merged_params[mp.param_name] is None:
                    still_missing.append(mp)

            if still_missing:
                # 更新状态，继续等待
                state.missing_params = still_missing
                state.original_params = merged_params
                self._states[request.session_id] = state
                return ContinuationResult(
                    status="needs_more",
                    next_continuation=state,
                    message=f"还需要提供参数: {', '.join(mp.param_name for mp in still_missing)}",
                )

            # 所有参数都有了，构建完整 command
            completed_command = InterpretedCommand(
                intent=state.original_intent,
                confidence=0.9,  # 多轮补齐后信心提升
                parameters=merged_params,
                requires_clarification=False,
                clarification_question=None,
                user_id=None,  # 应由调用方填充
                raw_input=request.user_input,
            )

            # 清理状态
            del self._states[request.session_id]

            return ContinuationResult(
                status="completed",
                completed_command=completed_command,
                message="参数已补齐，可以执行。",
            )

    def cancel(self, session_id: str) -> bool:
        """取消 continuation。"""
        with self._lock:
            if session_id in self._states:
                del self._states[session_id]
                return True
            return False

    def list_pending(self) -> list[ContinuationState]:
        """列出所有 pending 的 continuation（用于监控/清理）。"""
        with self._lock:
            return [s for s in self._states.values() if s.status == "pending"]

    def cleanup_expired(self, max_age_seconds: int = 3600) -> int:
        """清理过期 continuation，返回清理数量。"""
        # TODO: 基于 created_at 和 ttl_seconds 实现
        return 0

    # 兼容旧接口：runtime asset clarification
    # 这些方法是过渡性的，最终所有 clarification 都应走 ContinuationState

    def has_pending_runtime_asset(self, session_id: str) -> bool:
        """检查是否有 pending 的 runtime asset continuation。"""
        state = self.get(session_id)
        if state is None:
            return False
        return (
            state.kind == ContinuationKind.MISSING_PARAMETER
            and state.original_intent == "call_asset_method"
        )

    def get_pending_runtime_asset_params(self, session_id: str) -> dict[str, Any] | None:
        """获取 pending 的 runtime asset 参数。"""
        state = self.get(session_id)
        if state is None:
            return None
        if state.original_intent != "call_asset_method":
            return None
        return dict(state.original_params)

    def complete_runtime_asset_continuation(
        self,
        session_id: str,
        filled_params: dict[str, Any],
    ) -> InterpretedCommand | None:
        """完成 runtime asset continuation，返回可执行的 command。"""
        request = ContinuationResumeRequest(
            session_id=session_id,
            user_input="",  # 已由调用方解析
            filled_params=filled_params,
        )
        result = self.resume(request)
        if result.status == "completed":
            return result.completed_command
        return None
