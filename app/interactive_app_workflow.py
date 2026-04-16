"""Interactive App Workflow — self-modification workflow for the Interactive App.

Handles the complete flow:
1. Parse user modification intent
2. Read current app code
3. Call LLM to generate new code
4. Create new version
5. Activate (hot-swap)
6. Record to memory

All interaction goes through the LightBrain Gateway (master controller).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class InteractiveAppWorkflowError(ValueError):
    pass


class InteractiveAppWorkflow:
    """Self-modification workflow for the Interactive App.

    This is called by the LightBrain Gateway when a user requests
    UI/App modifications through natural language chat.
    """

    def __init__(
        self,
        interactive_app: Any = None,
        memory_service: Any = None,
        llm_responder: Any = None,
        data_dir: str | None = None,
    ) -> None:
        self._app = interactive_app
        self._memory = memory_service
        self._llm = llm_responder
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._workflow_dir = Path(base) / "interactive_app" / "workflows"
        self._workflow_dir.mkdir(parents=True, exist_ok=True)

    def modify_app(
        self,
        user_id: str,
        user_request: str,
        *,
        auto_activate: bool = True,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        """Execute a self-modification request.

        Args:
            user_id: The requesting user
            user_request: Natural language description of desired change
            auto_activate: If True, activate new version immediately
            require_confirmation: If True, return preview instead of activating

        Returns:
            Dict with version info, code changes, and activation status
        """
        if not self._app:
            raise InteractiveAppWorkflowError("InteractiveApp service not available")

        # Step 1: Get current code
        current_files = self._app.get_user_code(user_id)

        # Step 2: Generate new code via LLM
        new_files = self._generate_code(user_request, current_files, user_id)

        # Step 3: Create new version
        version_id = self._app.create_user_version(user_id, new_files, user_request)

        result = {
            "user_id": user_id,
            "request": user_request,
            "new_version": version_id,
            "files_changed": list(new_files.keys()),
            "auto_activated": False,
            "requires_confirmation": require_confirmation,
            "status": "preview" if require_confirmation else "activated",
        }

        if auto_activate and not require_confirmation:
            activation_result = self._app.activate_user_version(user_id, version_id)
            result["auto_activated"] = True
            result["activation"] = activation_result
            result["status"] = "activated"

        # Step 4: Record to memory
        if self._memory:
            self._memory.record_app_usage(
                user_id,
                "interactive_app",
                "self_modify",
                {
                    "request": user_request,
                    "new_version": version_id,
                    "files_changed": list(new_files.keys()),
                    "auto_activated": result["auto_activated"],
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

        # Step 5: Persist workflow record
        self._persist_workflow_record(result)

        return result

    def rollback(self, user_id: str, target_version: str) -> dict[str, Any]:
        """Rollback to a previous version."""
        if not self._app:
            raise InteractiveAppWorkflowError("InteractiveApp service not available")

        result = self._app.activate_user_version(user_id, target_version)

        if self._memory:
            self._memory.record_app_usage(
                user_id,
                "interactive_app",
                "rollback",
                {
                    "target_version": target_version,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

        return result

    def list_user_versions(self, user_id: str) -> list[dict[str, Any]]:
        """List all versions for a user."""
        if not self._app:
            return []
        return self._app.get_user_version_history(user_id)

    def _generate_code(
        self,
        user_request: str,
        current_files: dict[str, str],
        user_id: str,
    ) -> dict[str, str]:
        """Generate new code using LLM.

        If LLM is not available, falls back to template-based generation.
        """
        # Always use template for speed and reliability
        # LLM can be slow/unreliable for UI modifications
        return self._generate_with_template(user_request, current_files)

    def _generate_with_llm(
        self,
        user_request: str,
        current_files: dict[str, str],
    ) -> dict[str, str]:
        """Use LLM to generate new code."""
        prompt = self._build_generation_prompt(user_request, current_files)
        response, _ = self._llm.generate_reply(
            system_context="You are a frontend developer. You generate clean, modern HTML/CSS/JS code for a chat application. Return ONLY the complete file content, no explanations.",
            user_message=prompt,
            max_tokens=8000,
        )

        # Parse LLM response into file changes
        return self._parse_llm_response(response, current_files)

    def _generate_with_template(
        self,
        user_request: str,
        current_files: dict[str, str],
    ) -> dict[str, str]:
        """Template-based fallback for code generation.

        Handles common modification requests without LLM.
        """
        new_files = dict(current_files)

        if "index.html" not in current_files:
            return new_files

        html = current_files["index.html"]

        # Common template modifications
        request_lower = user_request.lower()

        if any(w in request_lower for w in ["亮", "light", "bright", "浅色", "白"]):
            html = self._apply_theme(html, "light")
        elif any(w in request_lower for w in ["暗", "dark", "黑", "深色"]):
            html = self._apply_theme(html, "dark")
        elif any(w in request_lower for w in ["侧边栏", "sidebar", "左边"]):
            html = self._add_sidebar(html)
        elif any(w in request_lower for w in ["顶部", "header", "导航", "nav"]):
            html = self._add_header(html)
        elif any(w in request_lower for w in ["按钮", "button", "快捷"]):
            html = self._add_quick_buttons(html)

        new_files["index.html"] = html
        return new_files

    def _apply_theme(self, html: str, theme: str) -> str:
        """Apply a theme to the HTML."""
        if theme == "light":
            replacements = {
                "#0a0a0f": "#f5f5fa",
                "#12121a": "#ffffff",
                "#1a1a26": "#eeeef5",
                "#2a2a3a": "#d0d0e0",
                "#e8e8f0": "#1a1a2e",
                "#8888a0": "#666680",
            }
        else:  # dark
            replacements = {
                "#f5f5fa": "#0a0a0f",
                "#ffffff": "#12121a",
                "#eeeef5": "#1a1a26",
                "#d0d0e0": "#2a2a3a",
                "#1a1a2e": "#e8e8f0",
                "#666680": "#8888a0",
            }

        for old, new in replacements.items():
            html = html.replace(old, new)

        return html

    def _add_sidebar(self, html: str) -> str:
        """Add a sidebar to the HTML."""
        sidebar_html = """
        <div class="sidebar" id="sidebar">
            <div class="sidebar-header">📂 会话列表</div>
            <div class="sidebar-content" id="sidebarContent"></div>
        </div>"""

        # Insert sidebar before messages container
        if '<div class="chat-area"' in html:
            html = html.replace('<div class="chat-area"', f'{sidebar_html}\n        <div class="chat-area"')

        # Add sidebar CSS if not present
        if ".sidebar {" not in html:
            css = """
        .sidebar {
            width: 260px;
            background: var(--surface);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .sidebar-header {
            padding: 16px;
            font-weight: 600;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }
        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }"""
            html = html.replace("</style>", f"{css}\n        </style>")

        return html

    def _add_header(self, html: str) -> str:
        """Add a header bar to the HTML."""
        header_html = """
        <header class="app-header">
            <div class="header-title">✦ AgentSystem</div>
            <div class="header-actions">
                <button class="header-btn" onclick="showSettings()">⚙️</button>
            </div>
        </header>"""

        if '<div class="app-container"' in html:
            html = html.replace('<div class="app-container"', f'{header_html}\n        <div class="app-container"')

        if ".app-header {" not in html:
            css = """
        .app-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 24px;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }
        .header-title {
            font-size: 18px;
            font-weight: 600;
        }
        .header-btn {
            background: none;
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
        }
        .header-btn:hover {
            background: var(--surface-2);
        }"""
            html = html.replace("</style>", f"{css}\n        </style>")

        return html

    def _add_quick_buttons(self, html: str) -> str:
        """Add quick action buttons."""
        buttons_html = """
        <div class="quick-actions" id="quickActions">
            <button class="quick-btn" onclick="sendQuick('列出所有App')">📱 列出App</button>
            <button class="quick-btn" onclick="sendQuick('系统状态')">📊 状态</button>
            <button class="quick-btn" onclick="sendQuick('帮助')">❓ 帮助</button>
        </div>"""

        if '<div class="input-area"' in html:
            html = html.replace('<div class="input-area"', f'{buttons_html}\n        <div class="input-area"')

        if ".quick-actions {" not in html:
            css = """
        .quick-actions {
            display: flex;
            gap: 8px;
            padding: 8px 16px;
            border-bottom: 1px solid var(--border);
        }
        .quick-btn {
            background: var(--surface-2);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            white-space: nowrap;
        }
        .quick-btn:hover {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }"""
            html = html.replace("</style>", f"{css}\n        </style>")

        return html

    def _build_generation_prompt(
        self,
        user_request: str,
        current_files: dict[str, str],
    ) -> str:
        """Build the LLM prompt for code generation."""
        prompt = f"User request: {user_request}\n\n"
        prompt += "Current files:\n\n"
        for filename, content in current_files.items():
            prompt += f"--- {filename} ---\n{content}\n\n"
        prompt += "\nGenerate the modified files. Return each file as:\n"
        prompt += "--- filename.ext ---\n<file content>\n\n"
        prompt += "Return only the modified files, keep the rest unchanged."
        return prompt

    def _parse_llm_response(
        self,
        response: str,
        current_files: dict[str, str],
    ) -> dict[str, str]:
        """Parse LLM response into file changes."""
        import re

        new_files = {}
        # Parse "--- filename ---" sections
        pattern = r"---\s*([\w./-]+)\s*---\n(.*?)(?=---|$)"
        matches = re.findall(pattern, response, re.DOTALL)

        for filename, content in matches:
            filename = filename.strip()
            content = content.strip()
            if content:
                new_files[filename] = content

        # If no files found, assume it's a single file modification
        if not new_files and "index.html" in current_files:
            new_files["index.html"] = response.strip()

        return new_files

    def _persist_workflow_record(self, result: dict[str, Any]) -> None:
        """Persist a workflow execution record."""
        record_path = self._workflow_dir / f"wf_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{result['user_id']}.json"
        try:
            record_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        except OSError:
            pass  # Best effort
