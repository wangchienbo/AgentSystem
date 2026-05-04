from __future__ import annotations


def repo_located_message(repo_path: str, readme_path: str) -> str:
    return f"repo_located repo_path={repo_path} readme_path={readme_path}"


def target_file_identified_message(target_path: str) -> str:
    return f"target_file_identified path={target_path}"


def upgrade_path_determined_message(steps: list[str], rollback_hint: str) -> str:
    joined_steps = " | ".join(steps)
    return f"upgrade_path_determined steps={joined_steps} rollback_hint={rollback_hint}"


def acceptance_result_message(status: str, summary: str) -> str:
    return f"acceptance_result status={status} summary={summary}"
