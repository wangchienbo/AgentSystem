from app.models.app_blueprint import AppBlueprint
from app.services.policy_guard import PolicyGuardError, PolicyGuardService


service = PolicyGuardService()



def test_policy_guard_allows_declared_prompt_invoke_module() -> None:
    blueprint = AppBlueprint(
        id="bp.prompt.allowed",
        name="Prompt Allowed",
        goal="allow prompt invoke",
        required_modules=["prompt.invoke"],
        required_skills=[],
        workflows=[],
        runtime_policy={"allow_prompt_invoke": True},
    )

    service.ensure_workflow_step_allowed(blueprint, kind="module", ref="prompt.invoke")



def test_policy_guard_blocks_prompt_invoke_when_runtime_policy_disallows() -> None:
    blueprint = AppBlueprint(
        id="bp.prompt.blocked",
        name="Prompt Blocked",
        goal="block prompt invoke",
        required_modules=["prompt.invoke"],
        required_skills=[],
        workflows=[],
        runtime_policy={"allow_prompt_invoke": False},
    )

    try:
        service.ensure_workflow_step_allowed(blueprint, kind="module", ref="prompt.invoke")
    except PolicyGuardError as error:
        assert "prompt invocation disabled" in str(error)
    else:
        raise AssertionError("expected prompt.invoke to be blocked")
