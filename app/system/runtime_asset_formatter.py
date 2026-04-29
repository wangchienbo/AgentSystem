from __future__ import annotations

import json

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

    if footer:
        lines.append("")
        lines.append(footer)

    return "\n".join(lines)


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


def render_asset_interface_details(
    interfaces: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[str]:
    normalized_interfaces: dict[str, Any] = {}
    if isinstance(interfaces, list):
        for item in interfaces:
            if isinstance(item, dict):
                key = item.get("name") or item.get("method") or "unknown"
                normalized_interfaces[str(key)] = item
    elif isinstance(interfaces, dict):
        normalized_interfaces = interfaces

    interface_lines = []
    for key, info in normalized_interfaces.items():
        info = info or {}
        desc = info.get("description", "") if isinstance(info, dict) else ""
        input_schema = info.get("input_schema") or info.get("input") or {} if isinstance(info, dict) else {}
        output_schema = info.get("output_schema") or info.get("output") or {} if isinstance(info, dict) else {}
        line = f"\n**{key}** - {desc}" if desc else f"\n**{key}**"
        if input_schema:
            line += f"\n  输入: {json.dumps(input_schema, ensure_ascii=False)}"
        if output_schema:
            line += f"\n  输出: {json.dumps(output_schema, ensure_ascii=False)}"
        interface_lines.append(line)
    return interface_lines


def render_asset_detail_document(
    *,
    asset_id: str,
    asset_name: str,
    description: str,
    interfaces: dict[str, Any] | list[dict[str, Any]] | None,
) -> str:
    interface_lines = render_asset_interface_details(interfaces)
    if interface_lines:
        return (
            f"📋 **{asset_name}** 详细使用说明\n\n"
            f"资产ID: {asset_id}\n"
            f"{description}\n\n"
            f"**可用接口：**{''.join(interface_lines)}"
        )
    return (
        f"📋 **{asset_name}** 详细使用说明\n\n"
        f"资产ID: {asset_id}\n"
        f"{description}\n\n无可用接口"
    )


def render_asset_overview_prompt(
    assets: list[Any],
    *,
    header: str,
) -> str:
    if not assets:
        return "当前没有可用的资产。"

    lines = [
        header,
        "",
        "以下是你可以调用的资产列表。每个资产包含：",
        "- asset_id: 资产唯一标识",
        "- 名称: 人类可读名称",
        "- 接口: 该资产提供的所有可调用的功能",
        "",
        "**重要：如需了解某个资产的详细使用说明（输入参数格式、输出格式、注意事项），",
        "请调用 query_asset_detail(asset_id) 工具。**",
        "",
    ]
    for asset in assets:
        if hasattr(asset, "interfaces"):
            interfaces = getattr(asset, "interfaces", {}) or {}
            fn_names = ", ".join(f"{k}({v.get('description', '')})" for k, v in interfaces.items()) if interfaces else "无"
        elif hasattr(asset, "functions"):
            functions = getattr(asset, "functions", []) or []
            fn_names = ", ".join(f"{f.key}({f.name})" for f in functions) if functions else "无"
        else:
            fn_names = "无"
        lines.append(f"### {getattr(asset, 'asset_id', 'unknown')} ({getattr(asset, 'name', 'unknown')})")
        lines.append(f"描述: {getattr(asset, 'description', '')}")
        lines.append(f"可用接口: {fn_names if fn_names else '无'}")
        lines.append("")
    return "\n".join(lines)
