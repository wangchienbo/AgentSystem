"""Asset Manifest Validator — Enforces the unified manifest schema for all assets.

Implements N3-01: Unified Manifest Standard.
Every asset (skill, app, system module) must conform to this schema to be discovered/installed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
from pydantic import BaseModel, Field, ValidationError

AssetType = Literal["skill", "app", "system", "service"]
OwnerRole = Literal["system", "admin", "user", "app"]

class AssetManifest(BaseModel):
    """
    Unified Asset Manifest Schema (N3-01 Standard).
    All assets must include these fields to be valid.
    """
    asset_id: str = Field(..., description="Unique identifier, e.g., 'skill.writer', 'app.notebook'")
    asset_type: AssetType = Field(..., description="Type of asset: skill, app, system, service")
    name: str = Field(..., description="Human-readable name")
    version: str = Field(default="1.0.0", description="Semantic version")
    entry: str = Field(..., description="Entry point, e.g., 'app.skills.writer:main'")
    owner: str = Field(default="system", description="Owner identity")
    owner_role: OwnerRole = Field(default="system", description="Owner role level")
    dependencies: list[str] = Field(default_factory=list, description="List of required asset_ids")
    source_path: str = Field(..., description="Relative path to source code")
    description: str = Field(default="", description="Short description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extended metadata")

    class Config:
        extra = "allow"  # Allow extra fields but enforce core ones

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

class ManifestValidator:
    """Validates asset manifests against the N3-01 standard."""

    def validate(self, manifest: dict[str, Any]) -> ValidationResult:
        """
        Validate a manifest dictionary.
        Returns ValidationResult with errors/warnings.
        """
        errors = []
        warnings = []

        # 1. Pydantic Schema Validation
        try:
            AssetManifest(**manifest)
        except ValidationError as e:
            for error in e.errors():
                field_name = ".".join(str(x) for x in error["loc"])
                errors.append(f"{field_name}: {error['msg']}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 2. Business Logic Checks (Optional strictness)
        # Example: Enforce semantic versioning format (loose check)
        version = manifest.get("version", "")
        if version and "." not in version:
            warnings.append(f"Version '{version}' may not follow semver (x.y.z).")

        # Example: Warn if no dependencies declared (might be intended, but worth noting)
        if not manifest.get("dependencies"):
            warnings.append("No dependencies declared.")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def validate_file(self, manifest_path: str) -> ValidationResult:
        """Validate a manifest file (JSON/YAML)."""
        import json
        import yaml
        from pathlib import Path

        path = Path(manifest_path)
        if not path.exists():
            return ValidationResult(is_valid=False, errors=[f"File not found: {manifest_path}"])

        try:
            if path.suffix in [".yaml", ".yml"]:
                data = yaml.safe_load(path.read_text())
            else:
                data = json.loads(path.read_text())
            
            return self.validate(data)
        except Exception as e:
            return ValidationResult(is_valid=False, errors=[f"Parse error: {str(e)}"])
