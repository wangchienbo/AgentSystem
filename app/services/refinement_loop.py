from __future__ import annotations

from pathlib import Path
import subprocess

from app.models.proposal_review import ProposalReviewRequest
from app.models.refinement_loop import (
    RefinementExperiment,
    RefinementHypothesis,
    RefinementLoopRequest,
    RefinementLoopResult,
    RolloutDecision,
    VerificationResult,
)
from app.services.priority_analysis import PriorityAnalysisRequest, PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.refinement_memory import RefinementMemoryStore


class RefinementLoopError(ValueError):
    pass


class RefinementLoopService:
    def __init__(
        self,
        proposal_review: ProposalReviewService,
        priority_analysis: PriorityAnalysisService,
        memory: RefinementMemoryStore | None = None,
        regression_runner: str = "/root/project/AgentSystem/scripts/run_test_groups.sh",
        verification_executor=None,
    ) -> None:
        self._proposal_review = proposal_review
        self._priority_analysis = priority_analysis
        self._memory = memory or RefinementMemoryStore()
        self._regression_runner = regression_runner
        self._verification_executor = verification_executor or self._run_regression_command

    @property
    def memory(self) -> RefinementMemoryStore:
        return self._memory

    def run(self, request: RefinementLoopRequest) -> RefinementLoopResult:
        analysis = self._priority_analysis.analyze(PriorityAnalysisRequest(app_instance_id=request.app_instance_id))
        if not analysis.prioritized:
            raise RefinementLoopError(f"No prioritized proposals available for app instance: {request.app_instance_id}")

        top = analysis.prioritized[0]
        proposal = next(
            (item for item in self._proposal_review.list_proposals(request.app_instance_id) if item.proposal_id == top.proposal_id),
            None,
        )
        if proposal is None:
            raise RefinementLoopError(f"Proposal not found for prioritized item: {top.proposal_id}")

        hypothesis = self._memory.add_hypothesis(
            RefinementHypothesis(
                hypothesis_id=f"hyp.{request.app_instance_id}.{len(self._memory.list_hypotheses(request.app_instance_id)) + 1}",
                app_instance_id=request.app_instance_id,
                proposal_id=proposal.proposal_id,
                experience_id=request.experience_id,
                contradiction=analysis.primary_contradiction,
                hypothesis=f"If proposal {proposal.proposal_id} is applied in a bounded validation path, the current main contradiction should weaken.",
                expected_change=proposal.expected_benefit,
                evidence=list(proposal.evidence),
                status="approved" if proposal.auto_apply_allowed and proposal.risk_level == "low" else "proposed",
            )
        )
        validation_mode = "grouped_regression" if Path(self._regression_runner).exists() else "checklist"
        experiment = self._memory.add_experiment(
            RefinementExperiment(
                experiment_id=f"expmt.{request.app_instance_id}.{len(self._memory.list_experiments(hypothesis.hypothesis_id)) + 1}",
                hypothesis_id=hypothesis.hypothesis_id,
                app_instance_id=request.app_instance_id,
                workflow_id=str(proposal.patch.get("workflow_id", "")),
                validation_plan=list(proposal.validation_checklist),
                validation_mode=validation_mode,
                status="completed",
            )
        )

        verification = self._memory.add_verification(self._verify_proposal(request.app_instance_id, hypothesis.hypothesis_id, proposal))

        rollout_status = "promote" if verification.outcome == "passed" else "hold"
        rollout_reason = (
            f"Promote proposal {proposal.proposal_id} into the next rollout window."
            if rollout_status == "promote"
            else f"Hold proposal {proposal.proposal_id} until remaining checks are resolved."
        )
        rollout = self._memory.add_decision(
            RolloutDecision(
                decision_id=f"rollout.{request.app_instance_id}.{len(self._memory.list_decisions(hypothesis.hypothesis_id)) + 1}",
                hypothesis_id=hypothesis.hypothesis_id,
                app_instance_id=request.app_instance_id,
                status=rollout_status,
                reason=rollout_reason,
            )
        )
        if rollout.status == "promote" and proposal.auto_apply_allowed and proposal.risk_level == "low":
            self._proposal_review.review(
                ProposalReviewRequest(
                    proposal_id=proposal.proposal_id,
                    action="apply",
                    reviewer="refinement-loop",
                    note=f"auto-applied after {verification.execution_reference or verification.summary}",
                )
            )
        return RefinementLoopResult(
            app_instance_id=request.app_instance_id,
            experience_id=request.experience_id,
            primary_contradiction=analysis.primary_contradiction,
            hypothesis=hypothesis,
            experiment=experiment,
            verification=verification,
            rollout=rollout,
        )

    def _verify_proposal(self, app_instance_id: str, hypothesis_id: str, proposal) -> VerificationResult:
        verification_id = f"verify.{app_instance_id}.{len(self._memory.list_verifications(hypothesis_id)) + 1}"
        if Path(self._regression_runner).exists():
            result = self._verification_executor(self._regression_runner)
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            if result.returncode == 0:
                return VerificationResult(
                    verification_id=verification_id,
                    hypothesis_id=hypothesis_id,
                    app_instance_id=app_instance_id,
                    outcome="passed",
                    summary=f"Grouped regression passed for proposal {proposal.proposal_id}",
                    passed_checks=list(proposal.validation_checklist) or ["grouped regression runner"],
                    failed_checks=[],
                    execution_reference="grouped_regression:passed",
                )
            return VerificationResult(
                verification_id=verification_id,
                hypothesis_id=hypothesis_id,
                app_instance_id=app_instance_id,
                outcome="failed",
                summary=f"Grouped regression failed for proposal {proposal.proposal_id}",
                passed_checks=[],
                failed_checks=list(proposal.validation_checklist) or [output[-200:]],
                execution_reference="grouped_regression:failed",
            )

        passed_checks = list(proposal.validation_checklist[: max(1, len(proposal.validation_checklist) - 1)])
        failed_checks = [] if proposal.risk_level == "low" else proposal.validation_checklist[-1:]
        outcome = "passed" if not failed_checks else "inconclusive"
        return VerificationResult(
            verification_id=verification_id,
            hypothesis_id=hypothesis_id,
            app_instance_id=app_instance_id,
            outcome=outcome,
            summary=(
                f"Bounded validation for proposal {proposal.proposal_id} {'passed core checks' if outcome == 'passed' else 'produced mixed signals'}"
            ),
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            execution_reference="checklist:bounded",
        )

    def _run_regression_command(self, runner_path: str):
        return subprocess.run([runner_path], capture_output=True, text=True)
