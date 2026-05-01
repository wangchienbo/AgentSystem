from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InteractionContextSnapshot:
    summaries: list[Any] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_detail(self, asset_id: str) -> bool:
        return asset_id in self.details

    def has_summary(self, asset_id: str) -> bool:
        return any(self._summary_asset_id(item) == asset_id for item in self.summaries)

    def get_summary(self, asset_id: str) -> dict[str, Any] | None:
        for item in self.summaries:
            if self._summary_asset_id(item) == asset_id:
                return self._summary_to_dict(item)
        return None

    def list_summary_asset_ids(self) -> list[str]:
        return [asset_id for asset_id in (self._summary_asset_id(item) for item in self.summaries) if asset_id]

    def with_detail(self, asset_id: str, detail: dict[str, Any]) -> "InteractionContextSnapshot":
        return InteractionContextSnapshot(
            summaries=list(self.summaries),
            details={**self.details, asset_id: detail},
            metadata=dict(self.metadata),
        )

    def _summary_asset_id(self, item: Any) -> str | None:
        if isinstance(item, dict):
            return item.get("asset_id")
        return getattr(item, "asset_id", None)

    def _summary_to_dict(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        if hasattr(item, "__dict__"):
            return dict(item.__dict__)
        return {"asset_id": self._summary_asset_id(item)} if self._summary_asset_id(item) else {}


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
