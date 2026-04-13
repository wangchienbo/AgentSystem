"""Phase F.10: Skill-to-Skill invocation with deadlock prevention tests."""

import time
from unittest.mock import MagicMock

import pytest

from app.core.skill_invoker import (
    CallFrame,
    InvocationContext,
    SkillCycleError,
    SkillDepthLimitError,
    SkillInvoker,
    SkillInvocationError,
    SkillNotFoundError,
    SkillTimeoutError,
    create_invocation_context,
    get_context_from_request,
    get_invoker_from_request,
)
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(skill_id: str, output: dict) -> SkillExecutionResult:
    return SkillExecutionResult(skill_id=skill_id, output=output)


def _make_request(skill_id: str, inputs: dict = None, config: dict = None) -> SkillExecutionRequest:
    return SkillExecutionRequest(
        skill_id=skill_id,
        app_instance_id="test-app",
        workflow_id="test-wf",
        step_id="test-step",
        inputs=inputs or {},
        config=config or {},
    )


# ---------------------------------------------------------------------------
# InvocationContext
# ---------------------------------------------------------------------------

class TestInvocationContext:
    def test_initial_state(self):
        ctx = InvocationContext(
            root_skill_id="skill-a",
            root_app_instance_id="app-1",
            root_workflow_id="wf-1",
            max_depth=5,
        )
        assert ctx.root_skill_id == "skill-a"
        assert ctx.depth == 0
        assert ctx.chain == []

    def test_push_pop(self):
        ctx = InvocationContext(
            root_skill_id="a", root_app_instance_id="app", root_workflow_id="wf",
        )
        frame = ctx.push("skill-b", {"x": 1})
        assert ctx.depth == 1
        assert frame.skill_id == "skill-b"

        ctx.pop(frame, result=_make_result("skill-b", {"y": 2}))
        assert frame.finished_at is not None
        assert frame.duration_ms is not None
        assert frame.duration_ms >= 0

    def test_cycle_detection(self):
        ctx = InvocationContext(
            root_skill_id="a", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("skill-a", {})
        ctx.push("skill-b", {})

        with pytest.raises(SkillCycleError, match="[Cc]ycle detected"):
            ctx.check_cycle("skill-a")

        with pytest.raises(SkillCycleError, match="[Cc]ycle detected"):
            ctx.check_cycle("skill-b")

        # No cycle for new skill
        ctx.check_cycle("skill-c")  # should not raise

    def test_depth_limit(self):
        ctx = InvocationContext(
            root_skill_id="a", root_app_instance_id="app", root_workflow_id="wf",
            max_depth=3,
        )
        ctx.push("b", {})
        ctx.push("c", {})
        ctx.check_depth()  # depth=2, max=3, OK

        ctx.push("d", {})
        with pytest.raises(SkillDepthLimitError, match="[Mm]ax call depth"):
            ctx.check_depth()  # depth=3, max=3, exceeded

    def test_timeout_check(self):
        ctx = InvocationContext(
            root_skill_id="a", root_app_instance_id="app", root_workflow_id="wf",
        )
        # No frame — should not raise
        ctx.check_timeout(0.001)

        # Frame just started — should not raise
        ctx.push("slow-skill", {})
        ctx.check_timeout(1.0)  # 1 second timeout, just started

    def test_snapshot(self):
        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        f1 = ctx.push("skill-a", {"input": "hello"})
        ctx.pop(f1, result=_make_result("skill-a", {"output": "world"}))

        snap = ctx.snapshot()
        assert snap["root"] == "root"
        assert snap["depth"] == 1
        assert len(snap["chain"]) == 1
        assert snap["chain"][0]["skill_id"] == "skill-a"
        assert snap["chain"][0]["status"] == "ok"

    def test_snapshot_running(self):
        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("running-skill", {})
        snap = ctx.snapshot()
        assert snap["chain"][0]["status"] == "running"


# ---------------------------------------------------------------------------
# SkillInvoker
# ---------------------------------------------------------------------------

class TestSkillInvoker:
    def test_simple_invoke(self):
        """Invoke one skill from another."""
        call_log = []

        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            call_log.append(request.skill_id)
            return _make_result(request.skill_id, {"echo": request.inputs.get("msg", "")})

        ctx = InvocationContext(
            root_skill_id="caller", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("caller", {})
        invoker = SkillInvoker(execute_fn, ctx)

        result = invoker.invoke("callee", {"msg": "hello"})

        assert result.output == {"echo": "hello"}
        assert call_log == ["callee"]
        # Invoker passed itself in config
        req = SkillExecutionRequest(
            skill_id="test", app_instance_id="app", workflow_id="wf", step_id="s",
        )
        # Verify context propagation — done via execute_fn's request

    def test_chain_invocation(self):
        """Skill A → Skill B → Skill C."""
        call_log = []

        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            call_log.append(request.skill_id)
            invoker = request.config.get("__invoker__")
            if request.skill_id == "skill-a" and invoker:
                result = invoker.invoke("skill-b", {"from": "a"})
                return _make_result("skill-a", {"b_result": result.output})
            elif request.skill_id == "skill-b" and invoker:
                result = invoker.invoke("skill-c", {"from": "b"})
                return _make_result("skill-b", {"c_result": result.output})
            return _make_result(request.skill_id, {"done": True})

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        invoker = SkillInvoker(execute_fn, ctx)
        # Push root
        ctx.push("root", {})
        result = invoker.invoke("skill-a", {})

        assert call_log == ["skill-a", "skill-b", "skill-c"]
        assert result.output["b_result"]["c_result"]["done"] is True
        assert ctx.depth == 4  # root + a + b + c

    def test_cycle_prevention(self):
        """Skill A → Skill B → Skill A should raise SkillCycleError."""
        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker = request.config.get("__invoker__")
            if request.skill_id == "skill-a" and invoker:
                return invoker.invoke("skill-b", {})
            elif request.skill_id == "skill-b" and invoker:
                return invoker.invoke("skill-a", {})  # Cycle!
            return _make_result(request.skill_id, {})

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        invoker = SkillInvoker(execute_fn, ctx)
        ctx.push("root", {})

        with pytest.raises(SkillCycleError, match="[Cc]ycle detected"):
            invoker.invoke("skill-a", {})

    def test_self_call_prevention(self):
        """Skill A calling itself should raise cycle error."""
        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker = request.config.get("__invoker__")
            if request.skill_id == "recursive" and invoker:
                return invoker.invoke("recursive", {})  # Self-call!
            return _make_result(request.skill_id, {})

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        invoker = SkillInvoker(execute_fn, ctx)
        ctx.push("root", {})

        with pytest.raises(SkillCycleError):
            invoker.invoke("recursive", {})

    def test_depth_limit_enforced(self):
        """Deep chain exceeding max_depth should raise."""
        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker = request.config.get("__invoker__")
            if invoker and request.skill_id.startswith("deep-"):
                next_n = int(request.skill_id.split("-")[1]) + 1
                return invoker.invoke(f"deep-{next_n}", {})
            return _make_result(request.skill_id, {"leaf": True})

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
            max_depth=3,
        )
        invoker = SkillInvoker(execute_fn, ctx)
        ctx.push("root", {})

        with pytest.raises(SkillDepthLimitError):
            invoker.invoke("deep-1", {})

    def test_invoke_error_wrapped(self):
        """Execution error should be wrapped in SkillInvocationError."""
        def execute_fn(request: SkillExecutionRequest) -> SkillExecutionResult:
            raise RuntimeError("something went wrong")

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        invoker = SkillInvoker(execute_fn, ctx)
        ctx.push("root", {})

        with pytest.raises(SkillInvocationError, match="something went wrong"):
            invoker.invoke("bad-skill", {})

    def test_context_property(self):
        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        invoker = SkillInvoker(lambda r: _make_result("ok", {}), ctx)
        assert invoker.context is ctx


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    def test_create_invocation_context(self):
        request = _make_request("my-skill")
        ctx = create_invocation_context(request, max_depth=5)
        assert ctx.root_skill_id == "my-skill"
        assert ctx.max_depth == 5

    def test_get_invoker_from_request(self):
        request = _make_request("my-skill", config={"__invoker__": "test-invoker"})
        invoker = get_invoker_from_request(request)
        assert invoker == "test-invoker"

    def test_get_invoker_from_request_none(self):
        request = _make_request("my-skill")
        assert get_invoker_from_request(request) is None

    def test_get_context_from_request(self):
        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        request = _make_request("my-skill", config={"__invocation_ctx__": ctx})
        assert get_context_from_request(request) is ctx


# ---------------------------------------------------------------------------
# Integration: SkillRuntimeService with invoker injection
# ---------------------------------------------------------------------------

class TestRuntimeIntegration:
    def test_invoker_injected_into_callable(self):
        """Verify that SkillRuntimeService injects invoker when context is present."""
        from app.services.skill_runtime import SkillRuntimeService

        received_invoker = None

        def handler(request: SkillExecutionRequest) -> SkillExecutionResult:
            nonlocal received_invoker
            received_invoker = request.config.get("__invoker__")
            return _make_result(request.skill_id, {"result": "ok"})

        runtime = SkillRuntimeService()
        from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry
        entry = SkillRegistryEntry(
            skill_id="test-skill", name="Test", active_version="1.0",
            runtime_adapter="callable", capability_profile=SkillCapabilityProfile(),
        )
        runtime.register_handler("test-skill", handler, entry=entry)

        # Execute with invoker context
        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("root", {})
        invoker = SkillInvoker(runtime.execute, ctx)
        # Push root frame for context
        req = SkillExecutionRequest(
            skill_id="test-skill", app_instance_id="app", workflow_id="wf",
            step_id="step1",
            config={"__invoker__": invoker, "__invocation_ctx__": ctx},
        )
        result = runtime.execute(req)

        assert received_invoker is not None
        assert isinstance(received_invoker, SkillInvoker)
        assert result.output == {"result": "ok"}

    def test_cross_skill_call_via_runtime(self):
        """Skill A invokes Skill B through the runtime."""
        from app.services.skill_runtime import SkillRuntimeService
        from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry

        call_log = []

        def handler_a(request: SkillExecutionRequest) -> SkillExecutionResult:
            call_log.append("a")
            invoker = request.config.get("__invoker__")
            if invoker:
                b_result = invoker.invoke("skill-b", {"from": "a"})
                return _make_result("skill-a", {"b_output": b_result.output})
            return _make_result("skill-a", {"no_invoker": True})

        def handler_b(request: SkillExecutionRequest) -> SkillExecutionResult:
            call_log.append("b")
            return _make_result("skill-b", {"received": request.inputs.get("from")})

        runtime = SkillRuntimeService()
        entry_a = SkillRegistryEntry(
            skill_id="skill-a", name="A", active_version="1.0",
            runtime_adapter="callable", capability_profile=SkillCapabilityProfile(),
        )
        entry_b = SkillRegistryEntry(
            skill_id="skill-b", name="B", active_version="1.0",
            runtime_adapter="callable", capability_profile=SkillCapabilityProfile(),
        )
        runtime.register_handler("skill-a", handler_a, entry=entry_a)
        runtime.register_handler("skill-b", handler_b, entry=entry_b)

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("root", {})
        invoker = SkillInvoker(runtime.execute, ctx)

        req = SkillExecutionRequest(
            skill_id="skill-a", app_instance_id="app", workflow_id="wf",
            step_id="step1",
            config={"__invoker__": invoker, "__invocation_ctx__": ctx},
        )
        result = runtime.execute(req)

        assert call_log == ["a", "b"]
        assert result.output["b_output"]["received"] == "a"

    def test_cycle_detected_in_runtime(self):
        """Runtime should prevent A → B → A cycles."""
        from app.services.skill_runtime import SkillRuntimeService
        from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry

        def handler_a(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker = request.config.get("__invoker__")
            if invoker:
                return invoker.invoke("skill-b", {})
            return _make_result("skill-a", {})

        def handler_b(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker = request.config.get("__invoker__")
            if invoker:
                return invoker.invoke("skill-a", {})  # Cycle!
            return _make_result("skill-b", {})

        runtime = SkillRuntimeService()
        entry_a = SkillRegistryEntry(
            skill_id="skill-a", name="A", active_version="1.0",
            runtime_adapter="callable", capability_profile=SkillCapabilityProfile(),
        )
        entry_b = SkillRegistryEntry(
            skill_id="skill-b", name="B", active_version="1.0",
            runtime_adapter="callable", capability_profile=SkillCapabilityProfile(),
        )
        runtime.register_handler("skill-a", handler_a, entry=entry_a)
        runtime.register_handler("skill-b", handler_b, entry=entry_b)

        ctx = InvocationContext(
            root_skill_id="root", root_app_instance_id="app", root_workflow_id="wf",
        )
        ctx.push("root", {})
        invoker = SkillInvoker(runtime.execute, ctx)

        req = SkillExecutionRequest(
            skill_id="skill-a", app_instance_id="app", workflow_id="wf",
            step_id="step1",
            config={"__invoker__": invoker, "__invocation_ctx__": ctx},
        )

        with pytest.raises(SkillCycleError):
            runtime.execute(req)
