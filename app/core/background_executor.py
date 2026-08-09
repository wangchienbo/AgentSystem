"""BackgroundExecutor — 后台执行器。

接收 PendingTaskRecord，在独立线程中执行，更新状态。
用户重连后回放结果。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from app.models.pending_task import PendingTaskRecord

logger = logging.getLogger(__name__)


class BackgroundExecutor:
    """后台执行器。

    用法:
        executor = BackgroundExecutor(pending_task_store, orchestrator)
        task_id = executor.submit(pending_task)
        status = executor.get_status(task_id)
    """

    def __init__(
        self,
        pending_task_store: Any = None,
        orchestrator: Any = None,
    ):
        self._store = pending_task_store
        self._orchestrator = orchestrator
        self._threads: dict[str, threading.Thread] = {}
        self._results: dict[str, dict[str, Any]] = {}

    def submit(self, task: PendingTaskRecord) -> str:
        """提交任务到后台执行。

        创建独立 daemon 线程执行，不阻塞调用方。
        """
        if task.task_id in self._threads:
            logger.warning("Task %s already running, skipping", task.task_id)
            return task.task_id

        def _run():
            try:
                self._execute_task(task)
            except Exception as e:
                logger.error("Background task %s failed: %s", task.task_id, e)
                task.status = "failed"
                task.error_message = str(e)
                if self._store:
                    self._store.upsert_task(task)
            finally:
                self._threads.pop(task.task_id, None)

        t = threading.Thread(target=_run, name=f"bg-{task.task_id[:8]}", daemon=True)
        self._threads[task.task_id] = t
        t.start()

        logger.info("Background task submitted: %s (stage=%s)", task.task_id, task.current_stage)
        return task.task_id

    def get_status(self, task_id: str) -> str | None:
        """获取任务状态。"""
        if not self._store:
            return None
        task = self._store.get_task(task_id)
        return task.status if task else None

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """获取任务结果摘要。"""
        return self._results.get(task_id)

    def cancel(self, task_id: str) -> bool:
        """取消正在执行的任务。

        注意：当前实现仅移除线程引用，不强制终止线程。
        """
        if task_id in self._threads:
            del self._threads[task_id]
            logger.info("Background task cancelled: %s", task_id)
            return True
        return False

    def is_running(self, task_id: str) -> bool:
        """检查任务是否仍在执行。"""
        return task_id in self._threads

    def _execute_task(self, task: PendingTaskRecord) -> None:
        """执行任务的主循环。

        通过编排器推进各阶段，直到完成/失败/阻塞。
        """
        task.status = "running"
        if self._store:
            self._store.upsert_task(task)

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # 检查是否被取消
            if task.task_id not in self._threads:
                logger.info("Task %s cancelled, stopping", task.task_id)
                task.status = "abandoned"
                break

            # 用编排器推进
            if self._orchestrator:
                task = self._orchestrator.advance_if_possible(task)

            # 检查状态
            if task.status in ("completed", "failed", "abandoned"):
                break

            next_action = (task.next_recommended_action or {}).get("type", "") if task.next_recommended_action else ""

            # 如果需要用户输入 → 标记阻塞
            if next_action.endswith("_pending") or next_action == "":
                task.stage_status = "blocked"
                if self._store:
                    self._store.upsert_task(task)
                break

            # 正在执行 → 短暂等待后继续
            time.sleep(1)

        # 记录结果摘要
        impl_plan = task.implementation_plan or {}
        acpt_plan = task.acceptance_plan or {}
        self._results[task.task_id] = {
            "task_id": task.task_id,
            "status": task.status,
            "current_stage": task.current_stage,
            "stage_status": task.stage_status,
            "completed_stages": task.completed_stages or [],
            "implemented_files": impl_plan.get("implemented_files", []),
            "summary": impl_plan.get("summary", ""),
            "acceptance_result": acpt_plan.get("evidence_summary", {}),
        }

        if self._store:
            self._store.upsert_task(task)

        logger.info(
            "Background task finished: %s status=%s stage=%s",
            task.task_id, task.status, task.current_stage,
        )
