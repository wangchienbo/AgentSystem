"""Contract Linter for AgentSystem.

Validates that agent outputs and tool arguments conform to expected schemas
or contracts before execution or return.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LintResult:
    """Result of a linting check."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ContractLinter:
    """Validates data against simple contracts/schemas."""

    def validate_json_structure(self, data: str | dict, required_keys: list[str] | None = None) -> LintResult:
        """Validate that data is valid JSON and contains required keys.
        
        Args:
            data: JSON string or dict.
            required_keys: List of keys that must be present at the top level.
            
        Returns:
            LintResult with validation status.
        """
        errors = []
        warnings = []
        parsed_data = {}

        # Parse if string
        if isinstance(data, str):
            try:
                parsed_data = json.loads(data)
            except json.JSONDecodeError as e:
                return LintResult(is_valid=False, errors=[f"Invalid JSON: {str(e)}"])
        else:
            parsed_data = data

        if not isinstance(parsed_data, dict):
            return LintResult(is_valid=False, errors=["Root element is not a JSON object"])

        # Check required keys
        if required_keys:
            missing_keys = [key for key in required_keys if key not in parsed_data]
            if missing_keys:
                errors.append(f"Missing required keys: {', '.join(missing_keys)}")

        return LintResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_tool_args(self, tool_name: str, args: dict, schema: dict | None = None) -> LintResult:
        """Validate tool arguments against a schema.
        
        Args:
            tool_name: Name of the tool being called.
            args: Arguments passed to the tool.
            schema: Optional JSON Schema dict for validation.
                    If None, only basic type checks are performed.
                    
        Returns:
            LintResult with validation status.
        """
        errors = []
        
        if not isinstance(args, dict):
            return LintResult(is_valid=False, errors=["Tool arguments must be a dictionary"])

        # Basic schema validation if provided
        if schema:
            # Simple implementation: check required fields and types
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            
            # Check required fields
            missing = [k for k in required if k not in args]
            if missing:
                errors.append(f"Tool '{tool_name}' missing required args: {', '.join(missing)}")
                
            # Check types (simplified)
            for key, value in args.items():
                if key in properties:
                    expected_type = properties[key].get("type")
                    if expected_type:
                        if expected_type == "string" and not isinstance(value, str):
                            errors.append(f"Arg '{key}' should be string, got {type(value).__name__}")
                        elif expected_type == "integer" and not isinstance(value, int):
                            errors.append(f"Arg '{key}' should be integer, got {type(value).__name__}")
                        elif expected_type == "boolean" and not isinstance(value, bool):
                            errors.append(f"Arg '{key}' should be boolean, got {type(value).__name__}")

        return LintResult(
            is_valid=len(errors) == 0,
            errors=errors
        )
