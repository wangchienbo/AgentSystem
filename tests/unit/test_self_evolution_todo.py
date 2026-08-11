"""Tests for the observation/todo integration in SelfEvolutionService.

Verifies that run_periodic_review snapshots the converged todo backlog
(when a SelfDevService is injected) and that get_evolution_history surfaces
the todo trend.
"""

from __future__ import annotations

from app.system.self_dev import SelfDevService
from app.system.self_evolution import SelfEvolutionService


def test_run_periodic_review_snapshot_includes_todo(tmp_path) -> None:
    history_path = str(tmp_path / "evolution_history.json")
    dev = SelfDevService(root_dir="app", processed_path=str(tmp_path / "processed.json"))
    evo = SelfEvolutionService(history_path=history_path, dev=dev, interval_seconds=0)

    result = evo.run_periodic_review(force=True)
    assert result["skipped"] is False
    todo = result["todo"]
    assert todo["available"] is True
    assert todo["queue_count"] == todo["queue_count"]  # 结构字段存在
    assert isinstance(todo["queue"], list)

    # 快照已持久化 todo 字段
    history = evo._load_history()
    assert history, "快照应已写入"
    assert "todo" in history[-1]
    assert history[-1]["todo"]["available"] is True


def test_run_periodic_review_without_dev_is_backward_compatible(tmp_path) -> None:
    """未注入 dev 时快照仍正常，todo 标记不可用（向后兼容）。"""
    evo = SelfEvolutionService(history_path=str(tmp_path / "h.json"), interval_seconds=0)
    result = evo.run_periodic_review(force=True)
    assert result["skipped"] is False
    assert result["todo"]["available"] is False
    assert result["todo"]["queue_count"] == 0


def test_evolution_history_surfaces_todo_trend(tmp_path) -> None:
    history_path = str(tmp_path / "h.json")
    dev = SelfDevService(root_dir="app", processed_path=str(tmp_path / "processed.json"))
    evo = SelfEvolutionService(history_path=history_path, dev=dev, interval_seconds=0)

    evo.run_periodic_review(force=True)
    hist = evo.get_evolution_history(limit=10)
    assert hist["series"], "应有演进曲线数据点"
    assert "todo_queue_count" in hist["series"][0]
    assert "processed_decisions_count" in hist["series"][0]
    assert "todo" in hist["latest"]
