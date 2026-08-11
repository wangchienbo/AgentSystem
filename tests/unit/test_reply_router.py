"""PreReplyRouter 单测 — 决策层框架 + ReplayPolicy 不变量。"""
from __future__ import annotations

import pytest

from app.context.reply_decision import (
    PreReplyRouter,
    ReplayPolicy,
    ReplyContext,
    ReplyDecision,
    is_user_asking_task_result,
)


class FakeTask:
    """最小 PendingTaskRecord 替身（仅 ReplayPolicy 需要的字段）。"""

    def __init__(self, task_id="t1", status="completed"):
        self.task_id = task_id
        self.status = status

    def model_dump(self, mode="json"):
        return {"task_id": self.task_id, "status": self.status}


class FakeGateway:
    """最小 gateway 替身，提供 ReplayPolicy 依赖的接口。"""

    def __init__(self, closed_task=None, already_replayed=False):
        self._closed_task = closed_task
        self._already_replayed = already_replayed
        self.replay_formatted = None

    def _get_latest_closed_task(self, user_id):
        return self._closed_task

    def _format_replay_content(self, task):
        self.replay_formatted = task
        return f"REPLAY:{task.task_id}"

    def was_replayed(self, session_id, task_id):
        return self._already_replayed

    def mark_replayed(self, session_id, task_id):
        self.marked = (session_id, task_id)


def ctx(gateway, message, pending_task=None):
    return ReplyContext(
        message=message, session_id="s1", user_id="u1",
        pending_task=pending_task, gateway=gateway,
    )


# ---------------------------------------------------------------------------
# is_user_asking_task_result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("你好", False),
    ("25乘以4等于多少", False),
    ("把 hello 翻译成中文", False),
    ("帮我写一首诗", False),
    ("什么是Agent", False),
    ("上次任务结果怎么样了", True),
    ("我上一个任务进展如何", True),
    ("之前那个事办得怎么样了", True),
    ("", False),
    (None, False),
])
def test_is_user_asking_task_result(msg, expected):
    assert is_user_asking_task_result(msg) is expected


# ---------------------------------------------------------------------------
# ReplayPolicy 不变量
# ---------------------------------------------------------------------------

def test_replay_policy_pass_when_not_asking():
    """不变量：非询问请求（寒暄/计算/翻译）绝不回放、绝不放行给回放。"""
    g = FakeGateway(closed_task=FakeTask())  # 即使有 closed task
    for msg in ["你好", "25乘以4等于多少", "把 hello 翻译成中文", "帮我写一首诗"]:
        d = ReplayPolicy().evaluate(ctx(g, msg))
        assert d.outcome == "pass_through", f"{msg} 不应回放"


def test_replay_policy_short_when_asking_with_closed_task():
    g = FakeGateway(closed_task=FakeTask())
    d = ReplayPolicy().evaluate(ctx(g, "上次任务结果怎么样了"))
    assert d.outcome == "short_circuit"
    assert g.marked == ("s1", "t1")
    assert d.response is not None


def test_replay_policy_pass_when_no_closed_task():
    g = FakeGateway(closed_task=None)
    d = ReplayPolicy().evaluate(ctx(g, "上次任务结果怎么样了"))
    assert d.outcome == "pass_through"


def test_replay_policy_pass_when_already_replayed():
    g = FakeGateway(closed_task=FakeTask(), already_replayed=True)
    d = ReplayPolicy().evaluate(ctx(g, "上次任务结果怎么样了"))
    assert d.outcome == "pass_through"


def test_replay_policy_pass_when_pending_task_exists():
    """有进行中任务时不回放（任务延续接管）。"""
    g = FakeGateway(closed_task=FakeTask())
    d = ReplayPolicy().evaluate(ctx(g, "上次任务结果怎么样了", pending_task=FakeTask("pt")))
    assert d.outcome == "pass_through"


def test_replay_policy_pass_when_gateway_none():
    c = ReplyContext(message="上次任务结果", session_id="s", user_id="u", gateway=None)
    assert ReplayPolicy().evaluate(c).outcome == "pass_through"


# ---------------------------------------------------------------------------
# PreReplyRouter
# ---------------------------------------------------------------------------

def test_router_pass_through_when_no_policy_short_circuits():
    g = FakeGateway(closed_task=None)
    r = PreReplyRouter()
    d = r.decide(ctx(g, "上次任务结果怎么样了"))
    assert d.outcome == "pass_through"


def test_router_short_circuits_replay():
    g = FakeGateway(closed_task=FakeTask())
    r = PreReplyRouter()
    d = r.decide(ctx(g, "上次任务结果怎么样了"))
    assert d.outcome == "short_circuit"
    assert d.response is not None


def test_router_priority_order():
    """低 priority（先评估）策略优先短路。"""

    class First(ReplayPolicy):
        priority = 100
        name = "first"

        def evaluate(self, ctx):
            return ReplyDecision("short_circuit", response="FIRST", reason="first")

    class Second(ReplayPolicy):
        priority = 300
        name = "second"

        def evaluate(self, ctx):
            return ReplyDecision("short_circuit", response="SECOND", reason="second")

    r = PreReplyRouter([Second(), First()])  # 乱序传入
    assert [p.name for p in r.policies] == ["first", "second"]
    d = r.decide(ctx(FakeGateway(), "你好"))
    assert d.response == "FIRST"
