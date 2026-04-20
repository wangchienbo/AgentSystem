"""OpenClaw Tools — implementation of core system tools.

Handlers for: exec_shell, read_file, write_file, edit_file, list_files, search_files
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def exec_shell(command: str, workdir: str | None = None, timeout: int = 60) -> dict[str, Any]:
    """Execute shell command and return result."""
    try:
        cwd = Path(workdir) if workdir else None
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
            "stdout": result.stdout[:2000],  # Limit output
            "stderr": result.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(path: str, limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    """Read file contents."""
    try:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        content = file_path.read_text(encoding="utf-8", errors="replace")
        
        # Line-based pagination if offset/limit specified
        if offset is not None or limit is not None:
            lines = content.splitlines()
            start = (offset - 1) if offset else 0
            end = start + (limit or len(lines))
            content = "\n".join(lines[start:end])
        
        return {
            "success": True,
            "content": content[:10000],  # Limit total content
            "lines": content.count("\n") + 1,
            "truncated": len(content) > 10000,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str) -> dict[str, Any]:
    """Write or overwrite file."""
    try:
        file_path = Path(path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(file_path), "bytes_written": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path: str, oldText: str, newText: str) -> dict[str, Any]:
    """Edit file with exact search-replace."""
    try:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        content = file_path.read_text(encoding="utf-8", errors="replace")
        
        if oldText not in content:
            # Try to find partial match for better error message
            return {
                "success": False,
                "error": f"Old text not found in file. Expected:\n{oldText[:100]}...",
            }
        
        # Replace only first occurrence (like edit tool)
        new_content = content.replace(oldText, newText, 1)
        
        if new_content == content:
            return {"success": False, "error": "Replacement had no effect"}
        
        file_path.write_text(new_content, encoding="utf-8")
        
        return {
            "success": True,
            "path": str(file_path),
            "replaced_bytes": len(oldText),
            "new_bytes": len(newText),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(path: str) -> dict[str, Any]:
    """List directory contents."""
    try:
        dir_path = Path(path).expanduser()
        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        
        items = []
        for item in dir_path.iterdir():
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": stat.st_mtime,
            })
        
        # Sort: directories first, then by name
        items.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"]))
        
        return {
            "success": True,
            "path": str(dir_path),
            "items": items[:100],  # Limit results
            "total": len(items),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(pattern: str, path: str, file_pattern: str | None = None) -> dict[str, Any]:
    """Search file contents with regex pattern."""
    try:
        search_path = Path(path).expanduser()
        if not search_path.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        
        results = []
        compiled = re.compile(pattern, re.IGNORECASE)
        
        for root, dirs, files in os.walk(search_path):
            for filename in files:
                if file_pattern and not re.match(file_pattern.replace("*", ".*"), filename):
                    continue
                
                try:
                    file_path = Path(root) / filename
                    if file_path.stat().st_size > 100000:  # Skip large files
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
                    continue  # Skip unreadable files
                
                if len(results) >= 20:  # Limit results
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


# ─── Tool Handler Map ─────────────────────────────────────────────────────────

OPENCLAW_TOOL_HANDLERS: dict[str, callable] = {
    "exec_shell": exec_shell,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "search_files": search_files,
}
