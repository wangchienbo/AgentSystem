from __future__ import annotations

from typing import Any


def render_package_list(packages: list[dict[str, Any]], *, header: str, include_install_status: bool = False) -> str:
    lines = [header]
    for package in packages:
        status_suffix = ""
        if include_install_status:
            installed = "✅ 已安装" if package.get("installed") else "❌ 未安装"
            status_suffix = f" [{installed}]"
        version = package.get("installed_version") or package.get("version") or "unknown"
        lines.append(f"- {package['asset_id']} ({package['asset_type']}) v{version}{status_suffix}")
        if package.get("description"):
            lines.append(f"  {package['description']}")
    return "\n".join(lines)


def render_package_detail(package: dict[str, Any]) -> str:
    lines = [f"📋 **{package.get('name', package['asset_id'])}**\n"]
    lines.append(f"类型: {package.get('asset_type', 'unknown')}")
    if package.get("source_version"):
        lines.append(f"源码版本: {package['source_version']}")
    if package.get("installed_version"):
        lines.append(f"已安装版本: {package['installed_version']}")
    if package.get("description"):
        lines.append(f"描述: {package['description']}")
    history = package.get("build_history", [])
    if history:
        lines.append(f"\n构建历史 ({len(history)} 次):")
        for item in history:
            build_hash = str(item.get("build_hash", ""))[:8]
            build_time = str(item.get("build_time", ""))[:16]
            lines.append(f"  - v{item.get('version', 'unknown')} hash={build_hash} ({build_time})")
    return "\n".join(lines)



def render_app_list(apps: list[dict[str, Any]], *, header: str = "📱 你的 App 列表：\n") -> str:
    lines = [header]
    for app in apps:
        status = app.get("status", "unknown")
        name = app.get("display_name") or app.get("name") or app.get("id", "未知")
        icon = {"running": "🟢", "paused": "🟡", "stopped": "🔴"}.get(status, "⚪")
        lines.append(f"{icon} {name} ({status})")
    return "\n".join(lines)
