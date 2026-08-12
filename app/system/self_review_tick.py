"""SelfReviewTickDriver — 固化「周期代码审查」自动线路。

自治进化模块的 run_periodic_review 虽有"24h 间隔"语义，但此前**没有任何调度器
周期调用它**——这条固化线路是断的，只能靠人手动/LLM 对话触发。

本驱动用 daemon 线程周期 tick `SelfIterationAssetService.run_periodic_review()`。
run_periodic_review 内部自带 24h 间隔判断（未到间隔立即返回 skipped、不调 LLM），
因此本驱动只需用小间隔（默认 1h）周期唤醒，真正的审查由服务内部节制，安全且轻量。

参考 RegressionNightlyTickDriver（http_test_server）的 daemon 线程模式。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class SelfReviewTickDriver:
    """周期唤醒自治进化的代码健康审查。"""

    def __init__(self, service: Any) -> None:
        self._service = service
        self._interval_seconds = 3600
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_result: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running and self._thread is not None and self._thread.is_alive(),
            "interval_seconds": self._interval_seconds,
            "thread_alive": self._thread is not None and self._thread.is_alive(),
            "last_result": self._last_result,
        }

    def start(self, *, interval_seconds: int = 3600) -> dict[str, Any]:
        self._interval_seconds = max(60, interval_seconds)
        if self._thread is not None and self._thread.is_alive():
            self._running = True
            return self.status()
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="self-review-tick", daemon=True)
        self._thread.start()
        logger.info("SelfReviewTickDriver started, interval=%ss", self._interval_seconds)
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._running = False
        self._stop_event.set()
        logger.info("SelfReviewTickDriver stopped")
        return self.status()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                result = self._service.run_periodic_review()
                self._last_result = {
                    "skipped": result.get("skipped", False),
                    "reviewed_at": result.get("reviewed_at") or result.get("last_reviewed_at"),
                    "history_size": result.get("history_size"),
                    "todo": result.get("todo"),
                    "trend": result.get("trend"),
                }
                logger.info(
                    "SelfReviewTickDriver periodic review: skipped=%s reviewed_at=%s",
                    result.get("skipped"),
                    result.get("reviewed_at") or result.get("last_reviewed_at"),
                )
            except Exception as error:  # noqa: BLE001 - 周期任务必须吞异常防线程退出
                logger.warning("SelfReviewTickDriver periodic review failed: %s", error)
