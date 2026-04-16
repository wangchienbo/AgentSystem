from __future__ import annotations

from typing import Any


class SchemaRegistryError(ValueError):
    pass


class SchemaRegistryService:
    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(self, schema_ref: str, schema: dict[str, Any]) -> None:
        if not schema_ref:
            raise SchemaRegistryError("Schema ref must not be empty")
        if not isinstance(schema, dict):
            raise SchemaRegistryError(f"Schema must be a mapping: {schema_ref}")
        self._schemas[schema_ref] = schema

    def resolve(self, schema_ref: str) -> dict[str, Any]:
        if not schema_ref:
            raise SchemaRegistryError("Schema ref must not be empty")
        if schema_ref not in self._schemas:
            raise SchemaRegistryError(f"Schema ref not found: {schema_ref}")
        return self._schemas[schema_ref]

    def validate(self, schema_ref: str, payload: Any) -> None:
        schema = self.resolve(schema_ref)
        self._validate_schema(schema_ref, schema, payload, path="$")

    def _validate_schema(self, schema_ref: str, schema: dict[str, Any], payload: Any, path: str) -> None:
        expected_type = schema.get("type")
        if expected_type == "object":
            if not isinstance(payload, dict):
                raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected object")
            required = schema.get("required", [])
            for key in required:
                if key not in payload:
                    raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: missing required property '{key}'")
            properties = schema.get("properties", {})
            for key, value in payload.items():
                if key in properties:
                    self._validate_schema(schema_ref, properties[key], value, path=f"{path}.{key}")
                elif schema.get("additionalProperties", True) is False:
                    raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: unexpected property '{key}'")
            return
        if expected_type == "array":
            if not isinstance(payload, list):
                raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected array")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(payload):
                    self._validate_schema(schema_ref, item_schema, item, path=f"{path}[{index}]")
            return
        if expected_type == "string" and not isinstance(payload, str):
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected string")
        if expected_type == "integer" and (not isinstance(payload, int) or isinstance(payload, bool)):
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected integer")
        if expected_type == "number" and (not isinstance(payload, (int, float)) or isinstance(payload, bool)):
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected number")
        if expected_type == "boolean" and not isinstance(payload, bool):
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected boolean")
        if expected_type == "null" and payload is not None:
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: expected null")
        if "enum" in schema and payload not in schema["enum"]:
            raise SchemaRegistryError(f"Schema validation failed for {schema_ref} at {path}: unexpected enum value {payload!r}")
