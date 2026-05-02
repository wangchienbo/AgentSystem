from __future__ import annotations

from typing import Any, Callable

from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, InteractionDecisionEnvelope
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.error_taxonomy import build_error_taxonomy
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope
from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer
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
        asset_center: Any,
        runtime_center: RuntimeCenter,
        model_selector: ModelSelector | None = None,
        descriptor_provider: Callable[[str], dict[str, Any] | None] | None = None,
        runtime_layer: AssetInvocationRuntimeLayer | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._runtime_center = runtime_center
        self._model_selector = model_selector or ModelSelector()
        self._descriptor_provider = descriptor_provider
        self._runtime_layer = runtime_layer

    def prepare_call(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> ModelResolvedCall:
        envelope = InvocationRequestEnvelope.from_legacy(asset_id=asset_id, method=method, params=params)
        return self.prepare_envelope(envelope)

    def prepare_envelope(self, envelope: InvocationRequestEnvelope) -> ModelResolvedCall:
        envelope.validate()
        descriptor = self._require_descriptor(envelope.target_id)
        method_spec = next((item for item in descriptor.methods if item.name == envelope.method), None)
        if method_spec is None:
            raise InvocationDispatchError(
                f"method {envelope.method} not declared by {envelope.target_id}",
                error_type="method_not_declared",
            )

        normalized_params = envelope.args or {}
        self._validate_params(method_spec.input_schema, normalized_params)

        requirement = descriptor.model_requirement
        resolved_model = None
        if requirement.preferred_model or requirement.fallback_model:
            try:
                resolved_model = self._model_selector.resolve(
                    model_records=self._list_model_records(),
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
            asset_id=envelope.target_id,
            method=envelope.method,
            params=normalized_params,
            resolved_model=resolved_model,
            request_id=envelope.request_id,
            target_type=envelope.target_type,
            session=envelope.session.to_dict() if envelope.session is not None else None,
            caller=envelope.caller.to_dict() if envelope.caller is not None else None,
            trace_context=envelope.trace_context,
            metadata=envelope.metadata,
        )

    def dispatch(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        envelope = InvocationRequestEnvelope.from_legacy(asset_id=asset_id, method=method, params=params)
        return self._dispatch_invocation_envelope(envelope)

    def dispatch_from_envelope(self, envelope: InteractionDecisionEnvelope | InvocationRequestEnvelope) -> dict[str, Any]:
        if isinstance(envelope, InvocationRequestEnvelope):
            return self._dispatch_invocation_envelope(envelope)
        envelope.validate()
        if envelope.decision != "invoke" or not envelope.invoke:
            raise InvocationDispatchError("envelope must carry invoke payload", error_type="invalid_envelope")
        invoke = envelope.invoke
        return self.dispatch(
            asset_id=str(invoke.get("asset_id") or ""),
            method=str(invoke.get("method") or ""),
            params=invoke.get("params") if isinstance(invoke.get("params"), dict) else {},
        )

    def _dispatch_invocation_envelope(self, envelope: InvocationRequestEnvelope) -> dict[str, Any]:
        prepared = self.prepare_envelope(envelope)
        if self._runtime_layer is not None and hasattr(self._runtime_center, "invoke_asset_envelope"):
            response = self._runtime_center.invoke_asset_envelope(envelope)
            response_payload = response.to_dict()
            result = response.metadata.get("execution") if isinstance(response.metadata, dict) else None
            if not isinstance(result, dict):
                result = {
                    "ok": response.ok,
                    "result": response.data,
                    "error": response.error,
                    "error_type": response.error_type,
                }
        else:
            result = self._runtime_center.call_asset_method(prepared.asset_id, prepared.method, prepared.params)
            response = InvocationResponseEnvelope(
                ok=bool(result.get("ok")),
                request_id=prepared.request_id,
                data=result.get("result") if isinstance(result.get("result"), dict) else {"result": result.get("result")},
                error=result.get("error"),
                error_type=result.get("error_type"),
                error_taxonomy=build_error_taxonomy(result.get("error_type"), str(result.get("error") or ""), source="runtime_center"),
                trace_context=prepared.trace_context,
                metadata={"execution": result},
            )
            response_payload = response.to_dict()
        return {
            "ok": response_payload["ok"],
            "resolved_call": prepared.to_dict(),
            "execution": result,
            "error": response_payload["error"],
            "error_type": response_payload["error_type"],
            "response_envelope": response_payload,
        }

    def safe_dispatch(self, *, asset_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self.dispatch(asset_id=asset_id, method=method, params=params)
        except InvocationDispatchError as exc:
            taxonomy = build_error_taxonomy(exc.error_type, str(exc), source="dispatcher")
            return {
                "ok": False,
                "resolved_call": None,
                "execution": None,
                "error": str(exc),
                "error_type": exc.error_type,
                "error_taxonomy": None if taxonomy is None else taxonomy.to_dict(),
            }
        except Exception as exc:
            taxonomy = build_error_taxonomy(type(exc).__name__, str(exc), source="dispatcher")
            return {
                "ok": False,
                "resolved_call": None,
                "execution": None,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "error_taxonomy": None if taxonomy is None else taxonomy.to_dict(),
            }

    def _require_descriptor(self, asset_id: str) -> AssetDescriptorRecord:
        if self._descriptor_provider is not None:
            detail = self._descriptor_provider(asset_id)
            if isinstance(detail, dict) and detail.get("methods"):
                return self._descriptor_from_detail(detail)
        if isinstance(self._asset_center, AssetCenterService):
            return self._asset_center.registry.require_asset(asset_id)
        if hasattr(self._asset_center, "get_asset_detail"):
            detail = self._asset_center.get_asset_detail(asset_id)
            if isinstance(detail, dict):
                return self._descriptor_from_detail(detail)
        registry = getattr(self._asset_center, "_registry", None)
        if registry is not None and hasattr(registry, "require_asset"):
            return registry.require_asset(asset_id)
        raise InvocationDispatchError(f"descriptor for {asset_id} unavailable", error_type="descriptor_unavailable")

    def _list_model_records(self) -> list[Any]:
        if isinstance(self._asset_center, AssetCenterService):
            return self._asset_center.registry.list_models()
        registry = getattr(self._asset_center, "_registry", None)
        if registry is not None and hasattr(registry, "list_models"):
            return registry.list_models()
        return []

    def _descriptor_from_detail(self, detail: dict[str, Any]) -> AssetDescriptorRecord:
        methods = tuple(
            AssetMethodSpec(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                input_schema=item.get("input_schema") or {"type": "object", "properties": {}},
                output_schema=item.get("output_schema") or {},
            )
            for item in (detail.get("methods") or [])
            if isinstance(item, dict)
        )
        requirement_payload = detail.get("model_requirement") or {}
        from app.system.asset_center.models import AssetModelRequirement

        return AssetDescriptorRecord(
            descriptor_version=int(detail.get("descriptor_version") or 1),
            asset_id=str(detail.get("asset_id") or ""),
            kind=str(detail.get("kind") or "system_asset"),
            summary=str(detail.get("summary") or ""),
            detail=str(detail.get("detail") or ""),
            methods=methods,
            model_requirement=AssetModelRequirement(
                preferred_model=requirement_payload.get("preferred_model"),
                fallback_model=requirement_payload.get("fallback_model"),
                minimum_requirements=requirement_payload.get("minimum_requirements") or {},
            ),
            metadata=detail.get("metadata") or {},
        )

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
