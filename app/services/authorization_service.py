"""Authorization Service — 授权态管理服务。

管理会话级授权状态的读写、判断和持久化。
网关在每轮交互前读取授权态，决定执行模式。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.models.authorization import (
    AuthorizationDecision,
    AuthorizationLevel,
    AuthorizationState,
    make_default_auth_state,
)

logger = logging.getLogger(__name__)


class AuthorizationService:
    """授权态管理服务。

    职责：
    1. 按 session 存储/读取授权态
    2. 判断当前授权是否足以执行某种操作
    3. 根据授权态生成执行决策
    4. 提供授权、撤销、过期清理能力

    支持持久化（通过 RuntimeStateStore），重启不丢失授权态。
    """

    STORAGE_KEY = "authorization_states"

    def __init__(self, state_store: Any = None) -> None:
        self._states: dict[str, AuthorizationState] = {}
        self._state_store = state_store
        self._load_from_store()

    # ── 持久化 ──

    def _load_from_store(self) -> None:
        """启动时从持久化存储恢复授权态。"""
        if not self._state_store:
            return
        try:
            raw = self._state_store.load_json(self.STORAGE_KEY, default={})
            if not isinstance(raw, dict):
                return
            loaded = 0
            for session_id, data in raw.items():
                try:
                    self._states[session_id] = AuthorizationState(**data)
                    loaded += 1
                except Exception as e:
                    logger.warning("Failed to load auth state for %s: %s", session_id, e)
            if loaded:
                logger.info("Restored %d authorization states from store", loaded)
        except Exception as e:
            logger.warning("Failed to load authorization states: %s", e)

    def _persist(self) -> None:
        """持久化所有授权态到存储。"""
        if not self._state_store:
            return
        try:
            self._state_store.save_mapping(self.STORAGE_KEY, self._states)
        except Exception as e:
            logger.warning("Failed to persist authorization states: %s", e)

    # ── 读写 ──

    def get_or_create(self, session_id: str, user_id: str) -> AuthorizationState:
        """获取或创建会话授权态。"""
        if session_id not in self._states:
            self._states[session_id] = make_default_auth_state(session_id, user_id)
        return self._states[session_id]

    def get(self, session_id: str) -> AuthorizationState | None:
        """获取会话授权态，不存在返回 None。"""
        return self._states.get(session_id)

    def save(self, state: AuthorizationState) -> None:
        """保存授权态。"""
        self._states[state.session_id] = state
        self._persist()
        logger.info(
            "Authorization saved: session=%s level=%s modify=%s restart=%s bg=%s",
            state.session_id,
            state.level.value,
            state.allow_modify,
            state.allow_restart,
            state.allow_background_continue,
        )

    # ── 授权操作 ──

    def authorize(
        self,
        session_id: str,
        user_id: str,
        *,
        level: AuthorizationLevel = AuthorizationLevel.AUTHORIZED,
        allow_modify: bool = False,
        allow_restart: bool = False,
        allow_background_continue: bool = False,
        message: str = "",
        intent: str = "",
        ttl_seconds: int | None = None,
    ) -> AuthorizationState:
        """对会话进行授权。"""
        state = self.get_or_create(session_id, user_id)
        state.authorize(
            level=level,
            allow_modify=allow_modify,
            allow_restart=allow_restart,
            allow_background_continue=allow_background_continue,
            message=message,
            intent=intent,
            ttl_seconds=ttl_seconds,
        )
        self.save(state)
        logger.info(
            "Authorized: session=%s level=%s modify=%s restart=%s bg=%s",
            session_id, level.value, allow_modify, allow_restart, allow_background_continue,
        )
        return state

    def revoke(self, session_id: str) -> None:
        """撤销会话授权，回到保守模式。"""
        state = self._states.get(session_id)
        if state:
            state.revoke()
            self._persist()
            logger.info("Authorization revoked: session=%s", session_id)

    def consume(self, session_id: str) -> None:
        """标记授权已被使用在一轮决策中。"""
        state = self._states.get(session_id)
        if state:
            state.consumed = True

    # ── 判断 ──

    def make_decision(self, session_id: str, engineering_task: bool = False) -> AuthorizationDecision:
        """根据授权态和执行类型，生成执行决策。

        Args:
            session_id: 会话 ID
            engineering_task: 当前是否为工程任务模式

        Returns:
            AuthorizationDecision 包含执行模式和建议
        """
        state = self.get(session_id)
        if not state or not state.is_authorized():
            return AuthorizationDecision(
                can_execute=False,
                execution_mode="chat",
                reason="未授权，需要用户确认",
                requires_clarification=True,
                clarification_prompt="需要你先确认授权才能执行修改操作。",
            )

        # 已授权 → 判断执行深度
        if state.allow_background_continue and engineering_task:
            return AuthorizationDecision(
                can_execute=True,
                execution_mode="background",
                reason="已授权后台执行，工程任务模式",
                requires_clarification=False,
            )

        if state.allow_modify or state.allow_restart:
            return AuthorizationDecision(
                can_execute=True,
                execution_mode="execute",
                reason="已授权执行",
                requires_clarification=False,
            )

        # 只有基础授权
        return AuthorizationDecision(
            can_execute=True,
            execution_mode="chat",
            reason="已授权但仅限于会话交互",
            requires_clarification=False,
        )

    def requires_authorization(self, session_id: str, action_type: str) -> bool:
        """判断某类操作是否需要授权。

        Args:
            session_id: 会话 ID
            action_type: 操作类型 (modify/restart/background)
        """
        state = self.get(session_id)
        if not state or not state.is_authorized():
            return True

        if action_type == "modify" and not state.allow_modify:
            return True
        if action_type == "restart" and not state.allow_restart:
            return True
        if action_type == "background" and not state.allow_background_continue:
            return True

        return False

    # ── 清理 ──

    def clean_expired(self) -> int:
        """清理过期授权态，返回清理数量。"""
        now = datetime.now(UTC)
        expired = [
            sid for sid, s in self._states.items()
            if s.expires_at and now > s.expires_at
        ]
        for sid in expired:
            del self._states[sid]
        if expired:
            self._persist()
            logger.info("Cleaned %d expired authorization states", len(expired))
        return len(expired)

    def clear_session(self, session_id: str) -> None:
        """清除指定会话的授权态。"""
        self._states.pop(session_id, None)
        self._persist()
