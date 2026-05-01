from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.system.asset_center.models import AssetDescriptorRecord


AssetMethodHandler = Callable[..., Any]


@dataclass(frozen=True)
class RegisteredAsset:
    descriptor: AssetDescriptorRecord
    service_ref: Any
    method_mappings: dict[str, AssetMethodHandler] = field(default_factory=dict)


class BaseAsset(Protocol):
    def asset_id(self) -> str: ...

    def build_descriptor(self) -> AssetDescriptorRecord: ...

    def build_method_mappings(self) -> dict[str, AssetMethodHandler]: ...

    def get_service_ref(self) -> Any: ...
