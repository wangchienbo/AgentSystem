from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.system.invocation.tool_context_contract import ModelInvocationRecord


class ModelInvocationStore:
    """Phase P 3.5: In-memory store for model invocation recording."""

    def __init__(self) -> None:
        self._records: list[ModelInvocationRecord] = []

    def record(self, record: ModelInvocationRecord) -> ModelInvocationRecord:
        self._records.append(record)
        return record

    def get_by_request_id(self, request_id: str) -> ModelInvocationRecord | None:
        for record in reversed(self._records):
            if record.request_id == request_id:
                return record
        return None

    def list_by_session(self, asset_id: str, local_session_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            r.to_dict()
            for r in self._records
            if r.asset_id == asset_id and r.local_session_id == local_session_id
        ][-limit:]

    def aggregate_token_usage(self, *, asset_id: str | None = None, local_session_id: str | None = None) -> dict[str, Any]:
        records = self._records
        if asset_id is not None:
            records = [r for r in records if r.asset_id == asset_id]
        if local_session_id is not None:
            records = [r for r in records if r.local_session_id == local_session_id]
        prompt = sum((r.token_usage or {}).get("prompt_tokens", 0) for r in records)
        completion = sum((r.token_usage or {}).get("completion_tokens", 0) for r in records)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "invocation_count": len(records),
        }
