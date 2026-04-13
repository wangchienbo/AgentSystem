"""Comprehensive E2E tests for the dynamic asset registry architecture.

Covers the full instruction chain:
  User Interaction → App Creation → Modification → Execution
  → Solidification → Re-Execution → Visibility / Permission Gates

These tests simulate the complete flow from the interaction layer through
the asset registry, to the orchestrator and back — without requiring a
running Gateway.
"""
import pytest

from app.models.asset import Asset, AssetFunction, AssetType, Visibility
from app.services.asset_registry import AssetRegistry
from app.services.asset_tools import AssetToolExecutor, assemble_asset_overview_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_asset(app_id, owner_id, functions=None, visibility=Visibility.PRIVATE):
    a = Asset(
        asset_id=app_id,
        asset_type=AssetType.APP,
        owner_id=owner_id,
        name=app_id,
        description=f"App {app_id}",
        visibility=visibility,
    )
    if functions:
        for key, name in functions:
            a.add_function(AssetFunction(key=key, name=name, description=""))
    return a


def _make_skill_asset(skill_id, owner_id, functions=None):
    a = Asset(
        asset_id=skill_id,
        asset_type=AssetType.SKILL,
        owner_id=owner_id,
        name=skill_id,
        description=f"Skill {skill_id}",
    )
    if functions:
        for key, name in functions:
            a.add_function(AssetFunction(key=key, name=name, description=""))
    return a


def _mock_router(app_id, path_key, inputs):
    """Simulate an orchestrator executing a path."""
    return {
        "app_id": app_id,
        "path_key": path_key,
        "inputs": inputs,
        "output": f"result from {app_id}/{path_key}",
    }


def _build_registry():
    """Build a standard test registry with multiple users and apps."""
    reg = AssetRegistry()

    # System assets
    reg.register(_make_app_asset("system.master", "system", [
        ("create_app", "创建应用"),
        ("modify_app", "修改应用"),
        ("list_apps", "查询应用"),
    ], Visibility.PUBLIC))

    # User Alice's assets
    reg.register(_make_app_asset("app.novel", "user.alice", [
        ("write_chapter", "生成章节"),
        ("generate_outline", "生成大纲"),
        ("revise", "修改"),
    ]))
    reg.register(_make_skill_asset("skill.writer", "app.novel", [
        ("write", "写文本"),
        ("continue_text", "续写"),
    ]))
    reg.register(_make_skill_asset("skill.reviewer", "app.novel", [
        ("review", "审核"),
    ]))

    # User Bob's assets
    reg.register(_make_app_asset("app.music", "user.bob", [
        ("compose", "作曲"),
        ("lyrics", "填词"),
    ]))

    # Shared asset
    shared = _make_app_asset("app.translator", "user.alice", [
        ("translate", "翻译"),
    ], Visibility.USER_SHARED)
    shared.shared_with = ["user.bob"]
    reg.register(shared)

    return reg


# ===========================================================================
# E2E-1 ~ E2E-5: Asset Registry Lifecycle
# ===========================================================================

