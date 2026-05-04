from pathlib import Path
import asyncio

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance
from app.models.chat import ChatMessageRequest
from app.models.interaction import AppCatalogEntry, UserCommand
from app.services.app_application_service import AppApplicationService
from app.services.app_catalog import AppCatalogService
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.app_context_store import AppContextStore
from app.services.draft_app_application_service import DraftAppApplicationService
from app.services.draft_app_service import DraftAppService
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.light_brain_memory import LightBrainMemory
from app.services.pending_task_orchestrator import PendingTaskOrchestrator
from app.services.requirement_router import RequirementRouter
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.system.runtime.pending_task_store import PendingTaskStore
from tests.unit.api_test_helper import create_isolated_test_client



def test_interaction_gateway_opens_service_app(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-gateway-service-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "runtime-gateway-service-ns"), store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    catalog = AppCatalogService()
    registry.register_blueprint(
        AppBlueprint(
            id="bp.assistant",
            name="Assistant",
            goal="long running assistant",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.assistant", "name": "assistant", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service"},
        )
    )
    catalog.register(
        AppCatalogEntry(
            app_id="app.assistant",
            name="Assistant",
            description="long running assistant",
            execution_mode="service",
            trigger_phrases=["打开助手"],
            blueprint_id="bp.assistant",
        )
    )
    gateway = InteractionGateway(catalog, RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u1", text="请帮我打开助手"))

    assert decision.action == "open_app"
    assert decision.execution_mode == "service"
    assert decision.app_instance_id == "app.assistant:u1"
    assert lifecycle.get_instance("app.assistant:u1").status == "running"
    context = context_store.get_context("app.assistant:u1")
    assert context.current_stage == "running"
    assert context.current_goal == "请帮我打开助手"
    assert context.entries[-1].key == "latest-user-command"


def test_interaction_gateway_runs_pipeline_app(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-gateway-pipeline-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "runtime-gateway-pipeline-ns"), store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    catalog = AppCatalogService()
    registry.register_blueprint(
        AppBlueprint(
            id="bp.pipeline",
            name="Pipeline",
            goal="one-shot pipeline",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.pipeline", "name": "pipeline", "triggers": ["manual"], "steps": []}],
            required_modules=["state.set"],
            required_skills=[],
            runtime_policy={"execution_mode": "pipeline", "restart_policy": "never", "idle_strategy": "stop"},
        )
    )
    catalog.register(
        AppCatalogEntry(
            app_id="app.pipeline",
            name="Pipeline",
            description="one-shot pipeline",
            execution_mode="pipeline",
            trigger_phrases=["执行流水线"],
            blueprint_id="bp.pipeline",
        )
    )
    gateway = InteractionGateway(catalog, RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u2", text="现在执行流水线"))

    assert decision.action == "run_pipeline"
    assert decision.execution_mode == "pipeline"
    assert decision.app_instance_id == "app.pipeline:u2:run"
    assert lifecycle.get_instance("app.pipeline:u2:run").status == "stopped"
    assert decision.pending_tasks == ["现在执行流水线"]
    context = context_store.get_context("app.pipeline:u2:run")
    assert context.current_stage == "stopped"
    assert context.status == "archived"
    assert context.entries[-1].key == "latest-pipeline-run"


def test_interaction_gateway_clarifies_unknown_command(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-gateway-clarify-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "runtime-gateway-clarify-ns"), store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    gateway = InteractionGateway(AppCatalogService(), RequirementRouter(), lifecycle, runtime, installer, context_store)

    decision = gateway.handle_command(UserCommand(user_id="u3", text="帮我搞个抽象战略平台"))

    assert decision.action == "clarify"
    assert "未命中已登记 app" in decision.message


def test_runtime_state_store_persists_files(tmp_path: Path) -> None:
    base_dir = tmp_path / "runtime-persistence-store"
    store = RuntimeStateStore(base_dir=str(base_dir))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    runtime.register_instance(
        AppInstance(
            id="app.persist.001",
            blueprint_id="bp.persist.001",
            owner_user_id="user.persist",
            status="installed",
            data_namespace="users/user.persist/apps/app.persist.001",
        )
    )
    runtime.start("app.persist.001")
    runtime.enqueue_task("app.persist.001", "persist task")

    assert Path(base_dir, "app_instances.json").exists()
    assert Path(base_dir, "runtime_leases.json").exists()
    assert Path(base_dir, "runtime_pending_tasks.json").exists()




class _GatewayInterpreter:
    def interpret(self, message, available_apps, user_id, session_id):
        from app.models.chat import InterpretedCommand

        return InterpretedCommand(intent="greet", raw_input=message, user_id=user_id)


def _advance_to_applyable_draft(gateway: LightBrainGateway, *, user_id: str = "u1", session_id: str = "s1") -> str:
    create_decision = gateway._build_continuation_decision("创建一个笔记 app", None)
    assert create_decision is not None
    gateway._materialize_continuation_decision(create_decision, user_id=user_id, session_id=session_id, message="创建一个笔记 app")
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id=user_id, channel="test", message="继续", session_id=session_id)))
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id=user_id, channel="test", message="继续", session_id=session_id)))
    final_response = asyncio.run(gateway.receive_message(ChatMessageRequest(user_id=user_id, channel="test", message="继续", session_id=session_id)))
    assert final_response.data is not None
    return final_response.data["pending_task"]["target_ref"]["app_id"]


