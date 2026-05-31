"""Novel Studio — 生成任务管理器（内存缓冲）

为后台管道执行提供任务队列和结果缓冲，
使得 HTTP 请求断开后管道仍可继续执行，
用户重新打开页面后可拉取结果。
"""

import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class GenerateTask:
    """一个管道生成任务"""

    def __init__(self, novel_id: str, template: str):
        self.id: str = uuid.uuid4().hex[:12]
        self.novel_id: str = novel_id
        self.template: str = template
        self.status: str = "pending"  # pending → running → complete | error
        self.events: list[dict[str, Any]] = []  # 缓冲的所有事件
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at: datetime = datetime.now(timezone.utc)

    def to_dict(self, from_event_index: int = 0) -> dict[str, Any]:
        """序列化（支持按事件索引偏移返回新事件）"""
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "template": self.template,
            "status": self.status,
            "events": self.events[from_event_index:],
            "total_events": len(self.events),
            "has_result": self.result is not None,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


# ─── 内存存储（进程级） ───

_tasks: dict[str, GenerateTask] = {}
_novel_latest: dict[str, str] = {}  # novel_id → latest task_id


def create_task(novel_id: str, template: str = "write_next_chapter") -> GenerateTask:
    """创建新任务"""
    task = GenerateTask(novel_id, template)
    _tasks[task.id] = task
    _novel_latest[novel_id] = task.id
    logger.info("Task created: %s for novel %s (template=%s)", task.id, novel_id, template)
    return task


def get_task(task_id: str) -> GenerateTask | None:
    """获取任务"""
    return _tasks.get(task_id)


def get_latest_task(novel_id: str) -> GenerateTask | None:
    """获取某小说最新的任务"""
    tid = _novel_latest.get(novel_id)
    if tid:
        return _tasks.get(tid)
    return None


def cleanup_old_tasks(max_age_seconds: int = 3600):
    """清理过期任务"""
    now = datetime.now(timezone.utc)
    to_remove = []
    for tid, task in _tasks.items():
        age = (now - task.created_at).total_seconds()
        if age > max_age_seconds:
            to_remove.append(tid)
    for tid in to_remove:
        t = _tasks.pop(tid, None)
        if t and _novel_latest.get(t.novel_id) == tid:
            del _novel_latest[t.novel_id]
    if to_remove:
        logger.info("Cleaned %d old tasks", len(to_remove))
