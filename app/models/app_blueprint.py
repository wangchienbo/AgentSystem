from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.runtime_policy import RuntimePolicy


RoleType = Literal["human", "agent", "system", "external"]


class Role(BaseModel):
    id: str
    name: str
    type: RoleType
    responsibilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    visible_views: list[str] = Field(default_factory=list)
    accessible_data: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    owner_role: str
    trigger: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    success_condition: str = ""
    failure_policy: str = "retry_then_escalate"
    escalation_target: str | None = None


class WorkflowStep(BaseModel):
    id: str
    kind: Literal["module", "skill", "human_task", "event"]
    ref: str
    config: dict[str, Any] = Field(default_factory=dict)


class Workflow(BaseModel):
    id: str
    name: str
    triggers: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)


class View(BaseModel):
    id: str
    name: str
    type: Literal["page", "form", "list", "detail", "dashboard"]
    visible_roles: list[str] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)


class StoragePlan(BaseModel):
    user_data: str = "user"
    app_data: str = "app"
    runtime_state: str = "runtime"
    system_metadata: str = "system"


class AppBlueprint(BaseModel):
    id: str
    name: str
    goal: str
    version: str = "0.1.0"
    roles: list[Role] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)
    required_modules: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    storage_plan: StoragePlan = Field(default_factory=StoragePlan)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
