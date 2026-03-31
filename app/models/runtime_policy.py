from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AppExecutionMode = Literal["service", "pipeline"]
ActivationMode = Literal["on_demand", "always_on", "scheduled"]
RestartPolicy = Literal["never", "on_failure", "always"]
PersistenceLevel = Literal["minimal", "standard", "full"]
IdleStrategy = Literal["keep_alive", "suspend", "stop"]


class RuntimePolicy(BaseModel):
    execution_mode: AppExecutionMode = "service"
    activation: ActivationMode = "on_demand"
    restart_policy: RestartPolicy = "on_failure"
    persistence_level: PersistenceLevel = "standard"
    idle_strategy: IdleStrategy = "suspend"
    max_restart_attempts: int = Field(default=3, ge=0)
    allow_prompt_invoke: bool = True
    prompt_invoke_requires_ask_user: bool = False
