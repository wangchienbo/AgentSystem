from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_registry import AppRegistryService
from app.services.runtime_state_store import RuntimeStateStore


client = TestClient(app)


def build_blueprint(
    execution_mode: str = "service",
    *,
    blueprint_id: str = "bp.test.registry",
    name: str = "Registry Test App",
) -> AppBlueprint:
    return AppBlueprint(
        id=blueprint_id,
        name=name,
        goal="verify registry and installer",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.test", "name": "test", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=[],
        runtime_policy={
            "execution_mode": execution_mode,
            "activation": "on_demand",
            "restart_policy": "on_failure",
            "persistence_level": "standard",
            "idle_strategy": "suspend",
        },
    )


def test_registry_overview_service_filters_and_ordering(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "overview-store"))
    registry = AppRegistryService(store=store)

    alpha = build_blueprint(blueprint_id="bp.alpha", name="Alpha App")
    beta = build_blueprint(blueprint_id="bp.beta", name="Beta App")
    gamma = build_blueprint(blueprint_id="bp.gamma", name="Gamma App")

    registry.register_blueprint(alpha)
    registry.register_blueprint(beta)
    registry.register_blueprint(gamma)

    registry.add_release("bp.alpha", "0.2.0", note="draft alpha")
    registry.add_release("bp.beta", "0.2.0", note="promote beta")
    registry.activate_release("bp.beta", "0.2.0", reviewer="ops")
    registry.rollback_release("bp.beta", "0.1.0", reviewer="ops", rollback_reason="regression")

    overview = registry.get_registry_overview()
    assert overview.total_apps == 3
    assert overview.apps_with_drafts == 1
    assert overview.apps_with_rollbacks == 1
    assert overview.apps_with_rollback_targets == 0
    assert overview.release_status_counts["active"] == 3
    assert overview.shape_counts["generic"] == 3
    assert overview.items[0].blueprint_id == "bp.alpha"
    assert overview.items[0].attention_needed is True
    assert {item.blueprint_id for item in overview.items} == {"bp.alpha", "bp.beta", "bp.gamma"}

    draft_only = registry.get_registry_overview(has_draft=True)
    assert draft_only.total_apps == 1
    assert draft_only.items[0].blueprint_id == "bp.alpha"

    rollback_only = registry.get_registry_overview(rollback_available=False, limit=2)
    assert rollback_only.total_apps == 2
    assert len(rollback_only.items) == 2


def test_registry_attention_summary_service(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "attention-store"))
    registry = AppRegistryService(store=store)

    alpha = build_blueprint(blueprint_id="bp.attn.alpha", name="Alpha Attention")
    beta = build_blueprint(blueprint_id="bp.attn.beta", name="Beta Attention")
    gamma = build_blueprint(blueprint_id="bp.attn.gamma", name="Gamma Attention")

    registry.register_blueprint(alpha)
    registry.register_blueprint(beta)
    registry.register_blueprint(gamma)

    registry.add_release("bp.attn.alpha", "0.2.0", note="needs review")
    registry.add_release("bp.attn.beta", "0.2.0", note="promote")
    registry.activate_release("bp.attn.beta", "0.2.0", reviewer="ops")
    registry.rollback_release("bp.attn.beta", "0.1.0", reviewer="ops", rollback_reason="issue")
    registry.add_release("bp.attn.gamma", "0.2.0", note="promote")
    registry.activate_release("bp.attn.gamma", "0.2.0", reviewer="ops")

    attention = registry.get_attention_summary()
    assert attention.total_attention_items == 3
    assert attention.draft_attention_count == 1
    assert attention.rollback_target_count == 1
    assert attention.recently_rolled_back_count == 1
    assert attention.items[0].blueprint_id == "bp.attn.alpha"
    assert attention.items[0].attention_reason == "draft_release"
    assert {item.blueprint_id for item in attention.items} == {"bp.attn.alpha", "bp.attn.beta", "bp.attn.gamma"}
    assert any(item.attention_reason == "recently_rolled_back" and item.blueprint_id == "bp.attn.beta" for item in attention.items)
    assert any(item.attention_reason == "rollback_target_available" and item.blueprint_id == "bp.attn.gamma" for item in attention.items)

    limited_attention = registry.get_attention_summary(limit=1)
    assert limited_attention.total_attention_items == 1
    assert len(limited_attention.items) == 1