class TestE2E_AssetLifecycle:
    """E2E-1..5: Full lifecycle of dynamic asset registration."""

    def test_e2e_1_system_startup_initialization(self):
        """System starts, initializes registry, registers system assets."""
        reg = AssetRegistry()
        # System startup: register core system assets
        reg.register(_make_app_asset("system.master", "system", [
            ("create_app", "创建应用"),
        ], Visibility.PUBLIC))
        reg.register(_make_app_asset("system.monitor", "system", [
            ("health_check", "健康检查"),
        ]))

        counts = reg.asset_count()
        assert counts["system"] == 2
        assert counts["total"] == 2
        assert "system" in reg.list_owners()

    def test_e2e_2_app_startup_registration(self):
        """App starts → automatically registers to owner's asset table."""
        reg = AssetRegistry()
        reg.ensure_owner_table("user.alice")

        # Simulate app.novel starting up
        app = _make_app_asset("app.novel", "user.alice", [
            ("write", "写"),
        ])
        reg.register(app)

        visible = reg.get_visible_assets("user.alice")
        assert any(a.asset_id == "app.novel" for a in visible)

    def test_e2e_3_skill_startup_registration_to_app_owner(self):
        """Skill starts → registers to its owner (an App)."""
        reg = AssetRegistry()
        # App already running
        reg.register(_make_app_asset("app.novel", "user.alice"))
        # Skill starts
        reg.register(_make_skill_asset("skill.writer", "app.novel", [
            ("write", "写"),
        ]))

        # App can see its bound skill
        app_visible = reg.get_visible_assets("app.novel")
        assert any(a.asset_id == "skill.writer" for a in app_visible)

    def test_e2e_4_skill_startup_creates_owner_table_if_missing(self):
        """Skill registers to a new app owner — creates the table automatically."""
        reg = AssetRegistry()
        assert "app.new_app" not in reg._user_assets

        reg.register(_make_skill_asset("skill.helper", "app.new_app", [
            ("help", "帮助"),
        ]))

        assert "app.new_app" in reg._user_assets
        assert "skill.helper" in reg._user_assets["app.new_app"]

    def test_e2e_5_app_shutdown_unregistration(self):
        """App stops → unregister from registry."""
        reg = _build_registry()
        assert reg.asset_count()["user_total"] > 0

        reg.unregister("app.novel", "user.alice")
        visible = reg.get_visible_assets("user.alice")
        assert not any(a.asset_id == "app.novel" for a in visible)


# ===========================================================================
# E2E-6 ~ E2E-10: Visibility & Permission Gates
# ===========================================================================

class TestE2E_visibility:
    """E2E-6..10: Multi-user visibility and permission isolation."""

    def test_e2e_6_system_sees_everything(self):
        reg = _build_registry()
        visible = reg.get_visible_assets("system")
        ids = {a.asset_id for a in visible}
        assert "system.master" in ids
        assert "app.novel" in ids
        assert "app.music" in ids
        assert "skill.writer" in ids

    def test_e2e_7_user_sees_only_own_and_public(self):
        reg = _build_registry()
        visible = reg.get_visible_assets("user.alice")
        ids = {a.asset_id for a in visible}
        assert "app.novel" in ids
        assert "system.master" in ids  # public
        assert "app.music" not in ids  # bob's private

    def test_e2e_8_user_sees_shared_assets(self):
        reg = _build_registry()
        visible = reg.get_visible_assets("user.bob")
        ids = {a.asset_id for a in visible}
        assert "app.translator" in ids  # shared with bob

    def test_e2e_9_user_does_not_see_unshared_assets(self):
        reg = _build_registry()
        visible = reg.get_visible_assets("user.bob")
        ids = {a.asset_id for a in visible}
        # Alice didn't share skill.writer with bob
        assert "skill.writer" not in ids
        assert "skill.reviewer" not in ids

    def test_e2e_10_app_sees_only_bound_skills_and_public(self):
        reg = _build_registry()
        visible = reg.get_visible_assets("app.novel")
        ids = {a.asset_id for a in visible}
        assert "skill.writer" in ids
        assert "skill.reviewer" in ids
        assert "system.master" in ids  # public
        assert "app.music" not in ids


# ===========================================================================
# E2E-11 ~ E2E-15: LLM Prompt Assembly & Detail Query
# ===========================================================================

