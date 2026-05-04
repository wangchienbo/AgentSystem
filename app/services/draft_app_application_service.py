from __future__ import annotations

from app.models.app_instance import AppInstance
from app.models.chat import ActionSuggestion, ChatMessageResponse, InterpretedCommand
from app.services.draft_app_service import DraftAppService
from app.system.runtime.lifecycle import AppLifecycleService, LifecycleError
from app.system.runtime.runtime_host import AppRuntimeHostService, RuntimeHostError


class DraftAppApplicationService:
    """Application-layer handoff for draft apps entering the formal lifecycle."""

    def __init__(
        self,
        draft_app_service: DraftAppService,
        lifecycle_service: AppLifecycleService | None = None,
        runtime_host_service: AppRuntimeHostService | None = None,
    ) -> None:
        self._draft_app_service = draft_app_service
        self._lifecycle_service = lifecycle_service
        self._runtime_host_service = runtime_host_service

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
        runtime_status = self._ensure_installed_and_running(lifecycle_app.id)

        content = (
            f"已把 draft app 接入正式生命周期，并推进到可运行状态。\n"
            f"App ID：{lifecycle_app.id}\n"
            f"当前状态：{runtime_status}\n"
            f"下一步：可以查看状态，或继续对这个 app 做正式管理。"
        )
        return ChatMessageResponse(
            type="progress",
            content=content,
            session_id=session_id,
            data={
                "app_id": lifecycle_app.id,
                "app_status": runtime_status,
                "source": "DraftAppApplicationService",
                "lifecycle_transition": "draft_to_running_activation",
            },
            actions=[
                ActionSuggestion(
                    id="query_status",
                    label="查看状态",
                    action_type="execute",
                    payload={"intent": "query_app", "target": lifecycle_app.id},
                    style="secondary",
                )
            ],
            related_app=lifecycle_app.id,
        )

    def _register_or_reuse_lifecycle_instance(self, draft_app: AppInstance) -> AppInstance:
        if self._lifecycle_service is None:
            return draft_app
        try:
            existing = self._lifecycle_service.get_instance(draft_app.id)
        except LifecycleError:
            if self._runtime_host_service is not None:
                return self._runtime_host_service.register_instance(draft_app.model_copy(deep=True))
            return self._lifecycle_service.register_instance(draft_app.model_copy(deep=True))
        if self._runtime_host_service is not None:
            self._runtime_host_service._checkpoints.setdefault(existing.id, [])
            self._runtime_host_service._pending_tasks.setdefault(existing.id, [])
        return existing

    def _ensure_installed_and_running(self, app_id: str) -> str:
        if self._lifecycle_service is None:
            draft_app = self._draft_app_service.get_app(app_id)
            return "unknown" if draft_app is None else draft_app.status

        app = self._lifecycle_service.get_instance(app_id)
        if app.status == "compiled":
            self._lifecycle_service.transition(app_id, "install", reason="draft_apply")
            app = self._lifecycle_service.get_instance(app_id)

        if app.status == "installed" and self._runtime_host_service is not None:
            try:
                self._runtime_host_service.start(app_id, reason="draft_apply")
                app = self._lifecycle_service.get_instance(app_id)
            except RuntimeHostError:
                pass
            except LifecycleError:
                pass

        return app.status
