from __future__ import annotations

from app.models.context_summary import ContextSummary
from app.models.context_policy import ContextCompactionPolicy
from app.services.app_context_store import AppContextStore
from app.services.runtime_state_store import RuntimeStateStore


class ContextCompactionError(ValueError):
    pass


class ContextCompactionService:
    def __init__(
        self,
        app_context_store: AppContextStore,
        workflow_executor,
        store: RuntimeStateStore | None = None,
    ) -> None:
        self._app_context_store = app_context_store
        self._workflow_executor = workflow_executor
        self._store = store
        self._summaries: dict[str, ContextSummary] = {}
        self._policies: dict[str, ContextCompactionPolicy] = {}

    def set_policy(self, policy: ContextCompactionPolicy) -> ContextCompactionPolicy:
        self._policies[policy.app_instance_id] = policy
        self._persist()
        return policy

    def get_policy(self, app_instance_id: str) -> ContextCompactionPolicy:
        return self._policies.get(app_instance_id, ContextCompactionPolicy(app_instance_id=app_instance_id))

    def should_compact(self, app_instance_id: str, event: str) -> bool:
        policy = self.get_policy(app_instance_id)
        context = self._app_context_store.get_context(app_instance_id)
        if len(context.entries) >= policy.max_context_entries:
            return True
        if event == "workflow_complete" and policy.compact_on_workflow_complete:
            return True
        if event == "workflow_failure" and policy.compact_on_workflow_failure:
            return True
        return False

    def compact(self, app_instance_id: str) -> ContextSummary:
        context = self._app_context_store.get_context(app_instance_id)
        history = self._workflow_executor.list_history(app_instance_id)

        decisions = [item.key for item in context.entries if item.section == "decisions"][-5:]
        constraints = [item.key for item in context.entries if item.section == "constraints"][-5:]
        open_loops = [item.key for item in context.entries if item.section == "open_loops"][-5:]
        artifacts = [item.key for item in context.entries if item.section == "artifacts"][-5:]
        detail_refs = [f"workflow:{item.workflow_id}:{item.trigger}" for item in history[-5:]]

        summary = ContextSummary(
            app_instance_id=app_instance_id,
            layer="summary",
            current_goal=context.current_goal,
            current_stage=context.current_stage,
            decisions=decisions,
            constraints=constraints,
            open_loops=open_loops,
            artifacts=artifacts,
            detail_refs=detail_refs,
            metadata={"history_count": len(history), "context_entry_count": len(context.entries)},
        )
        self._summaries[app_instance_id] = summary
        self._persist()
        return summary

    def build_working_set(self, app_instance_id: str) -> ContextSummary:
        context = self._app_context_store.get_context(app_instance_id)
        history = self._workflow_executor.list_history(app_instance_id)
        latest = history[-1] if history else None
        return ContextSummary(
            app_instance_id=app_instance_id,
            layer="working_set",
            current_goal=context.current_goal,
            current_stage=context.current_stage,
            decisions=[item.key for item in context.entries if item.section == "decisions"][-2:],
            constraints=[item.key for item in context.entries if item.section == "constraints"][-2:],
            open_loops=[item.key for item in context.entries if item.section == "open_loops"][-3:],
            artifacts=[item.key for item in context.entries if item.section == "artifacts"][-3:],
            detail_refs=[] if latest is None else [f"workflow:{latest.workflow_id}:{latest.trigger}"],
            metadata={"latest_workflow_status": None if latest is None else latest.status},
        )

    def list_layers(self, app_instance_id: str) -> dict:
        summary = self._summaries.get(app_instance_id)
        history = self._workflow_executor.list_history(app_instance_id)
        context = self._app_context_store.get_context(app_instance_id)
        return {
            "app_instance_id": app_instance_id,
            "layers": {
                "working_set": self.build_working_set(app_instance_id).model_dump(mode="json"),
                "summary": None if summary is None else summary.model_dump(mode="json"),
                "detail": {
                    "context_entry_count": len(context.entries),
                    "workflow_history_count": len(history),
                },
            },
        }

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("context_summaries", self._summaries)
        self._store.save_mapping("context_policies", self._policies)
