from __future__ import annotations

from app.models.interaction import AppExecutionMode, InteractionDecision, UserCommand
from app.models.telemetry import InteractionTelemetryRecord
from app.services.app_catalog import AppCatalogService
from app.services.app_context_store import AppContextStore
from app.services.app_installer import AppInstallerService
from app.services.lifecycle import AppLifecycleService
from app.services.requirement_router import RequirementRouter
from app.services.runtime_host import AppRuntimeHostService
from app.services.telemetry_service import TelemetryService


class InteractionGateway:
    def __init__(
        self,
        catalog: AppCatalogService,
        router: RequirementRouter,
        lifecycle: AppLifecycleService,
        runtime_host: AppRuntimeHostService,
        installer: AppInstallerService,
        context_store: AppContextStore | None = None,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        self._catalog = catalog
        self._router = router
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._installer = installer
        self._context_store = context_store
        self._telemetry_service = telemetry_service

    def handle_command(self, command: UserCommand) -> InteractionDecision:
        interaction_id = f"interaction:{command.user_id}:{abs(hash(command.text))}"
        matched_app, matched_phrases = self._catalog.match_command(command.text)
        if matched_app is None:
            intent = self._router.route(command.text)
            decision = InteractionDecision(
                action="clarify",
                message=f"未命中已登记 app。当前判断为 {intent.requirement_type}，建议先补充要打开的 app 或更具体的动作。",
                matched_phrases=intent.extracted_keywords,
            )
            self._record_interaction(command, interaction_id=interaction_id, success=True)
            return decision

        if matched_app.execution_mode == "service":
            decision = self._open_service_app(command, matched_app.app_id, matched_app.blueprint_id, matched_app.execution_mode, matched_phrases)
        else:
            decision = self._run_pipeline_app(command, matched_app.app_id, matched_app.blueprint_id, matched_app.execution_mode, matched_phrases)
        self._record_interaction(command, interaction_id=interaction_id, app_id=matched_app.app_id, success=True)
        return decision

    def _open_service_app(
        self,
        command: UserCommand,
        app_id: str,
        blueprint_id: str,
        execution_mode: AppExecutionMode,
        matched_phrases: list[str],
    ) -> InteractionDecision:
        app_instance_id = f"{app_id}:{command.user_id}"
        self._installer.install_app(blueprint_id=blueprint_id, user_id=command.user_id, app_instance_id=app_instance_id)
        if self._lifecycle.get_instance(app_instance_id).status in {"installed", "stopped", "failed"}:
            overview = self._runtime_host.start(app_instance_id, reason="user open app")
        else:
            overview = self._runtime_host.get_overview(app_instance_id)
        if self._context_store is not None:
            self._context_store.update_context(
                app_instance_id,
                current_stage="running",
                current_goal=command.text,
                status="active",
            )
            self._context_store.append_entry(
                app_instance_id,
                section="open_loops",
                key="latest-user-command",
                value={"text": command.text, "mode": "service_open"},
                tags=["interaction", "user-command"],
            )
        return InteractionDecision(
            action="open_app",
            app_id=app_id,
            app_instance_id=app_instance_id,
            execution_mode=execution_mode,
            message=f"已打开长期运行 app: {app_id}",
            matched_phrases=matched_phrases,
            pending_tasks=overview.pending_tasks,
        )

    def _run_pipeline_app(
        self,
        command: UserCommand,
        app_id: str,
        blueprint_id: str,
        execution_mode: AppExecutionMode,
        matched_phrases: list[str],
    ) -> InteractionDecision:
        app_instance_id = f"{app_id}:{command.user_id}:run"
        self._installer.install_app(blueprint_id=blueprint_id, user_id=command.user_id, app_instance_id=app_instance_id)
        self._runtime_host.start(app_instance_id, reason="run pipeline")
        pending_tasks = self._runtime_host.enqueue_task(app_instance_id, command.text)
        overview = self._runtime_host.stop(app_instance_id, reason="pipeline complete")
        if self._context_store is not None:
            self._context_store.update_context(
                app_instance_id,
                current_stage="stopped",
                current_goal=command.text,
                status="archived",
            )
            self._context_store.append_entry(
                app_instance_id,
                section="artifacts",
                key="latest-pipeline-run",
                value={"text": command.text, "pending_tasks": pending_tasks},
                tags=["interaction", "pipeline-run"],
            )
        return InteractionDecision(
            action="run_pipeline",
            app_id=app_id,
            app_instance_id=app_instance_id,
            execution_mode=execution_mode,
            message=f"已执行一次性 pipeline app: {app_id}",
            matched_phrases=matched_phrases,
            pending_tasks=overview.pending_tasks or pending_tasks,
        )

    def _record_interaction(self, command: UserCommand, *, interaction_id: str, app_id: str | None = None, success: bool = True) -> None:
        if self._telemetry_service is None:
            return
        self._telemetry_service.record_interaction(
            InteractionTelemetryRecord(
                interaction_id=interaction_id,
                user_id=command.user_id,
                app_id=app_id,
                request_type="user_command",
                success=success,
                strategy_name="interaction_gateway",
            )
        )

