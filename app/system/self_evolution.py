"""
self_evolution.py — 自治开发的「长期进化」层（Phase 3）

基于 diagnose_codebase 周期性做代码健康审查，并把每次审查的**健康度快照**
持久化到磁盘。跨会话可对比历史，观察代码健康度随时间演进
（长期进化：God Object 数量是否下降、导入缺陷是否清零等）。

核心能力：
  1. run_periodic_review — 周期性代码审查（默认 24h 间隔；force 强制重跑）
     输出本次快照：导入缺陷数、God Object 数、top 问题、与上次的趋势对比
  2. get_evolution_history — 读取历史审查记录，展示演进曲线数据
  3. reset_history — 清空演进历史（可选）

设计原则：
  - 独立关注点=独立模块（不塞进 diagnose/propose）
  - 只读诊断复用 SelfDiagnosisService；唯一副作用是写审查历史 JSON
  - 不自动改代码——长期进化的观察记录，改进仍需走 propose + 人类审批
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from app.system.self_diagnosis import SelfDiagnosisService

DEFAULT_REVIEW_INTERVAL_SECONDS = 24 * 60 * 60  # 每天一次


class SelfEvolutionService:
    def __init__(
        self,
        diagnosis: SelfDiagnosisService | None = None,
        history_path: str | None = None,
        interval_seconds: int = DEFAULT_REVIEW_INTERVAL_SECONDS,
        dev: "SelfDevService | None" = None,
    ) -> None:
        self._diagnosis = diagnosis or SelfDiagnosisService(root_dir="app")
        self._dev = dev
        self._history_path = history_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "evolution_history.json"
        )
        self._interval_seconds = interval_seconds
        os.makedirs(os.path.dirname(self._history_path), exist_ok=True)

    # ── 历史读写 ─────────────────────────────────
    def _load_history(self) -> list[dict[str, Any]]:
        if not os.path.exists(self._history_path):
            return []
        try:
            data = json.loads(open(self._history_path).read())
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _append_snapshot(self, snapshot: dict[str, Any]) -> None:
        history = self._load_history()
        history.append(snapshot)
        # 保留最近 200 条，避免无限增长
        history = history[-200:]
        tmp = self._history_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._history_path)

    def _last_review_time(self) -> datetime | None:
        history = self._load_history()
        if not history:
            return None
        last_ts = history[-1].get("reviewed_at")
        if not last_ts:
            return None
        try:
            return datetime.fromisoformat(last_ts)
        except ValueError:
            return None

    # ── 演进计算 ─────────────────────────────────
    def _compute_trend(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        history = self._load_history()
        if len(history) < 2:
            return {"available": False}
        prev = history[-2]
        counts_now = snapshot.get("counts", {})
        counts_prev = prev.get("counts", {})
        return {
            "available": True,
            "god_objects_delta": counts_now.get("god_objects", 0) - counts_prev.get("god_objects", 0),
            "import_defects_delta": counts_now.get("import_defects", 0) - counts_prev.get("import_defects", 0),
            "prev_reviewed_at": prev.get("reviewed_at"),
        }

    # ── 公开能力 ─────────────────────────────────
    def run_periodic_review(self, *, force: bool = False) -> dict[str, Any]:
        """周期性代码健康审查。未到间隔且非 force 时跳过（返回 skipped）。"""
        now = datetime.now(UTC)
        if not force:
            last = self._last_review_time()
            if last is not None and (now - last).total_seconds() < self._interval_seconds:
                return {
                    "skipped": True,
                    "reason": f"未到审查间隔（上次 {last.isoformat()}，间隔 {self._interval_seconds}s）",
                    "last_reviewed_at": last.isoformat(),
                }

        diagnosis = self._diagnosis.diagnose_codebase(include_god_objects=True)
        snapshot = {
            "reviewed_at": now.isoformat(timespec="seconds"),
            "counts": diagnosis.get("counts", {}),
            "import_defects": diagnosis.get("import_defects", []),
            "god_objects": diagnosis.get("god_objects", []),
            "top_problems": self._top_problems(diagnosis),
            "todo": self._snapshot_todo(diagnosis),
        }
        self._append_snapshot(snapshot)
        trend = self._compute_trend(snapshot)
        return {
            "skipped": False,
            "reviewed_at": snapshot["reviewed_at"],
            "counts": snapshot["counts"],
            "top_problems": snapshot["top_problems"],
            "todo": snapshot["todo"],
            "trend": trend,
            "history_size": len(self._load_history()),
        }

    def _snapshot_todo(self, diagnosis: dict[str, Any]) -> dict[str, Any]:
        """记录收敛后的自动待办统计（打通观察层与待办闭环）。

        依赖注入的 SelfDevService（dev）生成已过滤已裁决目标的 todo_queue，
        使快照可持久化待办数随时间的收敛。dev 未注入时返回空统计（向后兼容）。
        """
        if self._dev is None:
            return {"available": False, "queue_count": 0, "processed_count": 0}
        report = self._dev.build_dev_report(diagnosis)
        return {
            "available": True,
            "queue_count": report.get("todo_queue_count", 0),
            "processed_count": report.get("filtered_processed_count", 0),
            "queue": [
                {"file": t.get("file"), "target": t.get("target"), "refactorability": t.get("refactorability")}
                for t in report.get("todo_queue", [])
            ],
        }

    @staticmethod
    def _top_problems(diagnosis: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        """提取最值得关注的 top 问题（按规模排序的 God Object + 导入缺陷）。"""
        god_objects = sorted(
            diagnosis.get("god_objects", []),
            key=lambda g: g.get("size_lines", 0),
            reverse=True,
        )
        top = [
            {
                "kind": g.get("kind"),
                "file": g.get("file"),
                "name": g.get("name", g.get("line")),
                "size_lines": g.get("size_lines"),
            }
            for g in god_objects[:limit]
        ]
        for d in diagnosis.get("import_defects", [])[:limit]:
            top.append({
                "kind": d.get("kind"),
                "file": d.get("file"),
                "module": d.get("module"),
                "name": d.get("name"),
            })
        return top[:limit]

    def get_evolution_history(self, *, limit: int = 20) -> dict[str, Any]:
        """读取演进历史：健康度随时间的演变（供系统对比长期进化）。"""
        history = self._load_history()
        history = history[-limit:]
        series = [
            {
                "reviewed_at": s.get("reviewed_at"),
                "god_objects": s.get("counts", {}).get("god_objects", 0),
                "import_defects": s.get("counts", {}).get("import_defects", 0),
                "todo_queue_count": s.get("todo", {}).get("queue_count", 0),
                "processed_decisions_count": s.get("todo", {}).get("processed_count", 0),
            }
            for s in history
        ]
        latest = history[-1] if history else None
        return {
            "history_size": len(history),
            "series": series,
            "latest": {
                "reviewed_at": latest.get("reviewed_at"),
                "counts": latest.get("counts", {}),
                "todo": latest.get("todo", {}),
            } if latest else None,
        }

    def reset_history(self) -> dict[str, Any]:
        """清空演进历史（可选运维操作）。"""
        if os.path.exists(self._history_path):
            os.remove(self._history_path)
        return {"reset": True, "history_size": 0}
