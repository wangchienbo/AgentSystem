from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_INVOCATION_MANIFEST_FIELDS = {
    "invocation_contract_version",
    "runtime_wrapper_compatibility",
    "session_binding_support",
    "endpoint_requirement",
    "tool_vllm_usage_mode",
}


@dataclass(frozen=True)
class InvocationComplianceResult:
    compliant: bool
    reasons: list[str]


class InvocationComplianceValidator:
    def validate_manifest(self, manifest: dict[str, Any]) -> InvocationComplianceResult:
        metadata = manifest.get("metadata") or {}
        reasons: list[str] = []

        missing = sorted(field for field in REQUIRED_INVOCATION_MANIFEST_FIELDS if field not in metadata)
        if missing:
            reasons.append(f"missing invocation metadata fields: {', '.join(missing)}")

        if metadata.get("invocation_contract_version") not in {"phase-p-v1"}:
            reasons.append("invocation_contract_version must be 'phase-p-v1'")

        if metadata.get("runtime_wrapper_compatibility") is not True:
            reasons.append("runtime_wrapper_compatibility must be true")

        if metadata.get("session_binding_support") not in {"required", "supported"}:
            reasons.append("session_binding_support must be 'required' or 'supported'")

        if metadata.get("endpoint_requirement") not in {"none", "optional", "required"}:
            reasons.append("endpoint_requirement must be one of: none, optional, required")

        if metadata.get("tool_vllm_usage_mode") not in {"local_session_only", "session_binding_resolved"}:
            reasons.append("tool_vllm_usage_mode must be 'local_session_only' or 'session_binding_resolved'")

        return InvocationComplianceResult(compliant=not reasons, reasons=reasons)

    def validate_registration_descriptor(self, descriptor: Any) -> InvocationComplianceResult:
        metadata = getattr(descriptor, "metadata", {}) or {}
        reasons: list[str] = []
        if metadata.get("runtime_wrapper_compatibility") is not True:
            reasons.append("descriptor metadata must declare runtime_wrapper_compatibility=true")
        if metadata.get("session_binding_support") not in {"required", "supported"}:
            reasons.append("descriptor metadata must declare session_binding_support")
        if metadata.get("invocation_contract_version") not in {"phase-p-v1"}:
            reasons.append("descriptor metadata must declare invocation_contract_version=phase-p-v1")
        return InvocationComplianceResult(compliant=not reasons, reasons=reasons)
