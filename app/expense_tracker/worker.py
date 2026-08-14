"""个人财务记账助手 — App Worker 实现

MasterControl 可调度的 App Worker。
收到任务后在独立线程执行，通过 callback 报告结果，
通过 get_progress 实时反馈进度。
数据用本地 JSON 文件持久化，读写用线程锁保护。
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.system.master.master_control import TaskRecord, AppWorkerProtocol

logger = logging.getLogger(__name__)

# 默认数据目录：~/.local/share/agentsystem/data/apps/expense_tracker/
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "agentsystem" / "data" / "apps" / "expense_tracker"
EXPENSES_FILE = DEFAULT_DATA_DIR / "expenses.json"


# ── operation → (required_params, 中文说明) ─────────────────────────
OPERATIONS: dict[str, tuple[list[str], str]] = {
    "add_expense":     (["amount"], "记一笔账（amount 必填，category/note 可带）"),
    "list_expenses":   ([], "查看账目列表"),
    "monthly_total":   (["month"], "统计某月支出合计（month 如 2026-08）"),
    "delete_expense":  (["expense_id"], "删除一笔账目"),
}


class ExpenseTrackerWorker(AppWorkerProtocol):
    """个人财务记账助手 Worker——本地 JSON 持久化，线程锁保护"""

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "expenses.json"
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()

    # ── 数据持久化 ──────────────────────────────────────────────
    def _load(self) -> dict:
        """加载全部流水，结构：{"expenses": {expense_id: {...}}}"""
        with self._lock:
            if not self._file.exists():
                return {"expenses": {}}
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                return {"expenses": {}}

    def _save(self, data: dict) -> None:
        with self._lock:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── 任务进度 ────────────────────────────────────────────────
    def _set_progress(self, task_id: str, pct: int, msg: str):
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["progress_pct"] = pct
                self._tasks[task_id]["progress_msg"] = msg

    # ── AppWorkerProtocol ───────────────────────────────────────
    def execute(self, task_id: str, operation: str,
                params: dict, callback: Callable) -> None:
        """异步执行操作，完成后调 callback"""
        logger.info("ExpenseTrackerWorker execute task=%s op=%s params=%s",
                    task_id, operation, params)

        with self._tasks_lock:
            self._tasks[task_id] = {
                "status": "running",
                "progress_pct": 0,
                "progress_msg": "准备中...",
            }

        try:
            result = self._do_execute(task_id, operation, params)
            callback(task_id, "done", result=result)
        except Exception as e:
            logger.exception("ExpenseTrackerWorker task %s failed", task_id)
            callback(task_id, "failed", error=str(e))

    def _do_execute(self, task_id: str, operation: str, params: dict) -> dict:
        """按操作分发（支持操作名别名/大小写/连字符归一）"""
        op = operation.lower().replace(" ", "_").replace("-", "_")
        op_map = {
            "add_expense": "add_expense", "add": "add_expense", "record": "add_expense",
            "record_expense": "add_expense", "add_transaction": "add_expense", "transaction": "add_expense",
            "record_transaction": "add_expense", "记账": "add_expense", "记一笔账": "add_expense",
            "记一笔": "add_expense", "记支出": "add_expense", "记消费": "add_expense",
            "list_expenses": "list_expenses", "list": "list_expenses", "get_expenses": "list_expenses",
            "show_expenses": "list_expenses", "query_expenses": "list_expenses", "query": "list_expenses",
            "query_records": "list_expenses", "expense_list": "list_expenses", "查看账目": "list_expenses",
            "账目列表": "list_expenses", "我的账本": "list_expenses", "账本": "list_expenses",
            "支出记录": "list_expenses", "收支记录": "list_expenses", "最近支出": "list_expenses", "查账": "list_expenses",
            "monthly_total": "monthly_total", "month_total": "monthly_total",
            "monthly_sum": "monthly_total", "统计": "monthly_total", "月支出": "monthly_total",
            "delete_expense": "delete_expense", "remove_expense": "delete_expense",
            "del_expense": "delete_expense", "删除账目": "delete_expense",
        }
        canonical = op_map.get(op, op)

        if canonical == "add_expense":
            self._set_progress(task_id, 30, "正在写入账目...")
            amount = params.get("amount")
            if amount is None or amount == "":
                raise ValueError("缺少必要参数 amount（金额）")
            try:
                amount_val = float(amount)
            except (TypeError, ValueError):
                raise ValueError(f"amount 必须是数字，收到: {amount}")
            category = str(params.get("category", "")).strip() or "未分类"
            note = str(params.get("note", "")).strip()
            data = self._load()
            expense_id = f"exp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
            data["expenses"][expense_id] = {
                "id": expense_id,
                "amount": amount_val,
                "category": category,
                "note": note,
                "created_at": datetime.now().isoformat(),
            }
            self._save(data)
            self._set_progress(task_id, 100, "账目已记录")
            return {"success": True, "expense_id": expense_id, "amount": amount_val,
                    "category": category, "note": note}

        elif canonical == "list_expenses":
            self._set_progress(task_id, 40, "正在读取账目列表...")
            data = self._load()
            expenses = list(data["expenses"].values())
            expenses.sort(key=lambda e: e.get("created_at", ""), reverse=True)
            self._set_progress(task_id, 100, "读取完成")
            return {"success": True, "count": len(expenses), "expenses": expenses}

        elif canonical == "monthly_total":
            self._set_progress(task_id, 40, "正在统计月度支出...")
            month = str(params.get("month", "")).strip()
            if not month:
                raise ValueError("缺少必要参数 month（如 2026-08）")
            data = self._load()
            total = 0.0
            items = []
            for e in data["expenses"].values():
                created = e.get("created_at", "")
                if created.startswith(month):
                    total += float(e.get("amount", 0))
                    items.append(e)
            self._set_progress(task_id, 100, "统计完成")
            return {"success": True, "month": month, "total": round(total, 2),
                    "count": len(items), "expenses": items}

        elif canonical == "delete_expense":
            self._set_progress(task_id, 30, "正在删除账目...")
            expense_id = str(params.get("expense_id", "")).strip()
            if not expense_id:
                raise ValueError("缺少必要参数 expense_id")
            data = self._load()
            expense = data["expenses"].pop(expense_id, None)
            if expense is None:
                raise ValueError(f"账目不存在: {expense_id}")
            self._save(data)
            self._set_progress(task_id, 100, "已删除")
            return {"success": True, "expense_id": expense_id,
                    "amount": expense.get("amount"), "category": expense.get("category")}

        raise ValueError(f"不支持的操作: {operation}")

    def get_task(self, task_id: str) -> TaskRecord:
        with self._tasks_lock:
            t = self._tasks.get(task_id)
            if not t:
                return TaskRecord(task_id=task_id, status="unknown")
            return TaskRecord(
                task_id=task_id,
                status=t.get("status", "unknown"),
                progress_pct=t.get("progress_pct", 0),
                progress_msg=t.get("progress_msg", ""),
            )

    def get_progress(self, task_id: str) -> dict:
        """查询任务当前进度：{"pct", "msg", "status"}"""
        with self._tasks_lock:
            t = self._tasks.get(task_id)
            if not t:
                return {"pct": 0, "msg": "任务不存在", "status": "unknown"}
            return {
                "pct": t.get("progress_pct", 0),
                "msg": t.get("progress_msg", ""),
                "status": t.get("status", "running"),
            }
