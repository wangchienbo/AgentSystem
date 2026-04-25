"""Compatibility shim for OpenClaw-style tool handlers.

Kept temporarily during tool-boundary isolation refactor.
Internal AgentSystem code should depend on internal_tools instead.
"""
from app.tools.internal_tools import AGENTSYSTEM_INTERNAL_TOOL_HANDLERS as OPENCLAW_TOOL_HANDLERS
from app.tools.internal_tools import edit_file, exec_shell, list_files, read_file, search_files, write_file
