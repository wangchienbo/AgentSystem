"""LifecycleEventStore — lifecycle_events 的 JSONL 流式持久化。

设计动机（2026-08-15 架构整改）：
旧实现把 lifecycle_events 作为"内存全量状态"加载，每次 transition 全量序列化
到单个 JSON 文件。事件无限累积后（曾到 62 万条/326MB），每次 stop/start 都会
全量序列化，触发 OOM kill；文件非原子写入还会在进程中断时损坏。

新设计（对齐 context_writer 的 JSONL 模式）：
- 按 App 分目录、按天分文件追加写入（lifecycle_events/{app_id}/{date}.jsonl）
- 内存只保留每个 App 最近 N 条（调用方控制），历史查询按需走磁盘
- 追加是 O(1) 的流式写入，不随事件总量膨胀
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.runtime_paths import resolve_runtime_paths

# 默认：每个 App 在内存 / 恢复时保留的事件条数
DEFAULT_MEMORY_EVENT_LIMIT = 50


class LifecycleEventStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is not None:
            self.base_path = Path(base_dir)
        else:
            self.base_path = resolve_runtime_paths().state_dir / "runtime" / "lifecycle_events"
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _app_dir(self, app_instance_id: str) -> Path:
        return self.base_path / app_instance_id

    def _day_file(self, app_instance_id: str, timestamp: datetime) -> Path:
        return self._app_dir(app_instance_id) / f"{timestamp.astimezone(UTC).date().isoformat()}.jsonl"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append_event(self, app_instance_id: str, event: Any) -> None:
        """流式追加一条事件到当天 JSONL 文件（O(1)，不随总量膨胀）。"""
        day_file = self._day_file(app_instance_id, event.created_at)
        day_file.parent.mkdir(parents=True, exist_ok=True)
        with day_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def append_raw(self, app_instance_id: str, payload: dict, *, created_at: datetime | None = None) -> None:
        """追加一条已序列化的原始事件（迁移/工具用）。"""
        ts = created_at or datetime.now(UTC)
        day_file = self._day_file(app_instance_id, ts)
        day_file.parent.mkdir(parents=True, exist_ok=True)
        with day_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_events(
        self,
        app_instance_id: str,
        *,
        limit: int | None = None,
        include_history: bool = False,
        event_model=None,
    ) -> list[Any]:
        """读取某 App 的事件。

        include_history=False（默认）：返回最近 limit 条（按文件/行序倒排取尾部）。
        include_history=True：返回全量历史（按时间正序）。
        返回 pydantic 模型（event_model 提供时），否则返回原始 dict。
        """
        app_dir = self._app_dir(app_instance_id)
        if not app_dir.exists():
            return []
        events = self._read_all(app_dir, event_model=event_model)
        if not include_history and limit is not None and len(events) > limit:
            events = events[-limit:]
        return events

    def load_all_recent(self, *, limit: int = DEFAULT_MEMORY_EVENT_LIMIT, event_model=None) -> dict[str, list[Any]]:
        """启动恢复用：返回每个 App 最近 limit 条事件。"""
        result: dict[str, list[Any]] = {}
        for app_dir in sorted(self.base_path.iterdir()):
            if not app_dir.is_dir():
                continue
            events = self._read_all(app_dir, event_model=event_model)
            if events:
                result[app_dir.name] = events[-limit:]
        return result

    def list_app_ids(self) -> list[str]:
        return sorted(p.name for p in self.base_path.iterdir() if p.is_dir())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_all(self, app_dir: Path, *, event_model=None) -> list[Any]:
        events: list[Any] = []
        for day_file in sorted(app_dir.glob("*.jsonl")):
            try:
                with day_file.open(encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if event_model is not None:
                            try:
                                events.append(event_model.model_validate(raw))
                                continue
                            except Exception:
                                pass
                        events.append(raw)
            except OSError:
                continue
        return events
