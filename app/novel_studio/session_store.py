"""Novel Studio — 会话元数据存储

管理每个用户在每个小说下的多个会话（session）。
每个 session 有独立的 session_id，关联 ContextCenter 中的会话节点。

数据文件：~/.local/share/agentsystem/data/novel_studio/sessions.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import resolve_runtime_paths

logger = __import__("logging").getLogger(__name__)

SESSION_FILE = resolve_runtime_paths().data_dir / "novel_studio" / "sessions.json"


class SessionStore:
    """会话元数据存储引擎"""

    def __init__(self, file_path: str | Path | None = None):
        self._path = Path(file_path) if file_path else SESSION_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = {}  # username -> {novel_id -> {sessions...}}
        self._load()

    # ──── 内部 IO ────

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ──── 用户/小说 命名空间 ────

    def _ensure_novel(self, username: str, novel_id: str) -> dict:
        """确保返回 {current, sessions} 结构"""
        if username not in self._data:
            self._data[username] = {}
        if novel_id not in self._data[username]:
            self._data[username][novel_id] = {
                "current": None,
                "sessions": {},
            }
        return self._data[username][novel_id]

    # ──── 会话 CRUD ────

    def list_sessions(self, username: str, novel_id: str) -> list[dict]:
        """返回该用户在该小说下的所有会话摘要"""
        ns = self._ensure_novel(username, novel_id)
        current = ns.get("current")
        result = []
        for sid, meta in ns.get("sessions", {}).items():
            result.append({
                "session_uuid": sid,
                "label": meta.get("label", ""),
                "created_at": meta.get("created_at", ""),
                "last_active": meta.get("last_active", ""),
                "msg_count": meta.get("msg_count", 0),
                "is_current": sid == current,
            })
        # 按 last_active 降序
        result.sort(key=lambda x: x.get("last_active", ""), reverse=True)
        return result

    def get_current_session(self, username: str, novel_id: str) -> str | None:
        """返回当前的 session_uuid"""
        ns = self._ensure_novel(username, novel_id)
        return ns.get("current")

    def create_session(self, username: str, novel_id: str, label: str = "") -> str:
        """创建新会话，设为当前"""
        ns = self._ensure_novel(username, novel_id)
        session_uuid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        ns["sessions"][session_uuid] = {
            "label": label or f"对话{len(ns['sessions']) + 1}",
            "created_at": now,
            "last_active": now,
            "msg_count": 0,
        }
        ns["current"] = session_uuid
        self._save()
        return session_uuid

    def switch_session(self, username: str, novel_id: str, session_uuid: str) -> bool:
        """切换到已有会话"""
        ns = self._ensure_novel(username, novel_id)
        if session_uuid not in ns.get("sessions", {}):
            return False
        ns["current"] = session_uuid
        ns["sessions"][session_uuid]["last_active"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def delete_session(self, username: str, novel_id: str, session_uuid: str) -> bool:
        """删除会话"""
        ns = self._ensure_novel(username, novel_id)
        if session_uuid not in ns.get("sessions", {}):
            return False
        del ns["sessions"][session_uuid]
        # 如果删的是当前会话，重设 current 为最新或 None
        if ns.get("current") == session_uuid:
            remaining = list(ns["sessions"].keys())
            ns["current"] = remaining[0] if remaining else None
        self._save()
        return True

    def touch_session(self, username: str, novel_id: str, session_uuid: str):
        """更新会话活动时间 + 消息计数"""
        ns = self._data.get(username, {}).get(novel_id)
        if ns and session_uuid in ns.get("sessions", {}):
            ns["sessions"][session_uuid]["last_active"] = datetime.now(timezone.utc).isoformat()
            ns["sessions"][session_uuid]["msg_count"] = ns["sessions"][session_uuid].get("msg_count", 0) + 1
            self._save()
