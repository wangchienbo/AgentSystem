"""Blueprint Comparison Service — structured diff between two AppBlueprints.

Compares roles, tasks, workflows, dependencies (modules/skills),
storage plans, runtime policies, and produces a risk assessment
for breaking changes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.app_blueprint import AppBlueprint


class BlueprintDiffItem(BaseModel):
    """A single diff entry."""
    path: str
    kind: str  # "added" | "removed" | "modified"
    old: Any = None
    new: Any = None


class BlueprintCompareResult(BaseModel):
    """Structured comparison report between two blueprints."""
    from_id: str
    to_id: str
    from_version: str
    to_version: str
    roles_added: list[dict[str, Any]] = Field(default_factory=list)
    roles_removed: list[dict[str, Any]] = Field(default_factory=list)
    roles_modified: list[dict[str, Any]] = Field(default_factory=list)
    tasks_added: list[dict[str, Any]] = Field(default_factory=list)
    tasks_removed: list[dict[str, Any]] = Field(default_factory=list)
    tasks_modified: list[dict[str, Any]] = Field(default_factory=list)
    workflows_added: list[dict[str, Any]] = Field(default_factory=list)
    workflows_removed: list[dict[str, Any]] = Field(default_factory=list)
    workflows_modified: list[dict[str, Any]] = Field(default_factory=list)
    modules_added: list[str] = Field(default_factory=list)
    modules_removed: list[str] = Field(default_factory=list)
    skills_added: list[str] = Field(default_factory=list)
    skills_removed: list[str] = Field(default_factory=list)
    storage_plan_changed: bool = False
    storage_plan_diff: dict[str, BlueprintDiffItem] = Field(default_factory=dict)
    runtime_policy_changed: bool = False
    runtime_policy_diff: dict[str, BlueprintDiffItem] = Field(default_factory=dict)
    runtime_profile_changed: bool = False
    runtime_profile_diff: dict[str, BlueprintDiffItem] = Field(default_factory=dict)
    app_shape_changed: bool = False
    app_shape_from: str = "generic"
    app_shape_to: str = "generic"
    breaking_changes: list[str] = Field(default_factory=list)
    risk_level: str = "low"  # "low" | "medium" | "high" | "critical"
    total_changes: int = 0
    diff_items: list[BlueprintDiffItem] = Field(default_factory=list)
    summary: str = ""


class BlueprintCompareError(ValueError):
    pass


class BlueprintCompareService:
    """Compares two AppBlueprint objects and produces a structured diff."""

    # Paths whose changes are considered breaking
    _BREAKING_PATHS = {
        "roles.removed",
        "tasks.removed",
        "workflows.removed",
        "modules.removed",
        "skills.removed",
        "runtime_policy.execution_mode",
        "runtime_policy.activation",
        "app_shape",
    }

    def compare(self, old_bp: AppBlueprint, new_bp: AppBlueprint) -> BlueprintCompareResult:
        """Compare two blueprints and return a structured diff report."""
        if old_bp.id != new_bp.id:
            raise BlueprintCompareError(
                f"Cannot compare blueprints with different IDs: {old_bp.id} vs {new_bp.id}"
            )

        result = BlueprintCompareResult(
            from_id=old_bp.id,
            to_id=new_bp.id,
            from_version=old_bp.version,
            to_version=new_bp.version,
        )

        self._compare_roles(old_bp, new_bp, result)
        self._compare_tasks(old_bp, new_bp, result)
        self._compare_workflows(old_bp, new_bp, result)
        self._compare_dependencies(old_bp, new_bp, result)
        self._compare_storage_plan(old_bp, new_bp, result)
        self._compare_runtime_policy(old_bp, new_bp, result)
        self._compare_runtime_profile(old_bp, new_bp, result)
        self._compare_app_shape(old_bp, new_bp, result)

        self._assess_risk(result)
        result.total_changes = len(result.diff_items)
        result.summary = self._build_summary(result)
        return result

    # ------------------------------------------------------------------
    # Individual comparators
    # ------------------------------------------------------------------

    def _compare_roles(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_roles = {r.id: r for r in old_bp.roles}
        new_roles = {r.id: r for r in new_bp.roles}

        old_ids = set(old_roles.keys())
        new_ids = set(new_roles.keys())

        for rid in sorted(new_ids - old_ids):
            r = new_roles[rid]
            result.roles_added.append(r.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"roles.{rid}", kind="added", new=r.model_dump(mode="json")))

        for rid in sorted(old_ids - new_ids):
            r = old_roles[rid]
            result.roles_removed.append(r.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"roles.removed.{rid}", kind="removed", old=r.model_dump(mode="json")))

        for rid in sorted(old_ids & new_ids):
            old_r = old_roles[rid]
            new_r = new_roles[rid]
            if old_r != new_r:
                changes: dict[str, Any] = {}
                old_d = old_r.model_dump(mode="json")
                new_d = new_r.model_dump(mode="json")
                for key in old_d:
                    if old_d.get(key) != new_d.get(key):
                        changes[key] = {"from": old_d.get(key), "to": new_d.get(key)}
                result.roles_modified.append({"id": rid, "changes": changes})
                result.diff_items.append(
                    BlueprintDiffItem(path=f"roles.{rid}", kind="modified", old=old_d, new=new_d)
                )

    def _compare_tasks(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_tasks = {t.id: t for t in old_bp.tasks}
        new_tasks = {t.id: t for t in new_bp.tasks}

        old_ids = set(old_tasks.keys())
        new_ids = set(new_tasks.keys())

        for tid in sorted(new_ids - old_ids):
            t = new_tasks[tid]
            result.tasks_added.append(t.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"tasks.{tid}", kind="added", new=t.model_dump(mode="json")))

        for tid in sorted(old_ids - new_ids):
            t = old_tasks[tid]
            result.tasks_removed.append(t.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"tasks.removed.{tid}", kind="removed", old=t.model_dump(mode="json")))

        for tid in sorted(old_ids & new_ids):
            old_t = old_tasks[tid]
            new_t = new_tasks[tid]
            if old_t != new_t:
                changes: dict[str, Any] = {}
                old_d = old_t.model_dump(mode="json")
                new_d = new_t.model_dump(mode="json")
                for key in old_d:
                    if old_d.get(key) != new_d.get(key):
                        changes[key] = {"from": old_d.get(key), "to": new_d.get(key)}
                result.tasks_modified.append({"id": tid, "changes": changes})
                result.diff_items.append(
                    BlueprintDiffItem(path=f"tasks.{tid}", kind="modified", old=old_d, new=new_d)
                )

    def _compare_workflows(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_wfs = {w.id: w for w in old_bp.workflows}
        new_wfs = {w.id: w for w in new_bp.workflows}

        old_ids = set(old_wfs.keys())
        new_ids = set(new_wfs.keys())

        for wid in sorted(new_ids - old_ids):
            w = new_wfs[wid]
            result.workflows_added.append(w.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"workflows.{wid}", kind="added", new=w.model_dump(mode="json")))

        for wid in sorted(old_ids - new_ids):
            w = old_wfs[wid]
            result.workflows_removed.append(w.model_dump(mode="json"))
            result.diff_items.append(BlueprintDiffItem(path=f"workflows.removed.{wid}", kind="removed", old=w.model_dump(mode="json")))

        for wid in sorted(old_ids & new_ids):
            old_w = old_wfs[wid]
            new_w = new_wfs[wid]
            if old_w != new_w:
                changes: dict[str, Any] = {}
                old_d = old_w.model_dump(mode="json")
                new_d = new_w.model_dump(mode="json")
                for key in old_d:
                    if old_d.get(key) != new_d.get(key):
                        changes[key] = {"from": old_d.get(key), "to": new_d.get(key)}
                result.workflows_modified.append({"id": wid, "changes": changes})
                result.diff_items.append(
                    BlueprintDiffItem(path=f"workflows.{wid}", kind="modified", old=old_d, new=new_d)
                )

    def _compare_dependencies(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_modules = set(old_bp.required_modules)
        new_modules = set(new_bp.required_modules)

        result.modules_added = sorted(new_modules - old_modules)
        result.modules_removed = sorted(old_modules - new_modules)

        for mod in result.modules_added:
            result.diff_items.append(BlueprintDiffItem(path=f"modules.{mod}", kind="added", new=mod))
        for mod in result.modules_removed:
            result.diff_items.append(BlueprintDiffItem(path=f"modules.removed.{mod}", kind="removed", old=mod))

        old_skills = set(old_bp.required_skills)
        new_skills = set(new_bp.required_skills)

        result.skills_added = sorted(new_skills - old_skills)
        result.skills_removed = sorted(old_skills - new_skills)

        for skill in result.skills_added:
            result.diff_items.append(BlueprintDiffItem(path=f"skills.{skill}", kind="added", new=skill))
        for skill in result.skills_removed:
            result.diff_items.append(BlueprintDiffItem(path=f"skills.removed.{skill}", kind="removed", old=skill))

    def _compare_storage_plan(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_sp = old_bp.storage_plan.model_dump(mode="json")
        new_sp = new_bp.storage_plan.model_dump(mode="json")
        if old_sp != new_sp:
            result.storage_plan_changed = True
            for key in sorted(set(old_sp) | set(new_sp)):
                if old_sp.get(key) != new_sp.get(key):
                    item = BlueprintDiffItem(
                        path=f"storage_plan.{key}",
                        kind="modified",
                        old=old_sp.get(key),
                        new=new_sp.get(key),
                    )
                    result.storage_plan_diff[key] = item
                    result.diff_items.append(item)

    def _compare_runtime_policy(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_rp = old_bp.runtime_policy.model_dump(mode="json")
        new_rp = new_bp.runtime_policy.model_dump(mode="json")
        if old_rp != new_rp:
            result.runtime_policy_changed = True
            for key in sorted(set(old_rp) | set(new_rp)):
                if old_rp.get(key) != new_rp.get(key):
                    item = BlueprintDiffItem(
                        path=f"runtime_policy.{key}",
                        kind="modified",
                        old=old_rp.get(key),
                        new=new_rp.get(key),
                    )
                    result.runtime_policy_diff[key] = item
                    result.diff_items.append(item)

    def _compare_runtime_profile(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        old_prof = old_bp.runtime_profile.model_dump(mode="json")
        new_prof = new_bp.runtime_profile.model_dump(mode="json")
        if old_prof != new_prof:
            result.runtime_profile_changed = True
            for key in sorted(set(old_prof) | set(new_prof)):
                if old_prof.get(key) != new_prof.get(key):
                    item = BlueprintDiffItem(
                        path=f"runtime_profile.{key}",
                        kind="modified",
                        old=old_prof.get(key),
                        new=new_prof.get(key),
                    )
                    result.runtime_profile_diff[key] = item
                    result.diff_items.append(item)

    def _compare_app_shape(self, old_bp: AppBlueprint, new_bp: AppBlueprint, result: BlueprintCompareResult) -> None:
        result.app_shape_from = old_bp.app_shape
        result.app_shape_to = new_bp.app_shape
        if old_bp.app_shape != new_bp.app_shape:
            result.app_shape_changed = True
            result.diff_items.append(
                BlueprintDiffItem(
                    path="app_shape",
                    kind="modified",
                    old=old_bp.app_shape,
                    new=new_bp.app_shape,
                )
            )

    # ------------------------------------------------------------------
    # Risk assessment
    # ------------------------------------------------------------------

    def _assess_risk(self, result: BlueprintCompareResult) -> None:
        breaking: list[str] = []

        for item in result.diff_items:
            # Check exact path and parent paths against breaking paths
            path = item.path
            parts = path.split(".")
            for depth in range(1, len(parts) + 1):
                check = ".".join(parts[:depth])
                if check in self._BREAKING_PATHS:
                    reason = f"Breaking change: {item.kind} at {path}"
                    if reason not in breaking:
                        breaking.append(reason)
                    break

        # Removed roles/workflows/skills are always breaking
        if result.roles_removed:
            _ensure_breaking(breaking, "Roles removed", "roles.removed")
        if result.workflows_removed:
            _ensure_breaking(breaking, "Workflows removed", "workflows.removed")
        if result.skills_removed:
            _ensure_breaking(breaking, "Required skills removed", "skills.removed")
        if result.modules_removed:
            _ensure_breaking(breaking, "Required modules removed", "modules.removed")

        result.breaking_changes = breaking

        # Determine risk level
        if not result.diff_items:
            result.risk_level = "low"
        elif not breaking:
            result.risk_level = "low"
        elif len(breaking) <= 2:
            result.risk_level = "medium"
        elif len(breaking) <= 5:
            result.risk_level = "high"
        else:
            result.risk_level = "critical"

    def _build_summary(self, result: BlueprintCompareResult) -> str:
        parts: list[str] = []
        if result.total_changes == 0:
            return "No changes detected"

        if result.roles_added:
            parts.append(f"{len(result.roles_added)} role(s) added")
        if result.roles_removed:
            parts.append(f"{len(result.roles_removed)} role(s) removed")
        if result.roles_modified:
            parts.append(f"{len(result.roles_modified)} role(s) modified")
        if result.tasks_added:
            parts.append(f"{len(result.tasks_added)} task(s) added")
        if result.tasks_removed:
            parts.append(f"{len(result.tasks_removed)} task(s) removed")
        if result.tasks_modified:
            parts.append(f"{len(result.tasks_modified)} task(s) modified")
        if result.workflows_added:
            parts.append(f"{len(result.workflows_added)} workflow(s) added")
        if result.workflows_removed:
            parts.append(f"{len(result.workflows_removed)} workflow(s) removed")
        if result.workflows_modified:
            parts.append(f"{len(result.workflows_modified)} workflow(s) modified")
        if result.modules_added:
            parts.append(f"{len(result.modules_added)} module(s) added")
        if result.modules_removed:
            parts.append(f"{len(result.modules_removed)} module(s) removed")
        if result.skills_added:
            parts.append(f"{len(result.skills_added)} skill(s) added")
        if result.skills_removed:
            parts.append(f"{len(result.skills_removed)} skill(s) removed")
        if result.storage_plan_changed:
            parts.append("storage plan changed")
        if result.runtime_policy_changed:
            parts.append("runtime policy changed")
        if result.runtime_profile_changed:
            parts.append("runtime profile changed")
        if result.app_shape_changed:
            parts.append(f"app shape changed ({result.app_shape_from} → {result.app_shape_to})")

        summary = f"{result.total_changes} change(s): " + ", ".join(parts)
        if result.breaking_changes:
            summary += f" | {len(result.breaking_changes)} breaking change(s)"
        summary += f" | risk: {result.risk_level}"
        return summary


def _ensure_breaking(breaking: list[str], description: str, path: str) -> None:
    marker = f"Breaking change: {path}"
    if not any(marker in b for b in breaking):
        breaking.append(f"Breaking change: {description} ({path})")
