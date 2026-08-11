"""Tests for the persisted todo-decision convergence loop in SelfDevService.

Verifies that record_todo_decision persists decisions and that build_dev_report
filters already-decided targets out of todo_queue (so periodic reviews stop
re-suggesting targets that were assessed as done / declined).
"""

from __future__ import annotations

from app.system.self_diagnosis import SelfDiagnosisService
from app.system.self_dev import SelfDevService


def _run_diagnosis(root_dir: str) -> dict:
    return SelfDiagnosisService(root_dir=root_dir).diagnose_codebase(include_god_objects=True)


def test_record_then_filter_convergence(tmp_path) -> None:
    """记录裁决后，build_dev_report 的 todo_queue 不再包含该目标；新实例加载同一条记录。"""
    processed = tmp_path / "processed.json"
    dev = SelfDevService(root_dir="app", processed_path=str(processed))

    report = dev.build_dev_report(_run_diagnosis("app"))
    assert report["filtered_processed_count"] == 0
    assert len(report["todo_queue"]) == report["todo_queue_count"]

    # 取第一个待办目标，记录为 declined
    assert report["todo_queue"], "预期诊断能产出一个 high/medium 待办"
    first = report["todo_queue"][0]
    result = dev.record_todo_decision(first["file"], first["target"], status="declined", rationale="评估为高内聚不值得拆")
    assert result["recorded"] is True
    assert result["queue_size"] == 1

    # 同一实例再生成报告：该目标被过滤
    report2 = dev.build_dev_report(_run_diagnosis("app"))
    remaining = [t for t in report2["todo_queue"] if t["file"] == first["file"] and t["target"] == first["target"]]
    assert remaining == [], "已裁决目标不应再出现在 todo_queue"
    assert report2["filtered_processed_count"] >= 1

    # 新实例（模拟跨会话）加载同一条持久化裁决，依然过滤
    dev3 = SelfDevService(root_dir="app", processed_path=str(processed))
    report3 = dev3.build_dev_report(_run_diagnosis("app"))
    remaining3 = [t for t in report3["todo_queue"] if t["file"] == first["file"] and t["target"] == first["target"]]
    assert remaining3 == [], "跨会话加载后仍应过滤已裁决目标"

    # 裁决可列出/可清空
    listed = dev3.list_todo_decisions()
    assert any(d["file"] == first["file"] and d["target"] == first["target"] for d in listed)
    assert dev3.clear_todo_decisions() == 1


def test_record_decision_rejects_invalid_status(tmp_path) -> None:
    dev = SelfDevService(root_dir="app", processed_path=str(tmp_path / "p.json"))
    try:
        dev.record_todo_decision("a.py", "module", status="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("应拒绝非 done/declined 状态")


def test_record_normalizes_root_dir_prefix(tmp_path) -> None:
    """带 root_dir 前缀（app/...）与相对路径应归一为同一条裁决。"""
    processed = tmp_path / "p.json"
    dev = SelfDevService(root_dir="app", processed_path=str(processed))
    dev.record_todo_decision("app/orchestration/workflow_executor.py", "module", status="declined")
    assert dev._normalize_file("app/orchestration/workflow_executor.py") == "orchestration/workflow_executor.py"
    # 相对路径记录也能命中同一条（归一后 key 一致）
    report = dev.build_dev_report(_run_diagnosis("app"))
    matched = [t for t in report["todo_queue"]
               if t["file"] == "orchestration/workflow_executor.py" and t["target"] == "module"]
    assert matched == [], "带前缀记录后，相对路径待办应被过滤"
    assert any(d["file"] == "orchestration/workflow_executor.py" for d in dev.list_todo_decisions())


def test_clear_resets_filter(tmp_path) -> None:
    processed = tmp_path / "processed.json"
    dev = SelfDevService(root_dir="app", processed_path=str(processed))
    report = dev.build_dev_report(_run_diagnosis("app"))
    first = report["todo_queue"][0]
    dev.record_todo_decision(first["file"], first["target"], status="declined")
    assert dev.clear_todo_decisions() == 1

    report2 = dev.build_dev_report(_run_diagnosis("app"))
    remaining = [t for t in report2["todo_queue"] if t["file"] == first["file"] and t["target"] == first["target"]]
    assert remaining, "清空裁决后该目标应重新出现在 todo_queue"
