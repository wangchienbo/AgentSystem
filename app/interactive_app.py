"""Interactive App — per-user isolated application with self-modification.

Each user gets their own:
- Version tree (data/interactive_app/users/{user_id}/versions/)
- Active version symlink (data/interactive_app/users/{user_id}/active)
- Workspace (data/interactive_app/users/{user_id}/workspace/)
- Config (data/interactive_app/users/{user_id}/config.json)

The system-level template provides the default starting point.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.runtime_paths import resolve_runtime_paths


class InteractiveAppError(ValueError):
    pass


class InteractiveAppService:
    """Per-user Interactive App management with version control and self-modification."""

    def __init__(self, data_dir: str | None = None) -> None:
        base = Path(data_dir) if data_dir else resolve_runtime_paths().data_dir
        self._base_dir = Path(base) / "interactive_app"
        self._users_dir = self._base_dir / "users"
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._templates_dir = self._base_dir / "templates"
        self._templates_dir.mkdir(parents=True, exist_ok=True)

        # Initialize default template if not exists
        self._init_default_template()

    # -- User-level operations --------------------------------------------------

    def get_user_dir(self, user_id: str) -> Path:
        """Get user's app directory (creates if not exists)."""
        user_dir = self._users_dir / user_id
        if not user_dir.exists():
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "versions").mkdir(exist_ok=True)
            (user_dir / "workspace").mkdir(exist_ok=True)
            # Copy default template as initial version
            self._copy_template_to_user(user_id, "default_chat")
        return user_dir

    def get_user_active_dir(self, user_id: str) -> Path:
        """Get path to user's active version directory."""
        return self.get_user_dir(user_id) / "active"

    def get_user_code(self, user_id: str) -> dict[str, str]:
        """Read all code files from user's active version.

        Returns:
            Dict of {relative_path: file_content}
        """
        active_dir = self.get_user_active_dir(user_id)
        if not active_dir.exists():
            # Initialize from template
            self._copy_template_to_user(user_id, "default_chat")
            active_dir = self.get_user_active_dir(user_id)

        files = {}
        for f in active_dir.rglob("*"):
            if f.is_file() and f.name != "meta.json":
                rel_path = str(f.relative_to(active_dir))
                try:
                    files[rel_path] = f.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    pass  # Skip binary files

        return files

    def create_user_version(
        self,
        user_id: str,
        code_changes: dict[str, str],
        description: str = "",
    ) -> str:
        """Create a new version for a user.

        Args:
            user_id: User identifier
            code_changes: Dict of {file_path: new_content}
            description: Description of changes

        Returns:
            New version ID
        """
        version_id = f"v{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        user_dir = self.get_user_dir(user_id)
        version_dir = user_dir / "versions" / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        # First copy current active files (base)
        active_dir = user_dir / "active"
        if active_dir.exists():
            for f in active_dir.rglob("*"):
                if f.is_file() and f.name != "meta.json":
                    rel_path = f.relative_to(active_dir)
                    target = version_dir / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)

        # Apply changes
        for file_path, content in code_changes.items():
            target = version_dir / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        # Save version metadata
        meta = {
            "version_id": version_id,
            "description": description,
            "created_at": datetime.now(UTC).isoformat(),
            "files_changed": list(code_changes.keys()),
            "total_files": len(list(version_dir.rglob("*"))),
        }
        (version_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

        return version_id

    def activate_user_version(self, user_id: str, version_id: str) -> dict[str, Any]:
        """Activate a specific version for a user (hot-swap)."""
        user_dir = self.get_user_dir(user_id)
        version_dir = user_dir / "versions" / version_id
        if not version_dir.exists():
            raise InteractiveAppError(f"Version {version_id} not found for user {user_id}")

        active_dir = user_dir / "active"
        if active_dir.exists():
            shutil.rmtree(active_dir)
        shutil.copytree(version_dir, active_dir)

        # Update current version pointer
        pointer = user_dir / "current_version.txt"
        pointer.write_text(version_id)

        return {
            "status": "activated",
            "user_id": user_id,
            "version": version_id,
            "activated_at": datetime.now(UTC).isoformat(),
        }

    def get_user_current_version(self, user_id: str) -> str:
        """Get current active version ID for a user."""
        user_dir = self.get_user_dir(user_id)
        pointer = user_dir / "current_version.txt"
        if pointer.exists():
            return pointer.read_text().strip()

        # Check active dir for meta
        active_dir = user_dir / "active"
        if active_dir.exists():
            meta_path = active_dir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                return meta.get("version_id", "v0")
        return "v0"

    def get_user_version_history(self, user_id: str) -> list[dict[str, Any]]:
        """List all versions for a user."""
        user_dir = self.get_user_dir(user_id)
        versions_dir = user_dir / "versions"
        if not versions_dir.exists():
            return []

        history = []
        for meta_file in sorted(versions_dir.glob("*/meta.json")):
            try:
                meta = json.loads(meta_file.read_text())
                history.append(meta)
            except Exception:
                continue
        return history

    def get_user_config(self, user_id: str) -> dict[str, Any]:
        """Get user-specific configuration."""
        config_path = self.get_user_dir(user_id) / "config.json"
        if config_path.exists():
            return json.loads(config_path.read_text())
        return {"user_id": user_id, "theme": "dark", "created_at": datetime.now(UTC).isoformat()}

    def save_user_config(self, user_id: str, config: dict[str, Any]) -> None:
        """Save user-specific configuration."""
        config_path = self.get_user_dir(user_id) / "config.json"
        config["user_id"] = user_id
        config["updated_at"] = datetime.now(UTC).isoformat()
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

    def get_user_frontend_path(self, user_id: str) -> str:
        """Get path to user's active frontend index.html."""
        active_index = self.get_user_active_dir(user_id) / "index.html"
        if active_index.exists():
            return str(active_index)
        # Fallback to system default
        default = Path(__file__).parent.parent / "static" / "index.html"
        if default.exists():
            return str(default)
        return ""

    def delete_user_version(self, user_id: str, version_id: str) -> None:
        """Delete a specific version (cannot delete active version)."""
        user_dir = self.get_user_dir(user_id)
        version_dir = user_dir / "versions" / version_id
        current = self.get_user_current_version(user_id)
        if version_id == current:
            raise InteractiveAppError("Cannot delete the currently active version")
        if version_dir.exists():
            shutil.rmtree(version_dir)

    def get_user_status(self, user_id: str) -> dict[str, Any]:
        """Get Interactive App status for a specific user."""
        current = self.get_user_current_version(user_id)
        versions = self.get_user_version_history(user_id)
        return {
            "user_id": user_id,
            "current_version": current,
            "version_count": len(versions),
            "versions": versions[-5:],  # Last 5
        }

    # -- System-level template management ---------------------------------------

    def _init_default_template(self) -> None:
        """Create default chat template if not exists."""
        template_dir = self._templates_dir / "default_chat"
        if template_dir.exists():
            return

        template_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal default index.html
        default_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentSystem Chat</title>
    <style>
        :root {
            --bg: #0a0a0f; --surface: #12121a; --surface-2: #1a1a26;
            --border: #2a2a3a; --text: #e8e8f0; --text-dim: #8888a0;
            --accent: #6c5ce7; --accent-glow: rgba(108, 92, 231, 0.3);
            --radius: 12px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; background: var(--bg); color: var(--text); }
        .app { display: flex; height: 100vh; }
        .sidebar { width: 260px; background: var(--surface); border-right: 1px solid var(--border); padding: 16px; }
        .main { flex: 1; display: flex; flex-direction: column; }
        .messages { flex: 1; overflow-y: auto; padding: 24px; }
        .input-area { padding: 16px; border-top: 1px solid var(--border); display: flex; gap: 8px; }
        input { flex: 1; padding: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); }
        button { padding: 12px 24px; background: var(--accent); border: none; border-radius: 8px; color: white; cursor: pointer; }
    </style>
</head>
<body>
    <div class="app">
        <div class="sidebar"><h3>AgentSystem</h3></div>
        <div class="main">
            <div class="messages" id="messages"><p>Welcome!</p></div>
            <div class="input-area"><input id="input" placeholder="Type a message..."><button onclick="send()">Send</button></div>
        </div>
    </div>
</body>
</html>"""
        (template_dir / "index.html").write_text(default_html, encoding="utf-8")

        # Template metadata
        meta = {
            "template_id": "default_chat",
            "name": "Default Chat UI",
            "version": "1.0.0",
            "description": "Default chat interface template",
            "created_at": datetime.now(UTC).isoformat(),
        }
        (template_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    def _copy_template_to_user(self, user_id: str, template_id: str) -> None:
        """Copy a template to a user's active directory."""
        template_dir = self._templates_dir / template_id
        if not template_dir.exists():
            raise InteractiveAppError(f"Template {template_id} not found")

        user_dir = self.get_user_dir(user_id)
        active_dir = user_dir / "active"
        if active_dir.exists():
            shutil.rmtree(active_dir)
        shutil.copytree(template_dir, active_dir)

        # Set initial version pointer
        version_id = f"v{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        (user_dir / "current_version.txt").write_text(version_id)
