from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ContextAssemblyError(ValueError):
    pass


class ContextAssembly:
    def __init__(self, asset_center_service: Any = None) -> None:
        self._asset_center = asset_center_service

    def refresh(self, asset_center_service: Any = None) -> dict[str, Any]:
        center = asset_center_service or self._asset_center
        if center is None:
            return {}
        summaries = center.list_assets()
        summary_index = {}
        for summary in summaries:
            asset_id = summary.get("asset_id")
            if asset_id:
                detail = center.get_asset_detail(asset_id)
                if isinstance(detail, dict):
                    summary_index[asset_id] = detail
        return {
            "summaries": summaries,
            "summary_index": summary_index,
        }


@dataclass(frozen=True)
class InteractionContextSnapshot:
    summaries: list[Any] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    _summary_index: dict[str, Any] = field(default_factory=dict, repr=False)

    def has_detail(self, asset_id: str) -> bool:
        return asset_id in self.details

    def detail_epoch(self, asset_id: str) -> int | None:
        detail = self.details.get(asset_id)
        if not isinstance(detail, dict):
            return None
        epoch = detail.get("registration_epoch")
        return epoch if isinstance(epoch, int) else None

    def summary_epoch(self, asset_id: str) -> int | None:
        entry = self._summary_index.get(asset_id)
        if isinstance(entry, dict):
            epoch = entry.get("registration_epoch")
            return epoch if isinstance(epoch, int) else None
        return None

    def is_detail_stale(self, asset_id: str) -> bool:
        detail_epoch = self.detail_epoch(asset_id)
        summary_epoch = self.summary_epoch(asset_id)
        if detail_epoch is None or summary_epoch is None:
            return False
        return detail_epoch < summary_epoch

    def has_summary(self, asset_id: str) -> bool:
        return asset_id in self._summary_index

    def get_summary(self, asset_id: str) -> dict[str, Any] | None:
        entry = self._summary_index.get(asset_id)
        if isinstance(entry, dict):
            return entry
        return None

    def list_summary_asset_ids(self) -> list[str]:
        return list(self._summary_index.keys())

    def with_detail(self, asset_id: str, detail: dict[str, Any]) -> "InteractionContextSnapshot":
        return InteractionContextSnapshot(
            summaries=list(self.summaries),
            details={**self.details, asset_id: detail},
            metadata=dict(self.metadata),
            _summary_index=dict(self._summary_index),
        )

    def with_summaries(self, summaries: list[Any], summary_index: dict[str, Any]) -> "InteractionContextSnapshot":
        return InteractionContextSnapshot(
            summaries=list(summaries),
            details=dict(self.details),
            metadata=dict(self.metadata),
            _summary_index=dict(summary_index),
        )

def build_initial_interaction_context(
    *,
    asset_summaries: list[Any],
    preload_detail_ids: list[str] | None = None,
    detail_provider: Any = None,
) -> InteractionContextSnapshot:
    details: dict[str, dict[str, Any]] = {}
    preload_ids = preload_detail_ids or []
    if detail_provider is not None:
        for asset_id in preload_ids:
            detail = detail_provider(asset_id)
            if isinstance(detail, dict):
                details[asset_id] = detail
    return InteractionContextSnapshot(
        summaries=list(asset_summaries),
        details=details,
        metadata={"preloaded_detail_ids": preload_ids},
    )
