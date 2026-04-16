from __future__ import annotations

from app.models.app_blueprint import AppBlueprint


class PolicyGuardError(ValueError):
    pass


class PolicyGuardService:
    def ensure_workflow_step_allowed(self, blueprint: AppBlueprint, *, kind: str, ref: str) -> None:
        if kind == "skill":
            if ref not in blueprint.required_skills:
                raise PolicyGuardError(f"skill not declared in blueprint: {ref}")
            return
        if kind == "module":
            if ref not in blueprint.required_modules:
                raise PolicyGuardError(f"module not declared in blueprint: {ref}")
            if ref == "prompt.invoke" and not blueprint.runtime_policy.allow_prompt_invoke:
                raise PolicyGuardError("prompt invocation disabled by runtime policy")
            return
        if kind == "event":
            if "event.publish" not in blueprint.required_modules:
                return
            allowed = set(blueprint.required_modules) | set(blueprint.required_skills)
            if ref not in allowed:
                raise PolicyGuardError(f"event not permitted by blueprint policy: {ref}")
            return
