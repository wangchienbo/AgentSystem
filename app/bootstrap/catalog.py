from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.interaction import AppCatalogEntry
from app.services.app_catalog import AppCatalogService
from app.services.app_registry import AppRegistryService


def bootstrap_demo_catalog(app_registry: AppRegistryService, app_catalog: AppCatalogService) -> None:
    app_registry.register_blueprint(
        AppBlueprint(
            id="bp.workspace.assistant",
            name="Workspace Assistant",
            goal="长期运行的工作台助手 app",
            roles=[{"id": "workspace.agent", "name": "Workspace Agent", "type": "agent"}],
            tasks=[],
            workflows=[{"id": "wf.assistant", "name": "assistant loop", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive",
            },
        )
    )
    app_registry.register_blueprint(
        AppBlueprint(
            id="bp.pipeline.executor",
            name="Pipeline Executor",
            goal="一次性流水线执行 app",
            roles=[{"id": "pipeline.agent", "name": "Pipeline Agent", "type": "agent"}],
            tasks=[],
            workflows=[{"id": "wf.pipeline", "name": "pipeline run", "triggers": ["manual"], "steps": []}],
            required_modules=["state.set"],
            required_skills=[],
            runtime_policy={
                "execution_mode": "pipeline",
                "activation": "on_demand",
                "restart_policy": "never",
                "persistence_level": "standard",
                "idle_strategy": "stop",
            },
        )
    )
    app_catalog.register(
        AppCatalogEntry(
            app_id="app.workspace.assistant",
            name="Workspace Assistant",
            description="长期运行的工作台助手 app",
            execution_mode="service",
            trigger_phrases=["打开助手", "assistant", "workspace assistant", "打开工作台"],
            blueprint_id="bp.workspace.assistant",
        )
    )
    app_catalog.register(
        AppCatalogEntry(
            app_id="app.pipeline.executor",
            name="Pipeline Executor",
            description="一次性流水线执行 app",
            execution_mode="pipeline",
            trigger_phrases=["执行流水线", "pipeline", "run pipeline", "跑一下流程"],
            blueprint_id="bp.pipeline.executor",
        )
    )