def test_draft_apply_action_acceptance_runs_to_running_and_keeps_reply_context(tmp_path: Path) -> None:
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-draft-acceptance"))
    draft_service = DraftAppService(runtime_store)
    lifecycle = AppLifecycleService(store=runtime_store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
    app_application_service = AppApplicationService(
        draft_app_application_service=DraftAppApplicationService(draft_service, lifecycle, runtime_host)
    )
    pending_task_store = PendingTaskStore(runtime_store)
    memory = LightBrainMemory(data_dir=str(tmp_path / "memory-draft-acceptance"))
    gateway = LightBrainGateway(
        memory=memory,
        interpreter=_GatewayInterpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_task_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_task_store, draft_service),
        app_application_service=app_application_service,
    )

    app_id = _advance_to_applyable_draft(gateway)
    action_response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="s1",
            action_id=f"apply-draft:{app_id}",
            action_params={"intent": "apply_draft_app", "app_id": app_id},
        )
    )

    assert action_response.type == "progress"
    assert action_response.related_app == app_id
    assert action_response.data is not None
    assert action_response.data["lifecycle_transition"] == "draft_to_running_activation"
    assert lifecycle.get_instance(app_id).status == "running"
    recent_messages = memory.get_recent_messages("s1")
    assert recent_messages[-1]["role"] == "assistant"
    assert "推进到可运行状态" in recent_messages[-1]["content"]


def test_draft_apply_action_acceptance_exposes_follow_up_query_app_action(tmp_path: Path) -> None:
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-draft-followup"))
    draft_service = DraftAppService(runtime_store)
    lifecycle = AppLifecycleService(store=runtime_store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
    app_application_service = AppApplicationService(
        draft_app_application_service=DraftAppApplicationService(draft_service, lifecycle, runtime_host)
    )
    pending_task_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(data_dir=str(tmp_path / "memory-draft-followup")),
        interpreter=_GatewayInterpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_task_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_task_store, draft_service),
        app_application_service=app_application_service,
    )

    app_id = _advance_to_applyable_draft(gateway)
    action_response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="s1",
            action_id=f"apply-draft:{app_id}",
            action_params={"intent": "apply_draft_app", "app_id": app_id},
        )
    )

    assert action_response.actions
    follow_up = action_response.actions[0]
    assert follow_up.id == "query_status"
    assert follow_up.payload == {"intent": "query_app", "target": app_id}
