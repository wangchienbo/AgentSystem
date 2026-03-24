from app.models.operator_contracts import OperatorPageMeta
from app.models.refinement_loop import RefinementPageMeta
from app.models.workflow_observability import WorkflowPageMeta


def test_operator_page_meta_shared_defaults() -> None:
    meta = OperatorPageMeta()
    assert meta.returned_count == 0
    assert meta.total_count == 0
    assert meta.filtered_count == 0
    assert meta.has_more is False
    assert meta.window_since is None
    assert meta.next_cursor is None


def test_workflow_and_refinement_page_meta_extend_shared_contract() -> None:
    workflow_meta = WorkflowPageMeta(returned_count=1, total_count=3, filtered_count=2, has_more=True, unresolved_count=1)
    refinement_meta = RefinementPageMeta(returned_count=1, total_count=3, filtered_count=2, has_more=True)

    assert workflow_meta.total_count == 3
    assert workflow_meta.filtered_count == 2
    assert workflow_meta.unresolved_count == 1
    assert refinement_meta.total_count == 3
    assert refinement_meta.filtered_count == 2
    assert refinement_meta.has_more is True