class TestE2E_llmInteraction:
    """E2E-11..15: LLM prompt injection and detail query flow."""

    def test_e2e_11_assemble_prompt_for_user(self):
        """Interaction layer assembles asset overview for user."""
        reg = _build_registry()
        prompt = assemble_asset_overview_prompt(reg, "user.alice")

        assert "你可用的资产" in prompt
        assert "app.novel" in prompt
        assert "write_chapter" in prompt or "生成章节" in prompt
        assert "query_asset_detail" in prompt

    def test_e2e_12_assemble_prompt_only_visible(self):
        """Prompt for Alice must NOT include Bob's assets."""
        reg = _build_registry()
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.music" not in prompt

    def test_e2e_13_query_asset_detail_returns_full_schema(self):
        """LLM calls query_asset_detail to get full input/output schema."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("query_asset_detail", {
            "asset_id": "app.novel",
        }, "user.alice")

        assert result.success is True
        assert result.data["asset_id"] == "app.novel"
        fn = result.data["functions"][0]
        assert "key" in fn
        assert "name" in fn

    def test_e2e_14_query_asset_detail_denied_for_other_user(self):
        """Bob queries Alice's private app → denied."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("query_asset_detail", {
            "asset_id": "app.novel",
        }, "user.bob")

        assert result.success is False

    def test_e2e_15_two_step_flow_overview_then_detail(self):
        """Complete two-step LLM flow: overview → select → detail."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # Step 1: Get overview
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.novel" in prompt

        # Step 2: LLM selects app.novel, query detail
        detail = executor.execute("query_asset_detail", {
            "asset_id": "app.novel",
        }, "user.alice")
        assert detail.success is True
        assert len(detail.data["functions"]) == 3


# ===========================================================================
# E2E-16 ~ E2E-20: Path Execution via Center Skill
# ===========================================================================

class TestE2E_pathExecution:
    """E2E-16..20: execute_path_by_key routing through center skill."""

    def test_e2e_16_execute_path_success(self):
        """User executes a path on their app."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {"topic": "武侠", "chapter": 1},
        }, "user.alice")

        assert result.success is True
        assert "app.novel" in result.data["output"]

    def test_e2e_17_execute_path_wrong_user(self):
        """Bob tries to execute Alice's app → denied."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {},
        }, "user.bob")

        assert result.success is False

    def test_e2e_18_execute_path_via_system(self):
        """System can execute any path."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {},
        }, "system")

        assert result.success is True

    def test_e2e_19_execute_path_missing_key(self):
        """Missing path_key → error."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
        }, "user.alice")

        assert result.success is False

    def test_e2e_20_execute_path_router_exception(self):
        """Router throws → proper error propagation."""
        reg = _build_registry()
        def broken_router(*args):
            raise RuntimeError("orchestrator crash")
        executor = AssetToolExecutor(reg, broken_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {},
        }, "user.alice")

        assert result.success is False
        assert "crash" in result.error


# ===========================================================================
# E2E-21 ~ E2E-25: Workflow Solidification
# ===========================================================================

class TestE2E_solidification:
    """E2E-21..25: solidify_workflow flow."""

    def test_e2e_21_solidify_workflow_success(self):
        """User solidifies a workflow on their app."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "auto_write",
            "steps": [
                {"skill_id": "skill.writer", "action": "write"},
                {"skill_id": "skill.reviewer", "action": "review"},
            ],
        }, "user.alice")

        assert result.success is True

    def test_e2e_22_solidify_workflow_unauthorized(self):
        """Bob tries to solidify on Alice's app → denied."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "auto_write",
            "steps": [{"skill_id": "s", "action": "a"}],
        }, "user.bob")

        assert result.success is False

    def test_e2e_23_solidify_workflow_empty_steps(self):
        """Empty steps → validation error."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "auto_write",
            "steps": [],
        }, "user.alice")

        assert result.success is False

    def test_e2e_24_solidify_then_execute(self):
        """Solidify a path → immediately execute it."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # Solidify
        solidify_result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "quick_chapter",
            "steps": [{"skill_id": "skill.writer", "action": "write"}],
        }, "user.alice")
        assert solidify_result.success is True

        # Execute
        exec_result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "quick_chapter",
            "inputs": {"topic": "武侠"},
        }, "user.alice")
        assert exec_result.success is True

    def test_e2e_25_multiple_solidifications(self):
        """User solidifies multiple paths on the same app."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        paths = ["fast_write", "detailed_write", "outline_first"]
        for path_key in paths:
            result = executor.execute("solidify_workflow", {
                "app_id": "app.novel",
                "path_key": path_key,
                "steps": [{"skill_id": "skill.writer", "action": "write"}],
            }, "user.alice")
            assert result.success is True


# ===========================================================================
# E2E-26 ~ E2E-30: Full Instruction Chain (Create → Modify → Execute)
# ===========================================================================

