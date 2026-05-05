"""AgentSystem internal tool implementations.

This module defines the isolated internal tool runtime used by AgentSystem.
Compatibility with OpenClaw-style tool names is handled separately by
metadata/registration layers, not by exposing OpenClaw as the internal domain.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEARCH_ROOT = DEFAULT_REPO_ROOT
IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}
IGNORED_FILE_SUFFIXES = {".pyc", ".pyo"}


def _should_skip_path(path: Path) -> bool:
    if any(part in IGNORED_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in IGNORED_FILE_SUFFIXES:
        return True
    return False


def _normalize_workdir(workdir: str | None) -> Path:
    if workdir:
        return Path(workdir).expanduser()
    return DEFAULT_REPO_ROOT


def _normalize_path(path: str) -> Path:
    raw = Path(path).expanduser()
    if raw.is_absolute():
        return raw
    return DEFAULT_REPO_ROOT / raw


def exec_shell(command: str, workdir: str | None = None, timeout: int = 60) -> dict[str, Any]:
    try:
        cwd = _normalize_workdir(workdir)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "workdir": str(cwd),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s", "workdir": str(_normalize_workdir(workdir))}
    except Exception as e:
        return {"success": False, "error": str(e), "workdir": str(_normalize_workdir(workdir))}


def read_file(path: str, limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    try:
        file_path = _normalize_path(path)
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if offset is not None or limit is not None:
            lines = content.splitlines()
            start = (offset - 1) if offset else 0
            end = start + (limit or len(lines))
            content = "\n".join(lines[start:end])
        return {
            "success": True,
            "content": content[:10000],
            "lines": content.count("\n") + 1,
            "truncated": len(content) > 10000,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str) -> dict[str, Any]:
    try:
        file_path = _normalize_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(file_path), "bytes_written": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    try:
        file_path = _normalize_path(path)
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return {"success": False, "error": f"Old text not found in file. Expected:\n{old_text[:100]}..."}
        new_content = content.replace(old_text, new_text, 1)
        if new_content == content:
            return {"success": False, "error": "Replacement had no effect"}
        file_path.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": str(file_path),
            "replaced_bytes": len(old_text),
            "new_bytes": len(new_text),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(path: str) -> dict[str, Any]:
    try:
        dir_path = _normalize_path(path)
        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        items = []
        for item in dir_path.iterdir():
            if _should_skip_path(item):
                continue
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": stat.st_mtime,
            })
        items.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"]))
        return {"success": True, "path": str(dir_path), "items": items[:100], "total": len(items)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(pattern: str, path: str, file_pattern: str | None = None) -> dict[str, Any]:
    try:
        search_path = _normalize_path(path) if path else DEFAULT_SEARCH_ROOT
        if not search_path.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        results = []
        compiled = re.compile(pattern, re.IGNORECASE)
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
            for filename in files:
                file_path = Path(root) / filename
                if _should_skip_path(file_path):
                    continue
                if file_pattern and not re.match(file_pattern.replace("*", ".*"), filename):
                    continue
                try:
                    if file_path.stat().st_size > 100000:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    matches = list(compiled.finditer(content))
                    if matches:
                        results.append({
                            "file": str(file_path.relative_to(search_path)),
                            "matches": len(matches),
                            "preview": content[max(0, matches[0].start()-50):matches[0].end()+50],
                        })
                except Exception:
                    continue
                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break
        return {
            "success": True,
            "pattern": pattern,
            "path": str(search_path),
            "matches": len(results),
            "results": results,
        }
    except re.error as e:
        return {"success": False, "error": f"Invalid regex pattern: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


AGENTSYSTEM_INTERNAL_TOOL_HANDLERS: dict[str, callable] = {
    "exec_shell": exec_shell,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "search_files": search_files,
}
