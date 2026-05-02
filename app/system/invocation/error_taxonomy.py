from __future__ import annotations

from app.system.invocation.invocation_envelope import InvocationErrorTaxonomy


_ERROR_CATEGORY_MAP = {
    "params_schema_mismatch": ("validation", False),
    "method_not_declared": ("routing", False),
    "descriptor_unavailable": ("routing", True),
    "model_selection_failed": ("model", True),
    "asset_not_found": ("routing", False),
    "method_not_exposed": ("routing", False),
    "method_not_wired": ("execution", True),
    "handler_error": ("execution", False),
    "tool_result_error": ("execution", False),
    "invalid_envelope": ("validation", False),
}


def build_error_taxonomy(error_type: str | None, message: str, *, source: str, retryable: bool | None = None) -> InvocationErrorTaxonomy | None:
    if error_type is None:
        return None
    category, default_retryable = _ERROR_CATEGORY_MAP.get(error_type, ("unknown", False))
    return InvocationErrorTaxonomy(
        code=error_type,
        category=category,
        message=message,
        retryable=default_retryable if retryable is None else retryable,
        metadata={"source": source},
    )
