from __future__ import annotations

from typing import Any, Callable, Iterable


def join_kv_pairs(pairs: Iterable[tuple[str, Any]]) -> str:
    return "; ".join(f"{key}={value}" for key, value in pairs)


def extract_capability_methods(capabilities: list[dict[str, Any]] | None, *, limit: int | None = None) -> list[str]:
    items = capabilities or []
    visible_items = items[:limit] if limit is not None else items
    methods = []
    for cap in visible_items:
        if isinstance(cap, dict) and cap.get("method"):
            methods.append(str(cap.get("method")))
    return methods


def render_asset_summary_list(
    items: list[dict[str, Any]],
    *,
    header: str,
    sort_key: Callable[[dict[str, Any]], Any] | None = None,
) -> str:
    filtered = [item for item in items if isinstance(item, dict)]
    ordered = sorted(filtered, key=sort_key) if sort_key else filtered

    lines = [header]
    for item in ordered:
        lines.append(f"- {item.get('asset_id')}: {item.get('title', '')} | {item.get('summary', '')}")
    return "\n".join(lines)


def render_asset_detail_header(result_payload: dict[str, Any], *, header: str) -> list[str]:
    return [
        f"{header}: {result_payload.get('asset_id')}",
        f"- title: {result_payload.get('title', '')}",
        f"- summary: {result_payload.get('summary', '')}",
    ]


def append_detail_fallback(lines: list[str], detail: dict[str, Any], *, limit: int = 5) -> list[str]:
    if not detail:
        return lines
    detail_pairs = list(detail.items())[:limit]
    if detail_pairs:
        lines.append(f"- detail: {join_kv_pairs(detail_pairs)}")
    return lines


def render_asset_method_catalog(
    assets: list[dict[str, Any]],
    *,
    header: str,
    footer: str | None = None,
    max_items: int | None = None,
    overflow_template: str | None = None,
) -> str:
    if not assets:
        return f"{header}暂无可用资产"

    visible_assets = assets[:max_items] if max_items is not None else assets
    lines = [header]
    for asset in visible_assets:
        asset_id = asset.get("asset_id", asset.get("name", "unknown"))
        capabilities = asset.get("capabilities", [])
        methods = extract_capability_methods(capabilities, limit=5)
        method_text = ", ".join(methods) if methods else "多个方法"
        lines.append(f"  • {asset_id}: {method_text}")

    if max_items is not None and len(assets) > max_items and overflow_template:
        lines.append(overflow_template.format(extra=len(assets) - max_items))

def render_asset_info_summary(
    *,
    asset_id: str,
    intro: str,
    capabilities: list[dict[str, Any]] | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    lines = [
        intro,
        f"- asset_id: {asset_id}",
    ]
    methods = extract_capability_methods(capabilities)
    if methods:
        lines.append(f"- methods: {', '.join(methods)}")
    lines.extend(extra_lines or [])
    return "\n".join(lines)
