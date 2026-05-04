from __future__ import annotations

from app.services.high_value_fact_messages import (
    acceptance_result_message,
    repo_located_message,
    target_file_identified_message,
    upgrade_path_determined_message,
)


def test_high_value_fact_templates_are_stable() -> None:
    assert repo_located_message("/root/project/AgentSystem", "/root/project/AgentSystem/README.md") == (
        "repo_located repo_path=/root/project/AgentSystem readme_path=/root/project/AgentSystem/README.md"
    )
    assert target_file_identified_message("app/services/context_center.py") == (
        "target_file_identified path=app/services/context_center.py"
    )
    assert upgrade_path_determined_message(["pytest -q", "restart gateway"], "git checkout -- app/services/context_center.py") == (
        "upgrade_path_determined steps=pytest -q | restart gateway rollback_hint=git checkout -- app/services/context_center.py"
    )
    assert acceptance_result_message("passed", "targeted acceptance checks passed") == (
        "acceptance_result status=passed summary=targeted acceptance checks passed"
    )
