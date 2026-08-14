"""每日饮水提醒助手 — App Worker 实现

MasterControl 可调度的 App Worker。
收到任务后在独立线程执行，通过 callback 报告结果，
通过 get_progress 实时反馈进度。
数据用本地 JSON 文件持久化，读写用线程锁保护。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Callable

from app.system.master.master_control import TaskRecord, AppWorkerProtocol

logger = logging.getLogger(__name__)

# 默认数据目录：~/.local/share/agentsystem/data/apps/water_reminder/
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "agentsystem" / "data" / "apps" / "water_reminder"
WATER_FILE = DEFAULT_DATA_DIR / "water.json"


# ── operation → (required_params, 中文说明) ─────────────────────────
OPERATIONS: dict[str, tuple[list[str], str]] = {
    "set_water_reminder":  (["interval_min", "remind_at"], "设置每日饮水目标/提醒（interval_min 或 remind_at 二选一）"),
    "log_water_intake":    (["ml"], "记录一次饮水（ml 为毫升数）"),
    "query_today":         ([], "查看今日饮水进度"),
    "cancel_water_reminder": ([], "取消饮水提醒"),
}


class WaterReminderWorker(AppWorkerProtocol):
    """每日饮水提醒助手 Worker——本地 JSON 持久化，线程锁保护"""

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "water.json"
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()

    # ── 数据持久化 ──────────────────────────────────────────────
    def _load(self) -> dict:
        """加载配置与今日记录，结构：
        {"daily_target_ml": 2000, "remind_at": "09:00", "interval_min": 120,
         "records": {"2026-08-13": [{"ml": 250, "at": "08:30"}]}}
        """
        with self._lock:
            if not self._file.exists():
                return {"daily_target_ml": 2000, "remind_at": "", "interval_min": None,
                        "records": {}}
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                return {"daily_target_ml": 2000, "remind_at": "", "interval_min": None,
                        "records": {}}

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
        logger.info("WaterReminderWorker execute task=%s op=%s params=%s",
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
            logger.exception("WaterReminderWorker task %s failed", task_id)
            callback(task_id, "failed", error=str(e))

    def _do_execute(self, task_id: str, operation: str, params: dict) -> dict:
        """按操作分发（支持操作名别名/大小写/连字符归一）"""
        op = operation.lower().replace(" ", "_").replace("-", "_")
        op_map = {
            "set_water_reminder": "set_water_reminder", "set_reminder": "set_water_reminder",
            "set_water_target": "set_water_reminder", "设置饮水提醒": "set_water_reminder",
            "设置饮水目标": "set_water_reminder",
            "log_water_intake": "log_water_intake", "log_water": "log_water_intake",
            "log_intake": "log_water_intake", "drink": "log_water_intake",
            "记录饮水": "log_water_intake", "喝水": "log_water_intake",
            "record_water": "log_water_intake", "add_water": "log_water_intake",
            "record_intake": "log_water_intake", "add_water_record": "log_water_intake",
            "log": "log_water_intake", "add": "log_water_intake", "记录": "log_water_intake",
            "record": "log_water_intake", "饮水记录": "log_water_intake", "喝水记录": "log_water_intake",
            "query_today": "query_today", "today": "query_today", "progress": "query_today",
            "query_progress": "query_today", "今日进度": "query_today", "查看进度": "query_today",
            "query_water_records": "query_today", "query_records": "query_today",
            "query_water": "query_today", "get_records": "query_today",
            "get_water_records": "query_today", "list_records": "query_today",
            "查询饮水": "query_today", "查看饮水": "query_today", "饮水记录": "query_today",
            "查询记录": "query_today", "查看记录": "query_today", "查记录": "query_today",
            "status": "query_today", "query": "query_today", "查询": "query_today", "查看": "query_today",
            "cancel_water_reminder": "cancel_water_reminder", "cancel_reminder": "cancel_water_reminder",
            "取消提醒": "cancel_water_reminder",
        }
        canonical = op_map.get(op, op)

        today = date.today().isoformat()

        if canonical == "set_water_reminder":
            self._set_progress(task_id, 30, "正在设置饮水提醒...")
            data = self._load()
            interval_min = params.get("interval_min")
            remind_at = str(params.get("remind_at", "")).strip()
            if interval_min is not None and interval_min != "":
                try:
                    data["interval_min"] = int(interval_min)
                except (TypeError, ValueError):
                    raise ValueError(f"interval_min 必须是分钟数，收到: {interval_min}")
            if remind_at:
                data["remind_at"] = remind_at
            if data.get("interval_min") is None and not data.get("remind_at"):
                raise ValueError("缺少必要参数：请提供 interval_min（间隔分钟）或 remind_at（提醒时间）")
            target = params.get("daily_target_ml")
            if target is not None and target != "":
                try:
                    data["daily_target_ml"] = int(target)
                except (TypeError, ValueError):
                    raise ValueError(f"daily_target_ml 必须是毫升数，收到: {target}")
            self._save(data)
            self._set_progress(task_id, 100, "饮水提醒已设置")
            return {"success": True, "daily_target_ml": data["daily_target_ml"],
                    "remind_at": data.get("remind_at", ""), "interval_min": data.get("interval_min")}

        elif canonical == "log_water_intake":
            self._set_progress(task_id, 30, "正在记录饮水...")
            # LLM 参数名不稳定：兼容 ml / amount_ml / amount / volume 等常见键
            ml = None
            for key in ("ml", "amount_ml", "amount", "volume", "volume_ml", "water_ml", "milliliters", "饮水毫升"):
                v = params.get(key)
                if v is not None and v != "":
                    ml = v
                    break
            if ml is None:
                raise ValueError("缺少必要参数 ml（毫升数）")
            try:
                ml_val = float(ml)
            except (TypeError, ValueError):
                raise ValueError(f"ml 必须是数字，收到: {ml}")
            # 单位换算：unit 为「升/L」时乘以 1000
            unit = str(params.get("unit", "")).lower()
            if unit in ("升", "l", "liter", "liters"):
                ml_val = ml_val * 1000
            ml_val = int(round(ml_val))
            if ml_val <= 0:
                raise ValueError("ml 必须为正数")
            data = self._load()
            records = data.setdefault("records", {})
            today_records = records.setdefault(today, [])
            today_records.append({"ml": ml_val, "at": datetime.now().strftime("%H:%M")})
            self._save(data)
            drunk = sum(r["ml"] for r in today_records)
            target = data.get("daily_target_ml", 2000)
            self._set_progress(task_id, 100, "饮水已记录")
            return {"success": True, "ml": ml_val, "today_drunk": drunk,
                    "daily_target_ml": target, "remaining": max(0, target - drunk)}

        elif canonical == "query_today":
            self._set_progress(task_id, 40, "正在读取今日进度...")
            data = self._load()
            records = data.get("records", {}).get(today, [])
            drunk = sum(r["ml"] for r in records)
            target = data.get("daily_target_ml", 2000)
            self._set_progress(task_id, 100, "读取完成")
            return {"success": True, "date": today, "daily_target_ml": target,
                    "today_drunk": drunk, "remaining": max(0, target - drunk),
                    "records": records, "remind_at": data.get("remind_at", ""),
                    "interval_min": data.get("interval_min")}

        elif canonical == "cancel_water_reminder":
            self._set_progress(task_id, 30, "正在取消饮水提醒...")
            data = self._load()
            data["remind_at"] = ""
            data["interval_min"] = None
            self._save(data)
            self._set_progress(task_id, 100, "已取消提醒")
            return {"success": True, "message": "饮水提醒已取消"}

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
