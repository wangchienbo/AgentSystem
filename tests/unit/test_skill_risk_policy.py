from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.runtime_state_store import RuntimeStateStore
from app.services.skill_risk_policy import SkillRiskPolicyService


def test_skill_risk_policy_approve_list_revoke_and_reload(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "skill-risk-policy"))
    service = SkillRiskPolicyService(store=store)

    approved = service.approve_override(
        skill_id="skill.risky.demo",
        reviewer="tester",
        reason="approved for generated app assembly",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert approved.skill_id == "skill.risky.demo"
    assert service.get_active_override("skill.risky.demo") is not None
    assert len(service.list_decisions()) == 1

    reloaded = SkillRiskPolicyService(store=store)
    assert reloaded.get_active_override("skill.risky.demo") is not None

    revoked = reloaded.revoke_override("skill.risky.demo", reviewer="tester", reason="rollback approval")
    assert revoked.decision == "revoked"
    assert reloaded.get_active_override("skill.risky.demo") is None
