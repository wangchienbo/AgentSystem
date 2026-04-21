# Context Upload 工具函数
# Phase H+ 风险护栏：Context upload 白名单和 system note 模板的工具函数

from __future__ import annotations

from app.config.context_upload import (
    ContextUploadConfig,
    SYSTEM_NOTE_TEMPLATES,
    is_content_allowed_for_upload,
    format_system_note,
    validate_context_upload,
)
from app.models.context import SessionContextRecord


class ContextUploadHelper:
    """
    Context Upload 辅助工具类
    
    提供统一的 context upload 接口，确保所有上传都经过白名单校验和模板格式化
    """
    
    def __init__(self, config: ContextUploadConfig | None = None):
        self._config = config or ContextUploadConfig()
    
    def create_message_record(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> SessionContextRecord:
        """
        创建 message 类型的上下文记录（经过白名单校验）
        """
        allowed, reason = is_content_allowed_for_upload(
            content, "message", role, self._config
        )
        if not allowed:
            raise ValueError(f"Message 内容不允许上传：{reason}")
        
        return SessionContextRecord(
            session_id=session_id,
            kind="message",
            role=role,
            content=content,
            metadata={},
        )
    
    def create_system_note(
        self,
        session_id: str,
        template_name: str,
        **kwargs
    ) -> SessionContextRecord:
        """
        使用模板创建 system_note 记录
        """
        success, result = format_system_note(template_name, **kwargs)
        if not success:
            raise ValueError(f"System note 模板格式化失败：{result}")
        
        # 验证最终长度
        allowed, reason = is_content_allowed_for_upload(
            result, "system_note", "system", self._config
        )
        if not allowed:
            raise ValueError(f"System note 内容不允许上传：{reason}")
        
        return SessionContextRecord(
            session_id=session_id,
            kind="system_note",
            role="system",
            content=result,
            metadata={"template": template_name},
        )
    
    def create_dispatch_decision_note(
        self,
        session_id: str,
        actor: str,
        resolved_session_id: str,
        decision: str,
        outcome: str,
    ) -> SessionContextRecord:
        """
        创建 dispatch decision 类型的 system note
        """
        return self.create_system_note(
            session_id,
            "dispatch_decision",
            actor=actor,
            resolved_session_id=resolved_session_id,
            decision=decision,
            outcome=outcome,
        )
    
    def create_tool_execution_note(
        self,
        session_id: str,
        tool_name: str,
        status: str,
        duration_ms: int,
    ) -> SessionContextRecord:
        """
        创建 tool execution 类型的 system note
        """
        return self.create_system_note(
            session_id,
            "tool_execution",
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
        )
    
    def create_session_lifecycle_note(
        self,
        session_id: str,
        action: str,
        status: str,
    ) -> SessionContextRecord:
        """
        创建 session lifecycle 类型的 system note
        """
        return self.create_system_note(
            session_id,
            "session_lifecycle",
            action=action,
            session_id=session_id,
            status=status,
        )
    
    def create_error_boundary_note(
        self,
        session_id: str,
        error_type: str,
        brief_message: str,
    ) -> SessionContextRecord:
        """
        创建 error boundary 类型的 system note
        """
        return self.create_system_note(
            session_id,
            "error_boundary",
            error_type=error_type,
            brief_message=brief_message,
        )
    
    def validate_and_upload(
        self,
        context_center,
        records: list[SessionContextRecord],
    ) -> tuple[bool, list[str]]:
        """
        批量验证并上传记录到 ContextCenter
        
        Returns:
            (success, errors): 如果全部成功返回 (True, [])，否则返回 (False, [错误列表])
        """
        # 转换为 dict 格式进行验证
        record_dicts = [
            {
                "kind": r.kind,
                "role": r.role,
                "content": r.content,
            }
            for r in records
        ]
        
        valid, errors = validate_context_upload(record_dicts, self._config)
        if not valid:
            return False, errors
        
        # 逐条上传
        try:
            for record in records:
                context_center.append_context_record(record.session_id, record)
            return True, []
        except Exception as e:
            return False, [f"上传失败：{e}"]


# 便捷函数
def create_context_upload_helper(config: ContextUploadConfig | None = None) -> ContextUploadHelper:
    """创建 ContextUploadHelper 实例"""
    return ContextUploadHelper(config)


def create_dispatch_decision(
    session_id: str,
    actor: str,
    resolved_session_id: str,
    decision: str,
    outcome: str,
) -> SessionContextRecord:
    """便捷函数：创建 dispatch decision system note"""
    helper = ContextUploadHelper()
    return helper.create_dispatch_decision_note(
        session_id, actor, resolved_session_id, decision, outcome
    )


def create_tool_execution_record(
    session_id: str,
    tool_name: str,
    status: str,
    duration_ms: int,
) -> SessionContextRecord:
    """便捷函数：创建 tool execution system note"""
    helper = ContextUploadHelper()
    return helper.create_tool_execution_note(
        session_id, tool_name, status, duration_ms
    )
