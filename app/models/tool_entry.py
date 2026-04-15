"""Tool Entry — unified model for all callable tools in the system.

Every tool (skill, path, built-in function, external service) is registered
as a ToolEntry with a consistent interface. The ToolCallExecutor uses this
registry to discover and invoke tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolType(str, Enum):
    """Tool execution type."""
    SKILL = "skill"          # RPC skill (stateful or stateless)
    PATH = "path"            # Stateless one-shot flow (NOT registered as LLM tool)
    BUILTIN = "builtin"      # Built-in Python function
    EXTERNAL = "external"    # External service call


class ToolVisibility(str, Enum):
    """Tool visibility scope."""
    PUBLIC = "public"        # Visible to all users
    PRIVATE = "private"      # Visible only to owner
    APP = "app"              # Visible only within specific app


@dataclass
class ToolParameter:
    """A single parameter definition for a tool."""
    name: str
    param_type: str  # "string", "integer", "boolean", "object", "array"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class ToolEntry:
    """Unified tool registration entry.

    Attributes:
        tool_id: Unique identifier, e.g. "skill.maoxuan", "path.create_app"
        name: Human-readable name
        tool_type: Execution type (skill/path/builtin/external)
        description: What this tool does (L1 summary for LLM context)
        detail_description: Extended description (L2, fetched on demand)
        parameters: Input parameter schema
        handler: Callable that executes the tool
        visibility: Who can see/call this tool
        app_id: App scope (None for system-level tools)
        owner_role: Minimum role required to call
        tags: Classification tags
        enabled: Whether the tool is currently active
        version: Tool version for upgrade tracking
    """
    tool_id: str
    name: str
    tool_type: ToolType
    description: str = ""
    detail_description: str = ""
    parameters: list[ToolParameter] = field(default_factory=list)
    handler: Callable | None = None
    visibility: ToolVisibility = ToolVisibility.PUBLIC
    app_id: str | None = None
    owner_role: str = "user"
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    version: str = "1.0.0"

    def to_llm_context(self, include_detail: bool = False) -> dict[str, Any]:
        """Return a dict suitable for LLM tool selection context."""
        result = {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.param_type,
                    "required": p.required,
                    "description": p.description,
                }
                for p in self.parameters
            ],
            "tags": self.tags,
            "version": self.version,
        }
        if include_detail:
            result["detail_description"] = self.detail_description
        return result
