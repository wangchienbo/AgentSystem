from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.context_center import ContextCenter
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.routing_governance_service import RoutingGovernanceService


@dataclass(frozen=True)
class RuntimeTopologySnapshot:
    assets: list[dict[str, Any]] = field(default_factory=list)
    runtime_assets: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    bindings: list[dict[str, Any]] = field(default_factory=list)
    downstream_edges: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assets": self.assets,
            "runtime_assets": self.runtime_assets,
            "sessions": self.sessions,
            "bindings": self.bindings,
            "downstream_edges": self.downstream_edges,
        }


class RuntimeTopologyReadModel:
    def __init__(
        self,
        *,
        asset_center: AssetCenterService,
        runtime_center: RuntimeCenter,
        context_center: ContextCenter,
        routing_governance: RoutingGovernanceService | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._runtime_center = runtime_center
        self._context_center = context_center
        self._routing_governance = routing_governance

    def build_snapshot(self) -> RuntimeTopologySnapshot:
        assets = [self._asset_center.get_asset_detail(item["asset_id"]) for item in self._asset_center.list_assets()]
        runtime_assets = [item.model_dump(mode="json") for item in self._runtime_center.list_all()]
        bindings = self._asset_center.list_session_bindings()
        sessions = []
        try:
            all_sessions = self._context_center.list_sessions()
            for session in all_sessions:
                local_refs = self._context_center.list_asset_local_sessions_for_session(getattr(session, "session_id", ""))
                sessions.append(
                    {
                        "session_id": getattr(session, "session_id", ""),
                        "kind": getattr(session, "kind", ""),
                        "status": getattr(session, "status", ""),
                        "summary": getattr(session, "topic_key", ""),
                        "local_session_refs": local_refs,
                    }
                )
        except AttributeError:
            pass
        downstream_edges = []
        if self._routing_governance is not None:
            for asset in assets:
                route = self._routing_governance.resolve_route(asset["asset_id"])
                if route.get("endpoint") or route.get("runtime"):
                    downstream_edges.append(
                        {
                            "target_id": asset["asset_id"],
                            "endpoint": None if route.get("endpoint") is None else route["endpoint"].get("endpoint"),
                            "runtime_id": None if route.get("runtime") is None else route["runtime"].get("runtime_id"),
                        }
                    )
        return RuntimeTopologySnapshot(
            assets=assets,
            runtime_assets=runtime_assets,
            sessions=sessions,
            bindings=bindings,
            downstream_edges=downstream_edges,
        )
