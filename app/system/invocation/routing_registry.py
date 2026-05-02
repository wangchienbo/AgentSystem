from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.system.asset_center.models import AssetDescriptorRecord


@dataclass(frozen=True)
class AssetAliasRecord:
    alias: str
    asset_id: str
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.alias.strip():
            raise ValueError("alias is required")
        if not self.asset_id.strip():
            raise ValueError("asset_id is required")


@dataclass(frozen=True)
class AssetCapabilityTagRecord:
    asset_id: str
    tag: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("asset_id is required")
        if not self.tag.strip():
            raise ValueError("tag is required")


@dataclass(frozen=True)
class RuntimeRegistryRecord:
    target_id: str
    runtime_id: str
    status: str = "active"
    health: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.target_id.strip():
            raise ValueError("target_id is required")
        if not self.runtime_id.strip():
            raise ValueError("runtime_id is required")


@dataclass(frozen=True)
class EndpointRegistryRecord:
    target_id: str
    endpoint: str
    status: str = "active"
    health: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.target_id.strip():
            raise ValueError("target_id is required")
        if not self.endpoint.strip():
            raise ValueError("endpoint is required")


@dataclass(frozen=True)
class PortAllocationRecord:
    target_id: str
    port: int
    host: str = "127.0.0.1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.target_id.strip():
            raise ValueError("target_id is required")
        if self.port < 1 or self.port > 65535:
            raise ValueError("port must be between 1 and 65535")
        if not self.host.strip():
            raise ValueError("host is required")


class AssetIdentityResolutionError(ValueError):
    pass


class EndpointConflictError(ValueError):
    pass


class InvocationRoutingRegistry:
    def __init__(self) -> None:
        self._aliases: list[AssetAliasRecord] = []
        self._capability_tags: list[AssetCapabilityTagRecord] = []
        self._runtime_registry: dict[str, RuntimeRegistryRecord] = {}
        self._endpoint_registry: dict[str, EndpointRegistryRecord] = {}
        self._port_allocations: dict[str, PortAllocationRecord] = {}

    def register_alias(self, record: AssetAliasRecord) -> AssetAliasRecord:
        record.validate()
        # Remove any existing alias for the same alias+asset_id before adding
        self._aliases = [
            item for item in self._aliases
            if not (item.alias == record.alias and item.asset_id == record.asset_id)
        ]
        self._aliases.append(record)
        self._aliases.sort(key=lambda item: item.priority)
        return record

    def register_capability_tag(self, record: AssetCapabilityTagRecord) -> AssetCapabilityTagRecord:
        record.validate()
        self._capability_tags.append(record)
        return record

    def register_runtime(self, record: RuntimeRegistryRecord) -> RuntimeRegistryRecord:
        record.validate()
        self._runtime_registry[record.target_id] = record
        return record

    def register_endpoint(self, record: EndpointRegistryRecord) -> EndpointRegistryRecord:
        record.validate()
        self.ensure_endpoint_available(record.target_id, record.endpoint)
        self._endpoint_registry[record.target_id] = record
        parsed = urlparse(record.endpoint)
        if parsed.port is not None:
            self._port_allocations[record.target_id] = PortAllocationRecord(
                target_id=record.target_id,
                port=int(parsed.port),
                host=parsed.hostname or "127.0.0.1",
            )
        return record

    def allocate_port(self, target_id: str, *, host: str = "127.0.0.1", preferred_port: int | None = None, port_range: range | None = None) -> PortAllocationRecord:
        used = {item.port for item in self._port_allocations.values() if item.host == host}
        candidates = [preferred_port] if preferred_port is not None else []
        if port_range is not None:
            candidates.extend(list(port_range))
        if not candidates:
            candidates.extend(range(20000, 21000))
        for port in candidates:
            if port is None or port in used:
                continue
            record = PortAllocationRecord(target_id=target_id, port=int(port), host=host)
            record.validate()
            self._port_allocations[target_id] = record
            return record
        raise EndpointConflictError(f"no available port for target_id={target_id}")

    def get_port_allocation(self, target_id: str) -> PortAllocationRecord | None:
        return self._port_allocations.get(target_id)

    def ensure_endpoint_available(self, target_id: str, endpoint: str) -> None:
        for existing_target, record in self._endpoint_registry.items():
            if record.endpoint == endpoint:
                raise EndpointConflictError(f"endpoint already assigned to {existing_target}: {endpoint}")

    def get_runtime(self, target_id: str) -> RuntimeRegistryRecord | None:
        return self._runtime_registry.get(target_id)

    def get_endpoint(self, target_id: str) -> EndpointRegistryRecord | None:
        return self._endpoint_registry.get(target_id)

    def resolve_target_id(self, query: str, descriptors: list[AssetDescriptorRecord]) -> str:
        normalized = query.strip().lower()
        if not normalized:
            raise AssetIdentityResolutionError("query is required")

        exact_id = [item.asset_id for item in descriptors if item.asset_id.lower() == normalized]
        if exact_id:
            return exact_id[0]

        alias_hits = [item for item in self._aliases if item.alias.lower() == normalized]
        if alias_hits:
            winner = alias_hits[0]
            tied = [item for item in alias_hits if item.priority == winner.priority]
            if len(tied) > 1:
                raise AssetIdentityResolutionError(f"ambiguous alias: {query}")
            return winner.asset_id

        tag_hits = [item.asset_id for item in self._capability_tags if item.tag.lower() == normalized]
        tag_hits = sorted(set(tag_hits))
        if len(tag_hits) == 1:
            return tag_hits[0]
        if len(tag_hits) > 1:
            raise AssetIdentityResolutionError(f"ambiguous capability tag: {query}")

        summary_hits = [item.asset_id for item in descriptors if normalized in item.summary.lower()]
        summary_hits = sorted(set(summary_hits))
        if len(summary_hits) == 1:
            return summary_hits[0]
        if len(summary_hits) > 1:
            raise AssetIdentityResolutionError(f"ambiguous asset summary match: {query}")

        raise AssetIdentityResolutionError(f"unable to resolve target id for query: {query}")
