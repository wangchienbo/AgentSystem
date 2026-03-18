from __future__ import annotations

from app.models.workflow_execution import WorkflowExecutionResult
from app.models.workflow_subscription import WorkflowEventSubscription
from app.services.runtime_state_store import RuntimeStateStore
from app.services.workflow_executor import WorkflowExecutorService


class WorkflowSubscriptionError(ValueError):
    pass


class WorkflowSubscriptionService:
    def __init__(
        self,
        workflow_executor: WorkflowExecutorService,
        store: RuntimeStateStore | None = None,
    ) -> None:
        self._workflow_executor = workflow_executor
        self._subscriptions: dict[str, WorkflowEventSubscription] = {}
        self._store = store

    def subscribe(self, subscription: WorkflowEventSubscription) -> WorkflowEventSubscription:
        self._subscriptions[subscription.subscription_id] = subscription
        self._persist()
        return subscription

    def list_subscriptions(self, event_name: str | None = None) -> list[WorkflowEventSubscription]:
        subscriptions = list(self._subscriptions.values())
        if event_name is None:
            return subscriptions
        return [item for item in subscriptions if item.event_name == event_name]

    def trigger(self, event_name: str, payload: dict | None = None) -> list[WorkflowExecutionResult]:
        executions: list[WorkflowExecutionResult] = []
        for subscription in self.list_subscriptions(event_name):
            if not subscription.active:
                continue
            executions.append(
                self._workflow_executor.execute_workflow(
                    app_instance_id=subscription.app_instance_id,
                    workflow_id=subscription.workflow_id,
                    trigger=f"event:{event_name}",
                    inputs=payload or {},
                )
            )
        return executions

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("workflow_subscriptions", self._subscriptions)
