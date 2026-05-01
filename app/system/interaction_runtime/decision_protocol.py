from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import InteractionContextSnapshot


class InteractionDecisionProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class DecisionProtocolResult:
    envelope: InteractionDecisionEnvelope
    resolved_action: str


class DecisionProtocol:
    def normalize(self, envelope: InteractionDecisionEnvelope) -> DecisionProtocolResult:
        envelope.validate()
        if envelope.decision == "text":
            return DecisionProtocolResult(envelope=envelope, resolved_action="reply_text")
        if envelope.decision == "need_asset_detail_id":
            return DecisionProtocolResult(envelope=envelope, resolved_action="load_detail")
        if envelope.decision == "invoke":
            return DecisionProtocolResult(envelope=envelope, resolved_action="invoke_method")
        raise InteractionDecisionProtocolError(f"Unsupported decision: {envelope.decision}")

    def resolve_against_context(
        self,
        envelope: InteractionDecisionEnvelope,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        result = self.normalize(envelope)
        if envelope.decision == "need_asset_detail_id":
            asset_id = envelope.need_asset_detail_id or ""
            if context.has_detail(asset_id) and not context.is_detail_stale(asset_id):
                return DecisionProtocolResult(
                    envelope=InteractionDecisionEnvelope(
                        decision="text",
                        text=f"detail already loaded: {asset_id}",
                        metadata={"detail_cache_hit": True, "asset_id": asset_id},
                    ),
                    resolved_action="reply_text",
                )
            if context.has_detail(asset_id) and context.is_detail_stale(asset_id):
                return DecisionProtocolResult(
                    envelope=InteractionDecisionEnvelope(
                        decision="need_asset_detail_id",
                        need_asset_detail_id=asset_id,
                        metadata={
                            "detail_cache_stale": True,
                            "asset_id": asset_id,
                            "detail_epoch": context.detail_epoch(asset_id),
                            "summary_epoch": context.summary_epoch(asset_id),
                        },
                    ),
                    resolved_action="load_detail",
                )
            if not context.has_summary(asset_id):
                return DecisionProtocolResult(
                    envelope=InteractionDecisionEnvelope(
                        decision="text",
                        text=f"asset detail unavailable: {asset_id}",
                        metadata={"missing_asset_detail": True, "asset_id": asset_id},
                    ),
                    resolved_action="reply_text",
                )
        if envelope.decision == "invoke":
            invoke = envelope.invoke or {}
            if not invoke.get("asset_id") or not invoke.get("method"):
                raise InteractionDecisionProtocolError("invoke payload requires asset_id and method")
        return result

    def propose_for_self_iteration(
        self,
        *,
        user_message: str,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        text = (user_message or "").lower()
        asset_id = "asset:self_iteration_center:v1"

        if any(keyword in text for keyword in ("详情", "detail")) and not context.has_detail(asset_id):
            return self.resolve_against_context(
                InteractionDecisionEnvelope(
                    decision="need_asset_detail_id",
                    need_asset_detail_id=asset_id,
                    metadata={"route": "self_iteration"},
                ),
                context,
            )
        if any(keyword in text for keyword in ("列表", "list", "摘要")):
            return self.resolve_against_context(
                InteractionDecisionEnvelope(
                    decision="invoke",
                    invoke={
                        "asset_id": asset_id,
                        "method": "list_self_iteration_assets",
                        "params": {},
                    },
                    metadata={"route": "self_iteration"},
                ),
                context,
            )
        return self.resolve_against_context(
            InteractionDecisionEnvelope(
                decision="need_asset_detail_id",
                need_asset_detail_id=asset_id,
                metadata={"route": "self_iteration", "fallback": True},
            ),
            context,
        )

    def propose_for_config_center(
        self,
        *,
        user_message: str,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        text = (user_message or "").lower()
        asset_id = "asset:config_center:v1"

        if any(keyword in text for keyword in ("详情", "detail")) and not context.has_detail(asset_id):
            return self.resolve_against_context(
                InteractionDecisionEnvelope(
                    decision="need_asset_detail_id",
                    need_asset_detail_id=asset_id,
                    metadata={"route": "config_center"},
                ),
                context,
            )
        # Explicit action: get/query
        if any(keyword in text for keyword in ("获取", "查询", "查", "看", "当前", "get")):
            return self.resolve_against_context(
                InteractionDecisionEnvelope(
                    decision="invoke",
                    invoke={
                        "asset_id": asset_id,
                        "method": "get_config",
                        "params": {"skill_id": "maoxuan_skill"},
                    },
                    metadata={"route": "config_center"},
                ),
                context,
            )
        # Specific parameter change
        if any(keyword in text for keyword in ("超时", "token", "max_", "改为", "改成")):
            return self.resolve_against_context(
                InteractionDecisionEnvelope(
                    decision="invoke",
                    invoke={
                        "asset_id": asset_id,
                        "method": "update_config",
                        "params": {},
                    },
                    metadata={"route": "config_center"},
                ),
                context,
            )
        # Otherwise: request detail so the user can see what's available
        return self.resolve_against_context(
            InteractionDecisionEnvelope(
                decision="need_asset_detail_id",
                need_asset_detail_id=asset_id,
                metadata={"route": "config_center", "fallback": True},
            ),
            context,
        )

    def build_detail_request(self, asset_id: str, context: InteractionContextSnapshot) -> InteractionDecisionEnvelope:
        return InteractionDecisionEnvelope(
            decision="need_asset_detail_id",
            need_asset_detail_id=asset_id,
            metadata={"route": "general"},
        )

    def build_text_response(self, text: str) -> InteractionDecisionEnvelope:
        return InteractionDecisionEnvelope(
            decision="text",
            text=text,
        )

    def build_invoke_request(
        self,
        *,
        asset_id: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> InteractionDecisionEnvelope:
        return InteractionDecisionEnvelope(
            decision="invoke",
            invoke={"asset_id": asset_id, "method": method, "params": params or {}},
            metadata={"route": "general"},
        )
