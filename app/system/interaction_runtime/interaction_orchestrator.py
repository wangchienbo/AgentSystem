from __future__ import annotations

from typing import Any

from app.system.asset_center.service import AssetCenterService
from app.system.interaction_runtime.context_assembly import ContextAssembly, InteractionContextSnapshot
from app.system.interaction_runtime.decision_protocol import DecisionProtocol


class _DefaultExecutor:
    def invoke(self, asset_id: str, method: str, params: dict) -> dict:
        return {"status": "ok", "asset_id": asset_id, "method": method, "result": {}}


class InteractionOrchestrator:
    def __init__(
        self,
        asset_center_service: Any = None,
        context_assembly: "ContextAssembly | None" = None,
        decision_protocol: DecisionProtocol | None = None,
        executor: Any = None,
    ) -> None:
        self._asset_center = asset_center_service
        self._context_assembly = context_assembly or ContextAssembly(asset_center_service=asset_center_service)
        self._decision_protocol = decision_protocol or DecisionProtocol()
        self._executor = executor or _DefaultExecutor()
        self._snapshot = InteractionContextSnapshot()
        self._last_asset_id: str | None = None

    def process_message(self, user_message: str) -> dict[str, Any]:
        lower = (user_message or "").lower()
        asset_from_msg = self._extract_asset_id(user_message)
        if asset_from_msg:
            self._last_asset_id = asset_from_msg

        # Pronoun resolution: "它的..." / "它..." / "再看看" / "再看" → resolve to last asset
        pronoun_prefix = lower.startswith("它的") or lower.startswith("它") or lower.startswith("再看看") or lower.startswith("再看") or lower.startswith("再看下")
        if pronoun_prefix and self._last_asset_id and not asset_from_msg:
            asset_id = self._last_asset_id
            # Determine what the user wants based on remaining keywords
            if "治理" in lower and "策略" in lower:
                envelope = self._decision_protocol.build_invoke_request(
                    asset_id=asset_id, method="strategy_overview", params={},
                )
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
                return self._make_result(result)
            if "详情" in lower or "能力" in lower or "详细" in lower:
                envelope = self._decision_protocol.build_detail_request(asset_id, self._snapshot)
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
                return self._make_result(result)
            # For "再看看X" where X is an asset keyword, extract and redirect
            if "配置" in lower or "config" in lower:
                self._last_asset_id = "asset:config_center:v1"
            if "self-iteration" in lower or "self_iteration" in lower or "自我迭代" in lower:
                self._last_asset_id = "asset:self_iteration_center:v1"
            if "模型资源" in lower or "模型" in lower:
                self._last_asset_id = "asset:asset_center:v1"
            # Re-check the updated last_asset_id
            asset_id = self._last_asset_id
            if "self_iteration" in asset_id or "self-iteration" in asset_id:
                result = self._decision_protocol.propose_for_self_iteration(
                    user_message=user_message, context=self._snapshot,
                )
                return self._make_result(result)
            if "config" in asset_id:
                result = self._decision_protocol.propose_for_config_center(
                    user_message=user_message, context=self._snapshot,
                )
                return self._make_result(result)

        if self._asset_center:
            refreshed = self._context_assembly.refresh(self._asset_center)
            if refreshed:
                summaries = refreshed.get("summaries", [])
                summary_index = refreshed.get("summary_index", {})
                self._snapshot = self._snapshot.with_summaries(summaries, summary_index)

        # Greetings must come before other keyword checks
        if "你好" in lower or "hello" in lower or "hi" in lower:
            result = self._decision_protocol.resolve_against_context(
                self._decision_protocol.build_text_response("你好，系统正常运行中。有什么可以帮你的？"),
                self._snapshot,
            )
        # "X能做什么" / "X是做什么的" → detail request, not invoke
        elif "能做什么" in lower or "是做什么的" in lower or "能干嘛" in lower:
            asset_id = self._extract_asset_id(user_message)
            if asset_id:
                envelope = self._decision_protocol.build_detail_request(asset_id, self._snapshot)
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
            else:
                result = self._decision_protocol.resolve_against_context(
                    self._decision_protocol.build_text_response("请告诉我你想了解哪个资产？"),
                    self._snapshot,
                )
        # Governance: explicit mention of governance summary (before general self-iteration check)
        elif "治理摘要" in lower or "治理概览" in lower:
            asset_id = "asset:self_iteration_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="governance_summary",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        elif "治理" in lower and "策略" in lower:
            asset_id = "asset:self_iteration_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="strategy_overview",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        elif "治理" in lower:
            result = self._decision_protocol.propose_for_self_iteration(
                user_message=user_message,
                context=self._snapshot,
            )
        # Self-iteration: explicit mention of strategy/policy overview
        elif "策略概览" in lower or "策略总览" in lower or ("策略" in lower and "自我迭代" in lower):
            asset_id = "asset:self_iteration_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="strategy_overview",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        # Self-iteration: explicit mention for list/detail queries
        elif "自我迭代" in lower or "self-iteration" in lower or "self_iteration" in lower:
            # If "不存在" / "没有" → unknown method, text response
            if "不存在" in lower or "没有" in lower:
                result = self._decision_protocol.resolve_against_context(
                    self._decision_protocol.build_text_response("该资产没有你请求的方法。请查看资产详情了解可用方法列表。"),
                    self._snapshot,
                )
            # If "跑一下" / "执行" / "运行" → invoke strategy_overview
            elif "跑一下" in lower or "执行" in lower or "运行" in lower:
                asset_id = "asset:self_iteration_center:v1"
                envelope = self._decision_protocol.build_invoke_request(
                    asset_id=asset_id,
                    method="strategy_overview",
                    params={},
                )
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
            # If "列表" or "list" → list_self_iteration_assets
            elif "列表" in lower or "list" in lower:
                asset_id = "asset:self_iteration_center:v1"
                envelope = self._decision_protocol.build_invoke_request(
                    asset_id=asset_id,
                    method="list_self_iteration_assets",
                    params={},
                )
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
            # If "详细" / "能力" / "详情" → detail request
            elif "详细" in lower or "能力" in lower or "详情" in lower:
                envelope = self._decision_protocol.build_detail_request("asset:self_iteration_center:v1", self._snapshot)
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
            # Otherwise → propose (governance/general)
            else:
                result = self._decision_protocol.propose_for_self_iteration(
                    user_message=user_message,
                    context=self._snapshot,
                )
        # Model resource: "模型资源" / "备选模型" / "可用模型" → asset_center
        elif "模型资源" in lower or "备选模型" in lower or "可用模型" in lower:
            asset_id = "asset:asset_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="list_models",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        # Model config summary: "总结...模型配置" / "模型配置...总结"
        elif "模型配置" in lower and "总结" in lower:
            asset_id = "asset:config_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="model_config_summary",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        # Config center: explicit mention
        elif "配置中心" in lower or "config_center" in lower:
            result = self._decision_protocol.propose_for_config_center(
                user_message=user_message,
                context=self._snapshot,
            )
        # Vague config change without specific parameter → clarification
        elif lower == "改一下配置" or lower == "改配置" or lower == "修改配置" or lower == "改下配置":
            result = self._decision_protocol.resolve_against_context(
                self._decision_protocol.build_text_response("你想改哪个配置？请告诉我具体要修改的参数，比如超时时间或最大token数。"),
                self._snapshot,
            )
        # Config action: "改...配置" / "把...改成" → config center invoke
        elif "改" in lower and "配置" in lower or "把" in lower and ("改成" in lower or "改为" in lower):
            result = self._decision_protocol.propose_for_config_center(
                user_message=user_message,
                context=self._snapshot,
            )
        # Bare "配置" without action verb → clarification (text)
        elif "配置" in lower and "改" not in lower and "查" not in lower and "看" not in lower:
            result = self._decision_protocol.resolve_against_context(
                self._decision_protocol.build_text_response("你想了解配置的哪个方面？例如：查看当前配置、修改某个参数、或者模型配置摘要。"),
                self._snapshot,
            )
        # Asset health check: "各资产都健康" → list_models on asset_center
        elif "资产" in lower and "健康" in lower:
            asset_id = "asset:asset_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="list_models",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        # Status check: "状态" / "status"
        elif "状态" in lower or "status" in lower:
            asset_id = "asset:self_iteration_center:v1"
            envelope = self._decision_protocol.build_invoke_request(
                asset_id=asset_id,
                method="strategy_overview",
                params={},
            )
            result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
        # Summary / wrap-up (must be specific enough to not catch model_config_summary above)
        elif "总结" in lower or "总结报告" in lower or "summary" in lower or "总结做了什么" in lower or "好了" in lower:
            result = self._decision_protocol.resolve_against_context(
                self._decision_protocol.build_text_response("本轮交互已完成。"),
                self._snapshot,
            )
        # Asset detail / list
        elif "资产" in lower or "asset" in lower or "功能" in lower or "详情" in lower or "detail" in lower:
            asset_id = self._extract_asset_id(user_message)
            if asset_id:
                envelope = self._decision_protocol.build_detail_request(asset_id, self._snapshot)
                result = self._decision_protocol.resolve_against_context(envelope, self._snapshot)
            else:
                result = self._decision_protocol.resolve_against_context(
                    self._decision_protocol.build_text_response(
                        self._build_asset_list_text(),
                    ),
                    self._snapshot,
                )
        # Fallback
        else:
            result = self._decision_protocol.resolve_against_context(
                self._decision_protocol.build_text_response("请告诉我你想做什么，例如查看状态、了解某个资产、或者执行某个操作。"),
                self._snapshot,
            )

        envelope_dict = result.envelope.to_dict()
        return {
            "decision": envelope_dict["decision"],
            "text": envelope_dict.get("text"),
            "need_asset_detail_id": envelope_dict.get("need_asset_detail_id"),
            "invoke": envelope_dict.get("invoke"),
            "metadata": envelope_dict.get("metadata", {}),
            "resolved_action": result.resolved_action,
        }

    def _make_result(self, result) -> dict[str, Any]:
        envelope_dict = result.envelope.to_dict()
        return {
            "decision": envelope_dict["decision"],
            "text": envelope_dict.get("text"),
            "need_asset_detail_id": envelope_dict.get("need_asset_detail_id"),
            "invoke": envelope_dict.get("invoke"),
            "metadata": envelope_dict.get("metadata", {}),
            "resolved_action": result.resolved_action,
        }

    def _extract_asset_id(self, message: str) -> str | None:
        lower = (message or "").lower()
        if "self-iteration" in lower or "self_iteration" in lower or "自我迭代" in lower:
            return "asset:self_iteration_center:v1"
        if "config_center" in lower or "配置中心" in lower or "config center" in lower:
            return "asset:config_center:v1"
        if "asset_center" in lower or "资产中心" in lower:
            return "asset:asset_center:v1"
        return None

    def _build_asset_list_text(self) -> str:
        if not self._asset_center:
            return "资产列表暂时不可用"
        assets = self._asset_center.list_assets()
        lines = ["当前可用资产："]
        for asset in assets:
            lines.append(f"- {asset['asset_id']}: {asset['summary']}")
        return "\n".join(lines)

    def get_debug_view(self) -> dict[str, Any]:
        return {
            "loaded_summaries": self._snapshot.list_summary_asset_ids(),
            "loaded_details": sorted(self._snapshot.details.keys()),
            "summary_epochs": {
                asset_id: self._snapshot.summary_epoch(asset_id)
                for asset_id in self._snapshot.list_summary_asset_ids()
            },
            "detail_epochs": {
                asset_id: self._snapshot.detail_epoch(asset_id)
                for asset_id in sorted(self._snapshot.details.keys())
            },
        }
