from __future__ import annotations

from app.services.context_summary_worker import ContextSummaryWorker
from app.services.summary_prompt_policy import SummaryPromptPolicy


def test_summary_prompt_policy_short_record_is_near_verbatim() -> None:
    policy = SummaryPromptPolicy(short_record_threshold=50)

    prompt = policy.build_prompt(record_text="fixed gateway timeout and verified reply path")

    assert "Short record mode" in prompt
    assert "near-verbatim" in prompt
    assert "Do not invent facts" in prompt
    assert "Do not inflate attempts into confirmations" in prompt
    assert "Do not inflate partial work into completed work" in prompt


def test_summary_prompt_policy_long_record_is_result_focused() -> None:
    policy = SummaryPromptPolicy(short_record_threshold=10)

    prompt = policy.build_prompt(record_text="this is a longer record that should switch into summary mode with result focus")

    assert "Long record mode" in prompt
    assert "what was done" in prompt
    assert "what the result was" in prompt


def test_context_summary_worker_centralizes_prompt_construction(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)

    prompt = worker.build_summary_prompt("implemented stable pending flush behavior")

    assert "Source record:" in prompt
    assert "Do not invent facts" in prompt
