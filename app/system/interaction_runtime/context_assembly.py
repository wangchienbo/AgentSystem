from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InteractionContextSnapshot:
    summaries: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_detail(self, asset_id: str) -> bool:
        return asset_id in self.details

    def has_summary(self, asset_id: str) -> bool:
        return any(item.get("asset_id") == asset_id for item in self.summaries)

    def get_summary(self, asset_id: str) -> dict[str, Any] | None:
        for item in self.summaries:
            if item.get("asset_id") == asset_id:
                return item
        return None

    def with_detail(self, asset_id: str, detail: dict[str, Any]) -> "InteractionContextSnapshot":
        return InteractionContextSnapshot(
            summaries=list(self.summaries),
            details={**self.details, asset_id: detail},
            metadata=dict(self.metadata),
        )


def build_initial_interaction_context(
    *,
    asset_summaries: list[dict[str, Any]],
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
