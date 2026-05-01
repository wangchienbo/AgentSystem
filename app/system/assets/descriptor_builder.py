from __future__ import annotations

from typing import Iterable

from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetModelRequirement


def build_asset_descriptor(
    *,
    descriptor_version: int,
    asset_id: str,
    kind: str,
    summary: str,
    detail: str,
    methods: Iterable[AssetMethodSpec] = (),
    model_requirement: AssetModelRequirement | None = None,
    metadata: dict | None = None,
) -> AssetDescriptorRecord:
    return AssetDescriptorRecord(
        descriptor_version=descriptor_version,
        asset_id=asset_id,
        kind=kind,
        summary=summary,
        detail=detail,
        methods=tuple(methods),
        model_requirement=model_requirement or AssetModelRequirement(),
        metadata=metadata or {},
    )
