from __future__ import annotations

import asyncio

from app.services.external_model_review import ExternalModelReviewService, ExternalModelReviewWorker
from app.system.master.master_control import MasterControl


class _FakeReviewService(ExternalModelReviewService):
    def __init__(self) -> None:
        pass

    def review_plan(self, prompt: str, context=None):
        class _R:
            action = "review_plan"
            model = "qwen3.6-plus"
            source = "openai_qwen3_6plus"
            content = f"PLAN::{prompt}::{context.get('scope') if context else ''}"
        return _R()

    def review_code(self, prompt: str, context=None):
        class _R:
            action = "review_code"
            model = "qwen3.6-plus"
            source = "openai_qwen3_6plus"
            content = f"CODE::{prompt}::{context.get('file') if context else ''}"
        return _R()


def test_master_control_routes_external_review_plan() -> None:
    master = MasterControl()
    master.register_worker("external_review", ExternalModelReviewWorker(_FakeReviewService()))

    result = asyncio.run(master.execute(
        operation="external_review_plan",
        user_id="u1",
        user_role="user",
        params={"prompt": "评审方案A", "context": {"scope": "design"}},
    ))

    assert result["status"] == "success"
    assert result["data"]["action"] == "review_plan"
    assert result["data"]["model"] == "qwen3.6-plus"
    assert "PLAN::评审方案A::design" in result["data"]["content"]


def test_master_control_routes_external_review_code() -> None:
    master = MasterControl()
    master.register_worker("external_review", ExternalModelReviewWorker(_FakeReviewService()))

    result = asyncio.run(master.execute(
        operation="external_review_code",
        user_id="u1",
        user_role="user",
        params={"prompt": "评审补丁B", "context": {"file": "app.py"}},
    ))

    assert result["status"] == "success"
    assert result["data"]["action"] == "review_code"
    assert result["data"]["source"] == "openai_qwen3_6plus"
    assert "CODE::评审补丁B::app.py" in result["data"]["content"]