def test_registry_operator_surface_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.api.registry",
            "name": "API Registry App",
            "goal": "registry api flow",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [{"id": "wf.api", "name": "api flow", "triggers": ["manual"], "steps": []}],
            "views": [],
            "required_modules": ["state.get"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive",
            },
        },
    )
    assert register_response.status_code == 200

    draft_release = client.post(
        "/registry/apps/bp.api.registry/releases",
        json={"version": "0.2.0", "note": "staged rollout", "reviewer": "alice", "activate_immediately": False},
    )
    assert draft_release.status_code == 200

    activated = client.post(
        "/registry/apps/bp.api.registry/releases/0.2.0/activate",
        json={"reviewer": "bob"},
    )
    assert activated.status_code == 200

    summary_after_activate = client.get("/registry/apps/bp.api.registry/summary")
    assert summary_after_activate.status_code == 200
    summary_after_activate_payload = summary_after_activate.json()
    assert summary_after_activate_payload["active_version"] == "0.2.0"
    assert summary_after_activate_payload["rollback_available"] is True

    overview_after_activate = client.get("/registry/apps/overview")
    assert overview_after_activate.status_code == 200
    overview_after_activate_payload = overview_after_activate.json()
    registry_item = next(item for item in overview_after_activate_payload["items"] if item["blueprint_id"] == "bp.api.registry")
    assert registry_item["active_version"] == "0.2.0"
    assert registry_item["attention_needed"] is True

    attention_after_activate = client.get("/registry/apps/attention")
    assert attention_after_activate.status_code == 200
    attention_after_activate_payload = attention_after_activate.json()
    attention_item = next(item for item in attention_after_activate_payload["items"] if item["blueprint_id"] == "bp.api.registry")
    assert attention_item["attention_reason"] == "rollback_target_available"

    rolled_back = client.post(
        "/registry/apps/bp.api.registry/rollback",
        json={"target_version": "0.1.0", "reviewer": "carol", "rollback_reason": "staged release regression"},
    )
    assert rolled_back.status_code == 200

    summary_after_rollback = client.get("/registry/apps/bp.api.registry/summary")
    assert summary_after_rollback.status_code == 200
    summary_after_rollback_payload = summary_after_rollback.json()
    assert summary_after_rollback_payload["active_version"] == "0.1.0"
    assert summary_after_rollback_payload["rolled_back_release_count"] == 1
    assert summary_after_rollback_payload["rollback_available"] is False
    assert summary_after_rollback_payload["reviewer"] == "carol"

    overview_after_rollback = client.get("/registry/apps/overview", params={"rollback_available": False, "limit": 10})
    assert overview_after_rollback.status_code == 200
    overview_after_rollback_payload = overview_after_rollback.json()
    registry_item_after_rollback = next(item for item in overview_after_rollback_payload["items"] if item["blueprint_id"] == "bp.api.registry")
    assert registry_item_after_rollback["rollback_available"] is False
    assert registry_item_after_rollback["rolled_back_release_count"] == 1

    attention_after_rollback = client.get("/registry/apps/attention")
    assert attention_after_rollback.status_code == 200
    attention_after_rollback_payload = attention_after_rollback.json()
    attention_item_after_rollback = next(item for item in attention_after_rollback_payload["items"] if item["blueprint_id"] == "bp.api.registry")
    assert attention_item_after_rollback["attention_reason"] == "recently_rolled_back"
