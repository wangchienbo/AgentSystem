from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.model_resolved_call import ModelResolvedCall
from app.system.model_runtime.model_selector import ModelSelectionError, ModelSelector


class InvocationDispatchError(ValueError):
    pass


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
            raise InvocationDispatchError(f"method {method} not declared by {asset_id}")

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
                raise InvocationDispatchError(str(exc)) from exc

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
            "resolved_call": prepared.to_dict(),
            "execution": result,
        }

    def _validate_params(self, schema: dict[str, Any], params: dict[str, Any]) -> None:
        if schema.get("type") != "object":
            return
        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []

        for key in required:
            if key not in params:
                raise InvocationDispatchError(f"missing required param: {key}")

        additional_properties = schema.get("additionalProperties", True)
        if additional_properties is False:
            for key in params:
                if key not in properties:
                    raise InvocationDispatchError(f"unexpected param: {key}")

        for key, value in params.items():
            spec = properties.get(key)
            if not isinstance(spec, dict):
                continue
            expected_type = spec.get("type")
            if expected_type == "string" and not isinstance(value, str):
                raise InvocationDispatchError(f"param {key} must be string")
            if expected_type == "object" and not isinstance(value, dict):
                raise InvocationDispatchError(f"param {key} must be object")
            if expected_type == "array" and not isinstance(value, list):
                raise InvocationDispatchError(f"param {key} must be array")
            if expected_type == "boolean" and not isinstance(value, bool):
                raise InvocationDispatchError(f"param {key} must be boolean")
            if expected_type == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
                raise InvocationDispatchError(f"param {key} must be integer")
