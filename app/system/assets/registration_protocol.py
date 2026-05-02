from __future__ import annotations

from typing import Any

from app.system.asset_center.service import AssetCenterService
from app.system.assets.base_asset import AssetMethodHandler, BaseAsset, RegisteredAsset
from app.system.invocation.invocation_compliance import InvocationComplianceValidator
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope


class AssetRegistrationProtocol:
    def __init__(self, *, auto_wrap_runtime_invocation: bool = True, compliance_validator: InvocationComplianceValidator | None = None) -> None:
        self._auto_wrap_runtime_invocation = auto_wrap_runtime_invocation
        self._compliance_validator = compliance_validator or InvocationComplianceValidator()

    def materialize(self, asset: BaseAsset) -> RegisteredAsset:
        descriptor = asset.build_descriptor()
        descriptor = self._normalize_descriptor_metadata(descriptor)
        compliance = self._compliance_validator.validate_registration_descriptor(descriptor)
        if not compliance.compliant:
            raise ValueError("registration compliance validation failed: " + "; ".join(compliance.reasons))
        method_mappings = asset.build_method_mappings()
        service_ref = asset.get_service_ref()
        if self._auto_wrap_runtime_invocation:
            method_mappings = self._wrap_method_mappings(asset_id=descriptor.asset_id, method_mappings=method_mappings)
        return RegisteredAsset(
            descriptor=descriptor,
            service_ref=service_ref,
            method_mappings=method_mappings,
        )

    def register(self, asset: BaseAsset, asset_center: AssetCenterService) -> RegisteredAsset:
        registered = self.materialize(asset)
        stored_descriptor = asset_center.register_asset(registered.descriptor)
        return RegisteredAsset(
            descriptor=stored_descriptor,
            service_ref=registered.service_ref,
            method_mappings=registered.method_mappings,
        )

    def reregister(self, asset: BaseAsset, asset_center: AssetCenterService) -> RegisteredAsset:
        return self.register(asset, asset_center)

    def _normalize_descriptor_metadata(self, descriptor):
        metadata = dict(descriptor.metadata or {})
        if self._auto_wrap_runtime_invocation:
            # Phase P: auto-inject compliance defaults so existing assets can still register
            metadata.setdefault("runtime_wrapper_compatibility", True)
            metadata.setdefault("session_binding_support", "supported")
            metadata.setdefault("invocation_contract_version", "phase-p-v1")
            metadata.setdefault("endpoint_requirement", "none")
            metadata.setdefault("tool_vllm_usage_mode", "local_session_only")
        return type(descriptor)(**{**descriptor.__dict__, "metadata": metadata})

    def _wrap_method_mappings(self, *, asset_id: str, method_mappings: dict[str, AssetMethodHandler]) -> dict[str, AssetMethodHandler]:
        wrapped: dict[str, AssetMethodHandler] = {}
        for method_name, handler in method_mappings.items():
            wrapped[method_name] = self._wrap_single_handler(asset_id=asset_id, method_name=method_name, handler=handler)
        return wrapped

    def _wrap_single_handler(self, *, asset_id: str, method_name: str, handler: AssetMethodHandler) -> AssetMethodHandler:
        def wrapped_handler(*args: Any, **kwargs: Any) -> Any:
            runtime_envelope = kwargs.pop("__invocation_envelope__", None)
            local_session_id = kwargs.get("local_session_id")
            try:
                result = handler(*args, **kwargs)
            except TypeError as exc:
                # Only fall back if the error is specifically about unexpected keyword argument
                msg = str(exc).lower()
                if "local_session_id" in msg or "unexpected keyword" in msg:
                    fallback_kwargs = {k: v for k, v in kwargs.items() if k != "local_session_id"}
                    try:
                        result = handler(*args, **fallback_kwargs)
                    except TypeError:
                        raise exc
                else:
                    raise
            if isinstance(result, dict):
                metadata = dict(result.get("metadata") or {})
                metadata.setdefault("runtime_wrapper", True)
                metadata.setdefault("asset_id", asset_id)
                metadata.setdefault("method", method_name)
                if local_session_id is not None:
                    metadata.setdefault("local_session_id", local_session_id)
                if isinstance(runtime_envelope, InvocationRequestEnvelope):
                    metadata.setdefault("request_id", runtime_envelope.request_id)
                    metadata.setdefault("upstream_session_id", runtime_envelope.session.upstream_session_id if runtime_envelope.session else None)
                if "metadata" in result:
                    result = {**result, "metadata": metadata}
                else:
                    result = {**result, "metadata": metadata}
            return result

        return wrapped_handler