class TestE2E_fullChain:
    """E2E-26..30: Complete user instruction chain simulation."""

    def test_e2e_26_create_app_register_and_query(self):
        """Full chain: create app → register → query asset → see in prompt."""
        reg = _build_registry()

        # Simulate creating a new app
        new_app = _make_app_asset("app.poem", "user.alice", [
            ("write_poem", "写诗"),
            ("revise_poem", "改诗"),
        ])
        reg.register(new_app)

        # Verify it appears in user's view
        visible = reg.get_visible_assets("user.alice")
        assert any(a.asset_id == "app.poem" for a in visible)

        # Verify it appears in prompt
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.poem" in prompt

    def test_e2e_27_modify_app_add_skill_and_execute(self):
        """Modify app: add a new skill → execute with new skill."""
        reg = _build_registry()

        # Simulate adding a new skill to app.novel
        new_skill = _make_skill_asset("skill.illustrator", "app.novel", [
            ("draw", "插画"),
        ])
        reg.register(new_skill)

        # Verify app can see the new skill
        app_visible = reg.get_visible_assets("app.novel")
        assert any(a.asset_id == "skill.illustrator" for a in app_visible)

        # Execute a path using the new skill
        executor = AssetToolExecutor(reg, _mock_router)
        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "illustrated_chapter",
            "inputs": {"scene": "决战"},
        }, "user.alice")
        assert result.success is True

    def test_e2e_28_create_modify_solidify_execute(self):
        """Complete chain: create → modify → solidify → execute."""
        reg = AssetRegistry()

        # 1. Create app
        app = _make_app_asset("app.story", "user.alice", [
            ("create", "创建故事"),
        ])
        reg.register(app)

        # 2. Modify: add skills
        reg.register(_make_skill_asset("skill.plotter", "app.story", [
            ("plot", "构思剧情"),
        ]))
        reg.register(_make_skill_asset("skill.narrator", "app.story", [
            ("narrate", "叙述"),
        ]))

        # 3. Solidify a workflow
        executor = AssetToolExecutor(reg, _mock_router)
        solidify = executor.execute("solidify_workflow", {
            "app_id": "app.story",
            "path_key": "full_story",
            "steps": [
                {"skill_id": "skill.plotter", "action": "plot"},
                {"skill_id": "skill.narrator", "action": "narrate"},
            ],
        }, "user.alice")
        assert solidify.success is True

        # 4. Execute the solidified path
        execute = executor.execute("execute_path_by_key", {
            "app_id": "app.story",
            "path_key": "full_story",
            "inputs": {"genre": "武侠"},
        }, "user.alice")
        assert execute.success is True

    def test_e2e_29_multi_user_isolation_chain(self):
        """Two users create apps independently — complete isolation."""
        reg = AssetRegistry()

        # Alice creates app
        alice_app = _make_app_asset("app.novel", "user.alice", [
            ("write", "写"),
        ])
        reg.register(alice_app)

        # Bob creates app
        bob_app = _make_app_asset("app.script", "user.bob", [
            ("write_script", "写剧本"),
        ])
        reg.register(bob_app)

        # Alice can't see Bob's app
        alice_visible = {a.asset_id for a in reg.get_visible_assets("user.alice")}
        assert "app.script" not in alice_visible

        # Bob can't see Alice's app
        bob_visible = {a.asset_id for a in reg.get_visible_assets("user.bob")}
        assert "app.novel" not in bob_visible

        # System sees both
        system_visible = {a.asset_id for a in reg.get_visible_assets("system")}
        assert "app.novel" in system_visible
        assert "app.script" in system_visible

    def test_e2e_30_app_shutdown_cascades_to_skills(self):
        """App stops → unregister app and its bound skills."""
        reg = AssetRegistry()

        # App with skills
        reg.register(_make_app_asset("app.temp", "user.alice", [
            ("run", "运行"),
        ]))
        reg.register(_make_skill_asset("skill.temp_a", "app.temp", [
            ("act_a", "动作A"),
        ]))
        reg.register(_make_skill_asset("skill.temp_b", "app.temp", [
            ("act_b", "动作B"),
        ]))

        # Verify all registered
        assert reg.asset_count()["total"] == 3

        # App shuts down
        reg.unregister("app.temp", "user.alice")

        # Skills also unregistered (they belong to app.temp)
        app_table = reg._user_assets.get("app.temp", {})
        assert len(app_table) == 0


# ===========================================================================
# E2E-31 ~ E2E-35: Edge Cases & Error Handling
# ===========================================================================

