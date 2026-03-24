from app.models.operator_dashboards import OperatorDashboardCore
from app.models.refinement_loop import RefinementGovernanceDashboard, RefinementOverview, RefinementStatsSummary
from app.models.workflow_observability import WorkflowDashboardSummary, WorkflowHealthSummary, WorkflowOverview, WorkflowStatsSummary


def test_operator_dashboard_core_exposes_shared_overview_and_stats_fields() -> None:
    dashboard = OperatorDashboardCore[dict, dict](overview={"kind": "overview"}, stats={"kind": "stats"})
    assert dashboard.overview == {"kind": "overview"}
    assert dashboard.stats == {"kind": "stats"}


def test_workflow_and_refinement_dashboards_extend_shared_core() -> None:
    workflow = WorkflowDashboardSummary(
        overview=WorkflowOverview(diagnostics={}, health=WorkflowHealthSummary()),
        stats=WorkflowStatsSummary(),
        recent_timeline={"items": [], "meta": {}},
    )
    refinement = RefinementGovernanceDashboard(
        overview=RefinementOverview(app_instance_id="app.demo"),
        stats=RefinementStatsSummary(app_instance_id="app.demo"),
        recent_queue={"items": [], "meta": {}},
        recent_failed_hypotheses={"items": [], "meta": {}},
    )

    assert workflow.overview.health.health_status == "unknown"
    assert workflow.stats.total_executions == 0
    assert refinement.overview.app_instance_id == "app.demo"
    assert refinement.stats.app_instance_id == "app.demo"
