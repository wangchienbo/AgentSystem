from __future__ import annotations

from typing import Any, Callable, Iterable


def join_kv_pairs(pairs: Iterable[tuple[str, Any]]) -> str:
    return "; ".join(f"{key}={value}" for key, value in pairs)


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
