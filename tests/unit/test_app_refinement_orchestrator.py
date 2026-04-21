from __future__ import annotations

from types import SimpleNamespace

from app.models.app_blueprint import AppBlueprint, Workflow, View
from app.models.app_refinement import SuggestedSkillRefinementClosureRequest
from app.models.skill_creation import AppFromSkillsResult
from app.orchestration.app_refinement_orchestrator import AppRefinementOrchestratorService


class _FakeAppRefinement:
    def build_app_from_suggested_skills(self, request):
        blueprint = AppBlueprint(
            id="bp.novel",
            name="novel",
            goal="refine novel app",
            app_shape="generic",
            required_skills=["skill.a"],
            workflows=[Workflow(id="wf.main", name="Main")],
            views=[View(id="view.main", name="Main", type="page")],
        )
        app_result = AppFromSkillsResult(
            blueprint_id="bp.novel",
            workflow_id="wf.main",
            required_skills=["skill.a"],
            created_steps=[],
        )
        return SimpleNamespace(
            blueprint=blueprint,
            app_result=app_result,
            created_skills=[],
            reused_skill_ids=["skill.a"],
            selected_blueprints=[],
        )


class _FakeRegistry:
    def __init__(self):
        self.release_calls = []

    def register_blueprint(self, blueprint):
        return SimpleNamespace(id=blueprint.id)

    def add_release(self, blueprint_id, version, note, reviewer, activate_immediately=False):
        self.release_calls.append({
            "blueprint_id": blueprint_id,
            "version": version,
            "note": note,
            "reviewer": reviewer,
            "activate_immediately": activate_immediately,
        })
        return SimpleNamespace(model_dump=lambda mode="json": {"blueprint_id": blueprint_id, "version": version, "note": note})

    def get_blueprint(self, blueprint_id):
        return SimpleNamespace(runtime_profile={}, runtime_policy={})


class _FailingInstaller:
    def install_app(self, blueprint_id, user_id):
        from app.services.app_installer import AppInstallerError
        raise AppInstallerError("install failed")


class _FakeInstaller:
    def install_app(self, blueprint_id, user_id):
        return SimpleNamespace(app_instance_id="inst.novel", model_dump=lambda mode="json": {"app_instance_id": "inst.novel"})


class _FakeWorkflowExecutor:
    def __init__(self):
        self.calls = []

    def execute_workflow(self, *, app_instance_id, workflow_id, trigger, inputs):
        self.calls.append({
            "app_instance_id": app_instance_id,
            "workflow_id": workflow_id,
            "trigger": trigger,
            "inputs": inputs,
        })
        return SimpleNamespace(
            model_dump=lambda mode="json": {"status": "completed"},
            status="completed",
            failed_step_ids=[],
            unresolved_step_ids=[],
        )


def test_app_refinement_orchestrator_includes_phase_h_context_in_compare_summary() -> None:
    registry = _FakeRegistry()
    svc = AppRefinementOrchestratorService(
        app_refinement=_FakeAppRefinement(),
        app_registry=registry,
        app_installer=_FakeInstaller(),
        workflow_executor=_FakeWorkflowExecutor(),
        policy_authority=None,
    )

    result = svc.refine_closure(SuggestedSkillRefinementClosureRequest(
        blueprint_id="bp.novel",
        name="novel",
        note="phase5 refined candidate",
        target_app="novel",
        context_hints=["recent:App: novel"],
        related_session_ids=["sess-1"],
    ))

    assert result.compare_summary["target_app"] == "novel"
    assert result.compare_summary["context_hints"] == ["recent:App: novel"]
    assert result.compare_summary["related_session_ids"] == ["sess-1"]
    assert "target_app=novel" in registry.release_calls[-1]["note"]
    assert "context_hints=recent:App: novel" in registry.release_calls[-1]["note"]


def test_app_refinement_orchestrator_feeds_phase_h_context_into_workflow_inputs() -> None:
    workflow = _FakeWorkflowExecutor()
    svc = AppRefinementOrchestratorService(
        app_refinement=_FakeAppRefinement(),
        app_registry=_FakeRegistry(),
        app_installer=_FakeInstaller(),
        workflow_executor=workflow,
        policy_authority=None,
    )

    svc.refine_closure(SuggestedSkillRefinementClosureRequest(
        blueprint_id="bp.novel",
        name="novel",
        user_id="u1",
        install=True,
        run=True,
        workflow_inputs={"foo": "bar"},
        target_app="novel",
        context_hints=["recent:App: novel"],
        related_session_ids=["sess-1", "sess-2"],
    ))

    assert workflow.calls[-1]["inputs"]["foo"] == "bar"
    assert workflow.calls[-1]["inputs"]["target_app"] == "novel"
    assert workflow.calls[-1]["inputs"]["context_hints"] == ["recent:App: novel"]
    assert workflow.calls[-1]["inputs"]["related_session_ids"] == ["sess-1", "sess-2"]


def test_app_refinement_orchestrator_install_diagnostic_carries_phase_h_context() -> None:
    svc = AppRefinementOrchestratorService(
        app_refinement=_FakeAppRefinement(),
        app_registry=_FakeRegistry(),
        app_installer=_FailingInstaller(),
        workflow_executor=_FakeWorkflowExecutor(),
        policy_authority=None,
    )

    result = svc.refine_closure(SuggestedSkillRefinementClosureRequest(
        blueprint_id="bp.novel",
        name="novel",
        user_id="u1",
        install=True,
        target_app="novel",
        context_hints=["recent:App: novel"],
        related_session_ids=["sess-1", "sess-2"],
    ))

    diagnostic = result.diagnostics[-1]
    assert diagnostic["details"]["target_app"] == "novel"
    assert diagnostic["details"]["context_hints"] == ["recent:App: novel"]
    assert diagnostic["details"]["related_session_ids"] == ["sess-1", "sess-2"]
