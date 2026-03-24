from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.services.runtime_state_store import RuntimeStateStore
from app.services.skill_risk_policy import SkillRiskPolicyService


client = TestClient(app)


def test_skill_risk_policy_stats_and_dashboard_service_view(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "skill-risk-dashboard"))
    service = SkillRiskPolicyService(store=store)

    service.record_event(skill_id="skill.a", event_type="policy_blocked", reason="blocked by default policy")
    service.approve_override(skill_id="skill.a", reviewer="tester", reason="allow for controlled assembly")
    service.revoke_override(skill_id="skill.a", reviewer="tester", reason="close window")

    stats = service.get_stats_summary()
    dashboard = service.get_dashboard(recent_limit=2)

    assert stats.total_decisions == 1
    assert stats.total_events >= 3
    assert stats.blocked_events >= 1
    assert stats.approved_events >= 1
    assert stats.revoked_events >= 1
    assert dashboard.stats.total_events >= 3
    assert dashboard.recent_events.meta.returned_count == 2
    assert dashboard.recent_events.meta.has_more is True


def test_skill_risk_dashboard_api_surface() -> None:
    stats = client.get("/skill-risk/stats")
    assert stats.status_code == 200
    stats_payload = stats.json()
    assert stats_payload["total_decisions"] >= 0
    assert stats_payload["total_events"] >= 0

    dashboard = client.get("/skill-risk/dashboard", params={"recent_limit": 2})
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["overview"]["active_policy"] == "default_deny_with_override"
    assert "stats" in payload
    assert "recent_events" in payload
    assert "meta" in payload["recent_events"]
