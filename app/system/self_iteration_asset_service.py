from __future__ import annotations

from typing import Any

from app.refinement.refinement_memory import RefinementMemoryStore
from app.skills.skill_asset_service import SkillAssetService
from app.system.self_diagnosis import SelfDiagnosisService
from app.system.self_dev import SelfDevService
from app.system.self_evolution import SelfEvolutionService
from app.system.self_iteration_assets import build_self_iteration_asset_summaries
from app.system.self_iteration_strategy import (
    build_asset_query_action,
    build_follow_up_actions,
    build_strategy_route,
    select_recommended_next_asset,
)


class SelfIterationAssetService:
    def __init__(self, memory: RefinementMemoryStore | None = None, diagnosis: SelfDiagnosisService | None = None, dev: SelfDevService | None = None, skills: SkillAssetService | None = None, evolution: SelfEvolutionService | None = None) -> None:
        self._memory = memory or RefinementMemoryStore()
        self._diagnosis = diagnosis or SelfDiagnosisService(root_dir="app")
        self._dev = dev or SelfDevService(root_dir="app")
        self._skills = skills
        self._evolution = evolution

    def diagnose_codebase(self, *, include_god_objects: bool = True) -> dict[str, Any]:
        """运行只读代码健康诊断（导入缺陷 + God Object），供自治开发闭环的观察层使用。"""
        return self._diagnosis.diagnose_codebase(include_god_objects=include_god_objects)

    def propose_code_improvements(self, *, include_god_objects: bool = True) -> dict[str, Any]:
        """自治开发闭环的分析→方案层：基于诊断生成代码重构方案（供人类审批，不自动应用）。"""
        diagnosis = self._diagnosis.diagnose_codebase(include_god_objects=include_god_objects)
        return self._dev.build_dev_report(diagnosis)

    # ─── 自动待办裁决（打通待办收敛闭环） ─────────────────────────
    def record_todo_decision(self, file: str, target: str, *, status: str = "declined", rationale: str = "") -> dict[str, Any]:
        """记录对某重构目标的裁决（done=已重构 / declined=判定不值得拆）。

        记录后，propose_code_improvements 生成的 todo_queue 将不再包含该目标，
        实现自动待办的跨会话收敛（避免每次 review 重复建议已评估目标）。
        """
        return self._dev.record_todo_decision(file, target, status=status, rationale=rationale)

    def list_todo_decisions(self) -> list[dict[str, Any]]:
        """列出全部已裁决目标（供审计/查询）。"""
        return self._dev.list_todo_decisions()

    def clear_todo_decisions(self) -> dict[str, Any]:
        """清空全部裁决记录（重置自动待办）。返回清空条数。"""
        return {"cleared": self._dev.clear_todo_decisions()}

    # ─── Phase 2：能力自举（系统自己生成并注册新 skill 资产） ────────────────

    def _require_skill_service(self) -> SkillAssetService:
        if self._skills is None:
            raise RuntimeError("能力自举需要注入 SkillAssetService")
        return self._skills

    def bootstrap_skill_asset(
        self,
        *,
        skill_id: str,
        name: str,
        description: str = "",
        template_type: str = "text_transform",
        status: str = "candidate",
        source_workflow: str | None = None,
    ) -> dict[str, Any]:
        """能力自举：生成一个新的 skill 资产脚手架并注册到资产索引。

        默认落 candidate（草稿），由人类审批后 promote 到 core。
        """
        from app.models.generated_skill import GeneratedSkillRequest

        svc = self._require_skill_service()
        request = GeneratedSkillRequest(
            skill_id=skill_id,
            name=name,
            description=description,
            template_type=template_type,
        )
        asset, metadata = svc.create_asset_scaffold(
            request,
            adapter_kind="executable",
            status=status,
            source_workflow=source_workflow,
        )
        return {
            "skill_id": skill_id,
            "status": metadata.asset_status,
            "asset_dir": asset.asset_dir,
            "manifest_path": asset.manifest_path,
            "entrypoint_path": asset.entrypoint_path,
            "readme_path": asset.readme_path,
            "smoke_test_path": f"{asset.asset_dir}/tests/test_smoke.py",
            "message": "skill 资产脚手架已生成（candidate），可运行 smoke test 验证后 promote 到 core",
        }

    def list_bootstrapped_skills(self, status: str | None = None) -> list[dict[str, Any]]:
        """列出已自举的 skill 资产（默认全部状态）。"""
        svc = self._require_skill_service()
        entries = svc.list_assets(status=status)
        return [
            {
                "skill_id": e.skill_id,
                "status": e.asset_status,
                "version": e.version,
                "origin": e.asset_origin,
                "accepted": e.accepted,
            }
            for e in entries
        ]

    def promote_skill_asset(self, skill_id: str, accepted_by: str = "") -> dict[str, Any]:
        """人类审批：把 candidate skill 资产提升为 core（真正接入运行时能力）。"""
        svc = self._require_skill_service()
        metadata = svc.promote_candidate_to_core(skill_id, accepted_by=accepted_by)
        return {
            "skill_id": skill_id,
            "status": metadata.asset_status,
            "accepted": metadata.accepted,
            "accepted_by": metadata.accepted_by,
            "message": "skill 资产已提升为 core，能力自举完成",
        }

    def verify_bootstrapped_skills(self) -> dict[str, Any]:
        """校验已自举 skill 资产的完整性（manifest/metadata/entrypoint/smoke test）。"""
        svc = self._require_skill_service()
        results = svc.check_consistency()
        return {
            "total": len(results),
            "ok": sum(1 for r in results if r.ok),
            "failed": [{"skill_id": r.skill_id, "issues": [i.kind for i in r.issues]} for r in results if not r.ok],
            "results": [{"skill_id": r.skill_id, "ok": r.ok} for r in results],
        }

    # ─── Phase 3：长期进化（周期性代码审查 + 跨会话演进历史） ─────────────

    def _require_evolution(self) -> SelfEvolutionService:
        if self._evolution is None:
            raise RuntimeError("长期进化需要注入 SelfEvolutionService")
        return self._evolution

    def run_periodic_review(self, *, force: bool = False) -> dict[str, Any]:
        """长期进化：周期性代码健康审查（默认 24h 间隔，force 强制重跑）。

        每次审查把健康度快照持久化，跨会话可对比代码演进。
        """
        return self._require_evolution().run_periodic_review(force=force)

    def get_evolution_history(self, *, limit: int = 20) -> dict[str, Any]:
        """长期进化：读取历史审查记录，展示代码健康度随时间演进。"""
        return self._require_evolution().get_evolution_history(limit=limit)

    def list_self_iteration_assets(self, replay_session_id: str | None = None, comparison_limit: int = 5) -> list[dict[str, Any]]:
        return build_self_iteration_asset_summaries(
            memory=self._memory,
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        )

    def query_self_iteration_asset(self, asset_id: str, replay_session_id: str | None = None, comparison_limit: int = 5) -> dict[str, Any] | None:
        for asset in self.list_self_iteration_assets(
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        ):
            if asset.get("asset_id") == asset_id:
                return asset
        return None

    def get_self_iteration_strategy_overview(self, replay_session_id: str | None = None, comparison_limit: int = 5) -> dict[str, Any]:
        assets = self.list_self_iteration_assets(
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        )
        by_id = {
            asset.get("asset_id"): asset
            for asset in assets
            if isinstance(asset, dict) and asset.get("asset_id")
        }

        governance_dashboard = by_id.get("self_iteration.governance_dashboard") or {}
        governance_triggers = by_id.get("self_iteration.governance_triggers") or {}
        refinement_backlog = by_id.get("self_iteration.refinement_backlog") or {}
        observation_digest = by_id.get("self_iteration.live_observation_digest") or {}
        regression_runs = by_id.get("self_iteration.regression_runs") or {}

        dashboard_detail = governance_dashboard.get("detail") if isinstance(governance_dashboard.get("detail"), dict) else {}
        trigger_detail = governance_triggers.get("detail") if isinstance(governance_triggers.get("detail"), dict) else {}
        backlog_detail = refinement_backlog.get("detail") if isinstance(refinement_backlog.get("detail"), dict) else {}
        observation_detail = observation_digest.get("detail") if isinstance(observation_digest.get("detail"), dict) else {}
        regression_detail = regression_runs.get("detail") if isinstance(regression_runs.get("detail"), dict) else {}

        pressure_snapshot = {
            "risk_flag_count": int(dashboard_detail.get("risk_flag_count") or 0),
            "trigger_count": int(trigger_detail.get("trigger_count") or 0),
            "queue_count": int(backlog_detail.get("queue_count") or 0),
            "failed_hypothesis_count": int(backlog_detail.get("failed_hypothesis_count") or 0),
            "total_observations": int(observation_detail.get("total_observations") or 0),
            "run_count": int(regression_detail.get("run_count") or 0),
        }

        recommended_next_asset = select_recommended_next_asset(
            pressure_snapshot=pressure_snapshot,
        )
        recommended_next_action = build_asset_query_action(
            recommended_next_asset["asset_id"],
            reason=recommended_next_asset["reason"],
        )
        follow_up_actions = build_follow_up_actions(
            recommended_asset_id=recommended_next_asset["asset_id"],
        )
        route = build_strategy_route(
            recommended_next_asset=recommended_next_asset,
            recommended_next_action=recommended_next_action,
        )

        return {
            "system_view": {
                "observe": [
                    "self_iteration.regression_runs",
                    "self_iteration.live_observation_digest",
                ],
                "summarize": [
                    "self_iteration.governance_dashboard",
                ],
                "act": [
                    "self_iteration.governance_triggers",
                    "self_iteration.refinement_backlog",
                ],
            },
            "recommended_next_asset": recommended_next_asset,
            "recommended_next_action": recommended_next_action,
            "follow_up_actions": follow_up_actions,
            "route": route,
            "pressure_snapshot": pressure_snapshot,
            "assets": assets,
        }
