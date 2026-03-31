from app.services.requirement_clarifier import RequirementClarifierService


service = RequirementClarifierService()


def test_detects_local_vs_network_conflict() -> None:
    spec = service.clarify("做一个应用，要求本地离线运行，但必须联网拉取实时数据并直接输出")

    assert spec.readiness == "conflicting_constraints"
    assert "conflict_resolution" in spec.missing_fields
    assert any("本地执行和联网依赖" in note for note in spec.notes)



def test_detects_automation_vs_manual_approval_conflict() -> None:
    spec = service.clarify("做一个审批流程，要求自动执行所有步骤，但关键节点必须人工审批")

    assert spec.readiness == "conflicting_constraints"
    assert any("自动执行和人工审批" in note for note in spec.notes)
