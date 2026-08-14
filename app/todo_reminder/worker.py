"""待办事项提醒 — App Worker 实现

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
from typing import Any, Callable

from app.system.master.master_control import TaskRecord, AppWorkerProtocol

logger = logging.getLogger(__name__)

# 默认数据目录：~/.local/share/agentsystem/data/apps/todo_reminder/
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "agentsystem" / "data" / "apps" / "todo_reminder"
TODOS_FILE = DEFAULT_DATA_DIR / "todos.json"


# ── operation → (required_params, 中文说明) ─────────────────────────
OPERATIONS: dict[str, tuple[list[str], str]] = {
    "add_todo":        (["title"], "新增待办"),
    "list_todos":      ([], "查看待办列表"),
    "complete_todo":   (["todo_id"], "标记待办完成"),
    "delete_todo":     (["todo_id"], "删除待办"),
}


class TodoReminderWorker(AppWorkerProtocol):
    """待办事项提醒 Worker——本地 JSON 持久化，线程锁保护"""

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "todos.json"
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()

    # ── 数据持久化 ──────────────────────────────────────────────
    def _load(self) -> dict:
        """加载全部待办，结构：{"todos": {todo_id: {...}}}"""
        with self._lock:
            if not self._file.exists():
                return {"todos": {}}
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                return {"todos": {}}

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
        logger.info("TodoReminderWorker execute task=%s op=%s params=%s",
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
            logger.exception("TodoReminderWorker task %s failed", task_id)
            callback(task_id, "failed", error=str(e))

    def _do_execute(self, task_id: str, operation: str, params: dict) -> dict:
        """按操作分发（支持操作名别名/大小写/连字符归一）"""
        op = operation.lower().replace(" ", "_").replace("-", "_")
        op_map = {
            "add_todo": "add_todo", "add": "add_todo", "create_todo": "add_todo",
            "new_todo": "add_todo", "新增待办": "add_todo",
            "list_todos": "list_todos", "list": "list_todos", "get_todos": "list_todos",
            "show_todos": "list_todos", "查看待办": "list_todos", "待办列表": "list_todos",
            "complete_todo": "complete_todo", "done_todo": "complete_todo",
            "finish_todo": "complete_todo", "complete": "complete_todo",
            "标记完成": "complete_todo",
            "delete_todo": "delete_todo", "remove_todo": "delete_todo",
            "del_todo": "delete_todo", "删除待办": "delete_todo",
        }
        canonical = op_map.get(op, op)

        if canonical == "add_todo":
            self._set_progress(task_id, 30, "正在写入待办...")
            title = str(params.get("title", "")).strip()
            if not title:
                raise ValueError("缺少必要参数 title（待办内容）")
            remind_at = params.get("remind_at", "")
            data = self._load()
            todo_id = f"todo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
            data["todos"][todo_id] = {
                "id": todo_id,
                "title": title,
                "remind_at": remind_at,
                "done": False,
                "created_at": datetime.now().isoformat(),
            }
            self._save(data)
            self._set_progress(task_id, 100, "待办已添加")
            return {"success": True, "todo_id": todo_id, "title": title,
                    "remind_at": remind_at}

        elif canonical == "list_todos":
            self._set_progress(task_id, 40, "正在读取待办列表...")
            data = self._load()
            todos = list(data["todos"].values())
            todos.sort(key=lambda t: t.get("created_at", ""))
            self._set_progress(task_id, 100, "读取完成")
            return {"success": True, "count": len(todos), "todos": todos}

        elif canonical == "complete_todo":
            self._set_progress(task_id, 30, "正在标记完成...")
            todo_id = str(params.get("todo_id", "")).strip()
            if not todo_id:
                raise ValueError("缺少必要参数 todo_id")
            data = self._load()
            todo = data["todos"].get(todo_id)
            if not todo:
                raise ValueError(f"待办不存在: {todo_id}")
            todo["done"] = True
            todo["completed_at"] = datetime.now().isoformat()
            self._save(data)
            self._set_progress(task_id, 100, "已标记完成")
            return {"success": True, "todo_id": todo_id, "title": todo["title"],
                    "done": True}

        elif canonical == "delete_todo":
            self._set_progress(task_id, 30, "正在删除待办...")
            todo_id = str(params.get("todo_id", "")).strip()
            if not todo_id:
                raise ValueError("缺少必要参数 todo_id")
            data = self._load()
            todo = data["todos"].pop(todo_id, None)
            if todo is None:
                raise ValueError(f"待办不存在: {todo_id}")
            self._save(data)
            self._set_progress(task_id, 100, "已删除")
            return {"success": True, "todo_id": todo_id, "title": todo["title"]}

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
