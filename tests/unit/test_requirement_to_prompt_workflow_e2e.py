from pathlib import Path

from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.system.runtime.app_config_service import AppConfigService
from app.system.runtime.app_context_store import AppContextStore
from app.system.runtime.app_data_store import AppDataStore
from app.app_installer import AppInstallerService
from app.system.catalog.app_profile_resolver import AppProfileResolverService
from app.system.runtime.app_registry import AppRegistryService
from app.governance.collection_policy_service import CollectionPolicyService
from app.persistence.context_compaction import ContextCompactionService
from app.ai.evaluation_summary_service import EvaluationSummaryService
from app.persistence.event_bus import EventBusService
from app.system.runtime.lifecycle import AppLifecycleService
from app.governance.log_evidence_service import LogEvidenceService
from app.ai.prompt_invocation_service import PromptInvocationService
from app.ai.prompt_selection_service import PromptSelectionService
from app.refinement.requirement_clarifier import RequirementClarifierService
from app.refinement.requirement_blueprint_builder import RequirementBlueprintBuilderService
from app.system.runtime.runtime_host import AppRuntimeHostService
from app.persistence.runtime_state_store import RuntimeStateStore
from app.system.runtime.scheduler import SchedulerService
from app.skills.skill_control import SkillControlService
from app.governance.telemetry_service import TelemetryService
from app.persistence.upgrade_log_service import UpgradeLogService
from app.orchestration.workflow_executor import WorkflowExecutorService


class _FakeLoader:
    def load(self):
        class _Config:
            provider = "OpenAI"
            model = "gpt-5.4"
        return _Config()

    def resolve_api_key(self, config):
        return "sk-test"


class _FakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {
            "id": "resp_e2e_123",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "normalized prompt workflow output"}
                    ],
                }
            ],
            "extra_payload": extra_payload,
        }



def test_requirement_to_prompt_workflow_e2e(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "e2e-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "e2e-ns"), store=store)
    app_config = AppConfigService(data_store=data_store, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    log_evidence = LogEvidenceService(store=store)
    policy_service = CollectionPolicyService(store=store)
    upgrade_log_service = UpgradeLogService(base_dir=str(tmp_path / "e2e-logs"))
    telemetry = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)
    evaluation = EvaluationSummaryService(store=store, upgrade_log_service=upgrade_log_service)
    context_compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=type("_StubWorkflowExecutor", (), {"list_history": lambda self, app_instance_id: [], "_skill_runtime": None})(),
        store=store,
        log_evidence_service=log_evidence,
    )
    prompt_selection = PromptSelectionService(context_compaction=context_compaction, log_evidence=log_evidence)
    prompt_invocation = PromptInvocationService(
        prompt_selection=prompt_selection,
        model_loader=_FakeLoader(),
        client_factory=_FakeClient,
        telemetry_service=telemetry,
        evaluation_summary_service=evaluation,
    )

    skill_control = SkillControlService()
    for skill_id in ["system.app_config", "system.context", "system.state", "system.audit"]:
        skill_control.register(
            SkillRegistryEntry(
                skill_id=skill_id,
                name=skill_id,
                immutable_interface=True,
                active_version="1.0.0",
                versions=[SkillVersion(version="1.0.0", content=skill_id)],
                dependencies=[],
                capability_profile=SkillCapabilityProfile(
                    intelligence_level="L0_deterministic",
                    network_requirement="N0_none",
                    runtime_criticality="C2_required_runtime",
                    execution_locality="local",
                    invocation_default="automatic",
                    risk_level="R1_local_write",
                ),
                runtime_adapter="callable",
            )
        )
    resolver = AppProfileResolverService(skill_control=skill_control)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
        app_config_service=app_config,
        app_profile_resolver=resolver,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
        store=store,
        log_evidence_service=log_evidence,
        prompt_invocation_service=prompt_invocation,
    )

    clarifier = RequirementClarifierService()
    builder = RequirementBlueprintBuilderService()
    spec = clarifier.clarify("帮我做一个文本处理 app，把标题规范化并输出 slug 文本")
    blueprint = builder.build_blueprint_draft(spec)

    assert blueprint.workflows[0].steps[0].ref == "prompt.invoke"

    registry.register_blueprint(blueprint)
    install_result = installer.install_app(blueprint.id, user_id="e2e-user")
    context_store.update_context(
        install_result.app_instance_id,
        current_stage="reasoning",
        current_goal=blueprint.goal,
        status="active",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=install_result.app_instance_id,
        workflow_id=blueprint.workflows[0].id,
        failed_step_ids=["step.seed"],
        execution_id="exec.e2e.1",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=install_result.app_instance_id,
        workflow_id=blueprint.workflows[0].id,
        failed_step_ids=["step.seed"],
        execution_id="exec.e2e.2",
        status="partial",
    )

    result = executor.execute_primary_workflow(
        install_result.app_instance_id,
        inputs={"title": "Hello World"},
    )

    assert result.status == "completed"
    assert result.steps[0].ref == "prompt.invoke"
    assert result.steps[0].output["model_invocation"]["result"]["id"] == "resp_e2e_123"
    assert result.steps[0].output["normalized_response"]["text"] == "normalized prompt workflow output"
    interaction_id = result.steps[0].output["invocation_meta"]["interaction_id"]
    assert telemetry.get_interaction(interaction_id) is not None
    assert evaluation.get(f"prompt-invoke:{interaction_id}") is not None
