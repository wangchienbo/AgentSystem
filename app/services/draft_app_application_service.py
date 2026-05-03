from __future__ import annotations

from app.models.app_instance import AppInstance
from app.models.chat import ChatMessageResponse, InterpretedCommand
from app.services.draft_app_service import DraftAppService
from app.system.runtime.lifecycle import AppLifecycleService, LifecycleError


class DraftAppApplicationService:
    """Application-layer handoff for draft apps entering the formal lifecycle."""

    def __init__(
        self,
        draft_app_service: DraftAppService,
        lifecycle_service: AppLifecycleService | None = None,
    ) -> None:
        self._draft_app_service = draft_app_service
        self._lifecycle_service = lifecycle_service

    async def handle_apply_draft_app(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, object]],
    ) -> ChatMessageResponse:
        app_id = command.parameters.get("app_id") or command.target_app
        if not isinstance(app_id, str) or not app_id.strip():
            return ChatMessageResponse(
                type="error",
                content="缺少 draft app_id，暂时无法接入正式生命周期。",
                session_id=session_id,
            )

        draft_app = self._draft_app_service.get_app(app_id)
        if draft_app is None:
            return ChatMessageResponse(
                type="error",
                content=f"没有找到对应的 draft app：{app_id}",
                session_id=session_id,
            )

        lifecycle_app = self._register_or_reuse_lifecycle_instance(draft_app)

        content = (
            f"已把 draft app 接入正式生命周期。\n"
            f"App ID：{lifecycle_app.id}\n"
            f"当前状态：{lifecycle_app.status}\n"
            f"下一步：可以继续安装或启动这个 app。"
        )
        return ChatMessageResponse(
            type="progress",
            content=content,
            session_id=session_id,
            data={
                "app_id": lifecycle_app.id,
                "app_status": lifecycle_app.status,
                "source": "DraftAppApplicationService",
                "lifecycle_transition": "draft_to_compiled_registration",
            },
            related_app=lifecycle_app.id,
        )

    def _register_or_reuse_lifecycle_instance(self, draft_app: AppInstance) -> AppInstance:
        if self._lifecycle_service is None:
            return draft_app
        try:
            return self._lifecycle_service.get_instance(draft_app.id)
        except LifecycleError:
            return self._lifecycle_service.register_instance(draft_app.model_copy(deep=True))
