from __future__ import annotations

from typing import Any

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.model_resolved_call import ModelResolvedCall
from app.system.model_runtime.model_selector import ModelSelectionError, ModelSelector


class InvocationDispatchError(ValueError):
    def __init__(self, message: str, *, error_type: str = "invocation_error") -> None:
        super().__init__(message)
        self.error_type = error_type


class InvocationDispatcher:
    def __init__(
        self,
        *,
        asset_center: AssetCenterService,
        runtime_center: RuntimeCenter,
        model_selector: ModelSelector | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._runtime_center = runtime_center
        self._model_selector = model_selector or ModelSelector()

    def prepare_call(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> ModelResolvedCall:
        descriptor = self._asset_center.registry.require_asset(asset_id)
        method_spec = next((item for item in descriptor.methods if item.name == method), None)
        if method_spec is None:
            raise InvocationDispatchError(
                f"method {method} not declared by {asset_id}",
                error_type="method_not_declared",
            )

        normalized_params = params or {}
        self._validate_params(method_spec.input_schema, normalized_params)

        requirement = descriptor.model_requirement
        resolved_model = None
        if requirement.preferred_model or requirement.fallback_model:
            try:
                resolved_model = self._model_selector.resolve(
                    model_records=self._asset_center.registry.list_models(),
                    preferred_model=requirement.preferred_model,
                    fallback_model=requirement.fallback_model,
                    minimum_requirements=requirement.minimum_requirements,
                )
            except ModelSelectionError as exc:
                raise InvocationDispatchError(
                    str(exc),
                    error_type="model_selection_failed",
                ) from exc

        return ModelResolvedCall(
            asset_id=asset_id,
            method=method,
            params=normalized_params,
            resolved_model=resolved_model,
        )

    def dispatch(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        prepared = self.prepare_call(asset_id=asset_id, method=method, params=params)
        result = self._runtime_center.call_asset_method(prepared.asset_id, prepared.method, prepared.params)
        return {
            "ok": bool(result.get("ok")),
            "resolved_call": prepared.to_dict(),
            "execution": result,
            "error": result.get("error"),
            "error_type": result.get("error_type"),
        }

    def dispatch_from_envelope(self, envelope: InteractionDecisionEnvelope) -> dict[str, Any]:
        envelope.validate()
        if envelope.decision != "invoke" or not envelope.invoke:
            raise InvocationDispatchError("envelope must carry invoke payload", error_type="invalid_envelope")
        invoke = envelope.invoke
        return self.dispatch(
            asset_id=str(invoke.get("asset_id") or ""),
            method=str(invoke.get("method") or ""),
            params=invoke.get("params") if isinstance(invoke.get("params"), dict) else {},
        )

    def safe_dispatch(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self.dispatch(asset_id=asset_id, method=method, params=params)
        except InvocationDispatchError as exc:
            return {
                "ok": False,
                "resolved_call": None,
                "execution": None,
                "error": str(exc),
                "error_type": exc.error_type,
            }
        except Exception as exc:
            return {
                "ok": False,
                "resolved_call": None,
                "execution": None,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    def _validate_params(self, schema: dict[str, Any], params: dict[str, Any]) -> None:
        if schema.get("type") != "object":
            return
        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []

        for key in required:
            if key not in params:
                raise InvocationDispatchError(f"missing required param: {key}", error_type="params_schema_mismatch")

        additional_properties = schema.get("additionalProperties", True)
        if additional_properties is False:
            for key in params:
                if key not in properties:
                    raise InvocationDispatchError(f"unexpected param: {key}", error_type="params_schema_mismatch")

        for key, value in params.items():
            spec = properties.get(key)
            if not isinstance(spec, dict):
                continue
            expected_type = spec.get("type")
            if expected_type == "string" and not isinstance(value, str):
                raise InvocationDispatchError(f"param {key} must be string", error_type="params_schema_mismatch")
            if expected_type == "object" and not isinstance(value, dict):
                raise InvocationDispatchError(f"param {key} must be object", error_type="params_schema_mismatch")
            if expected_type == "array" and not isinstance(value, list):
                raise InvocationDispatchError(f"param {key} must be array", error_type="params_schema_mismatch")
            if expected_type == "boolean" and not isinstance(value, bool):
                raise InvocationDispatchError(f"param {key} must be boolean", error_type="params_schema_mismatch")
            if expected_type == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
                raise InvocationDispatchError(f"param {key} must be integer", error_type="params_schema_mismatch")