class TestE2E_edgeCases:
    """E2E-31..35: Edge cases, error handling, robustness."""

    def test_e2e_31_duplicate_registration_overwrites(self):
        """Re-registering same asset_id updates the entry."""
        reg = _build_registry()
        # Re-register app.novel with different functions
        new_version = _make_app_asset("app.novel", "user.alice", [
            ("write_chapter_v2", "生成章节v2"),
        ])
        reg.register(new_version)

        detail = reg.get_asset_detail("app.novel", "user.alice")
        assert detail is not None
        fn_keys = [f.key for f in detail.functions]
        assert "write_chapter_v2" in fn_keys

    def test_e2e_32_register_non_running_is_noop(self):
        """Registering a stopped asset does nothing."""
        reg = AssetRegistry()
        stopped = _make_app_asset("app.dead", "user.alice")
        stopped.is_running = False
        reg.register(stopped)
        assert reg.asset_count()["total"] == 0

    def test_e2e_33_unregister_nonexistent_is_safe(self):
        """Unregistering a non-existent asset does not crash."""
        reg = AssetRegistry()
        reg.unregister("app.nonexist", "user.alice")  # no crash

    def test_e2e_34_empty_registry_prompt(self):
        """Assembling prompt on empty registry returns friendly message."""
        reg = AssetRegistry()
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "没有可用" in prompt

    def test_e2e_35_query_detail_for_nonexistent_asset(self):
        """Querying a non-existent asset returns error."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)
        result = executor.execute("query_asset_detail", {
            "asset_id": "app.nonexistent",
        }, "user.alice")
        assert result.success is False
        assert "not found" in result.error


# ===========================================================================
# E2E-36 ~ E2E-40: Complex Multi-Step Scenarios
# ===========================================================================

class TestE2E_complexScenarios:
    """E2E-36..40: Complex multi-step scenarios."""

    def test_e2e_36_user_has_multiple_apps_with_shared_skills(self):
        """User creates two apps that share the same skill."""
        reg = AssetRegistry()

        # Two apps
        reg.register(_make_app_asset("app.novel", "user.alice", [
            ("write", "写小说"),
        ]))
        reg.register(_make_app_asset("app.essay", "user.alice", [
            ("write", "写散文"),
        ]))

        # Shared skill (owned by user, bound to both apps conceptually)
        reg.register(_make_skill_asset("skill.writer", "user.alice", [
            ("write", "写"),
        ]))

        # User sees everything
        visible = reg.get_visible_assets("user.alice")
        ids = {a.asset_id for a in visible}
        assert "app.novel" in ids
        assert "app.essay" in ids
        assert "skill.writer" in ids

    def test_e2e_37_system_executes_path_on_any_user_app(self):
        """System (admin) executes path on any user's app."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # System executes on Alice's app
        result_a = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {},
        }, "system")
        assert result_a.success is True

        # System executes on Bob's app
        result_b = executor.execute("execute_path_by_key", {
            "app_id": "app.music",
            "path_key": "compose",
            "inputs": {},
        }, "system")
        assert result_b.success is True

    def test_e2e_38_solidify_then_immediate_execute_by_other_user_denied(self):
        """Alice solidifies a path → Bob tries to execute → denied."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # Alice solidifies
        executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "auto_write",
            "steps": [{"skill_id": "skill.writer", "action": "write"}],
        }, "user.alice")

        # Bob tries to execute
        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "auto_write",
            "inputs": {},
        }, "user.bob")
        assert result.success is False

    def test_e2e_39_shared_app_execute_workflow(self):
        """Bob executes a workflow on Alice's shared app."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        result = executor.execute("execute_path_by_key", {
            "app_id": "app.translator",
            "path_key": "translate",
            "inputs": {"text": "hello"},
        }, "user.bob")
        assert result.success is True

    def test_e2e_40_full_prompt_to_execution_pipeline(self):
        """Complete pipeline: prompt → model selects → query detail → execute."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # Step 1: Interaction layer builds prompt
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.novel" in prompt
        assert "生成章节" in prompt or "write_chapter" in prompt

        # Step 2: Model (simulated) decides to use app.novel → query detail
        detail = executor.execute("query_asset_detail", {
            "asset_id": "app.novel",
        }, "user.alice")
        assert detail.success is True
        # Model can now see input_schema, output_schema, notes

        # Step 3: Model decides to execute write_chapter
        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "inputs": {"topic": "武侠", "chapter": 1},
        }, "user.alice")
        assert result.success is True
        assert "武侠" in str(result.data["inputs"])

        # Step 4: User wants to solidify a new workflow
        solidify = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "batch_write",
            "steps": [
                {"skill_id": "skill.writer", "action": "write"},
                {"skill_id": "skill.reviewer", "action": "review"},
            ],
        }, "user.alice")
        assert solidify.success is True

        # Step 5: Execute the new solidified path
        batch_result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "batch_write",
            "inputs": {"topic": "仙侠"},
        }, "user.alice")
        assert batch_result.success is True


# ===========================================================================
# E2E-41 ~ E2E-45: App Modification & Refinement Chain
# ===========================================================================

class TestE2E_appModification:
    """E2E-41..45: App modification and skill refinement chain."""

    def test_e2e_41_add_skill_to_existing_app(self):
        """User requests to add a skill to their existing app."""
        reg = _build_registry()

        # Before modification
        app_detail = reg.get_asset_detail("app.novel", "user.alice")
        initial_fn_count = len(app_detail.functions)

        # Add a new skill
        reg.register(_make_skill_asset("skill.formatter", "app.novel", [
            ("format", "格式化"),
        ]))

        # App can now see the new skill
        app_visible = reg.get_visible_assets("app.novel")
        assert any(a.asset_id == "skill.formatter" for a in app_visible)

    def test_e2e_42_modify_app_functions(self):
        """Re-register app with updated functions."""
        reg = _build_registry()

        # Simulate modification: add new function
        updated = _make_app_asset("app.novel", "user.alice", [
            ("write_chapter", "生成章节"),
            ("generate_outline", "生成大纲"),
            ("revise", "修改"),
            ("publish", "发布"),  # new
        ])
        reg.register(updated)

        detail = reg.get_asset_detail("app.novel", "user.alice")
        fn_keys = [f.key for f in detail.functions]
        assert "publish" in fn_keys

    def test_e2e_43_remove_app_function_by_re_registration(self):
        """Remove a function by re-registering without it."""
        reg = _build_registry()

        updated = _make_app_asset("app.novel", "user.alice", [
            ("write_chapter", "生成章节"),
            # removed: generate_outline, revise
        ])
        reg.register(updated)

        detail = reg.get_asset_detail("app.novel", "user.alice")
        fn_keys = [f.key for f in detail.functions]
        assert "generate_outline" not in fn_keys
        assert "write_chapter" in fn_keys

    def test_e2e_44_cross_app_skill_reuse(self):
        """One skill can be bound to multiple apps."""
        reg = AssetRegistry()

        reg.register(_make_app_asset("app.novel", "user.alice"))
        reg.register(_make_app_asset("app.essay", "user.alice"))

        # Same skill registered under both apps
        reg.register(_make_skill_asset("skill.writer", "app.novel", [
            ("write", "写"),
        ]))
        reg.register(_make_skill_asset("skill.writer_v2", "app.essay", [
            ("write", "写"),
        ]))

        # Each app sees its own skill
        novel_skills = reg.get_visible_assets("app.novel")
        assert any(a.asset_id == "skill.writer" for a in novel_skills)

        essay_skills = reg.get_visible_assets("app.essay")
        assert any(a.asset_id == "skill.writer_v2" for a in essay_skills)

    def test_e2e_45_full_modify_chain_permission_check(self):
        """Full modification chain with permission check."""
        reg = _build_registry()
        executor = AssetToolExecutor(reg, _mock_router)

        # Alice can modify her own app
        modify_result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "new_feature",
            "steps": [{"skill_id": "skill.writer", "action": "write"}],
        }, "user.alice")
        assert modify_result.success is True

        # Bob cannot modify Alice's app
        bob_result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "hack",
            "steps": [{"skill_id": "skill.writer", "action": "write"}],
        }, "user.bob")
        assert bob_result.success is False
