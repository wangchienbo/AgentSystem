"""OS 工作台功能域路由（App 目录 / Skill 库 / 治理看板 / 运行时状态）。

从 http_test_server.py 拆出（原 230-507 行）。所有依赖通过闭包捕获 runtime_services。
"""
from typing import Any

from fastapi import APIRouter

from app.system.http_routers.deps import get_runtime_services


def create_os_router() -> APIRouter:
    router = APIRouter()
    runtime_services = get_runtime_services()

    def _os_find_instance(lifecycle, app_id: str) -> str | None:
        """根据 blueprint_id 匹配实际 app_instance_id。"""
        try:
            for inst in lifecycle.list_instances():
                if inst.id == app_id or inst.id.startswith(app_id + ":"):
                    return inst.id
        except Exception:
            pass
        return None

    def _os_audit(action: str, target_id: str, *, result: str = "success", details: dict | None = None, error: str = "") -> None:
        """OS 工作台操作审计：写入 audit_logger（治理数据源，供工作台治理看板消费）。"""
        logger = runtime_services.get("audit_logger")
        if not logger:
            return
        try:
            logger.log(
                action=action,
                user_id="os_workbench",
                target_id=target_id,
                details=details or {},
                result=result,
                error_message=error,
            )
        except Exception:
            pass

    def _os_app_transition(app_id: str, event: str, reason: str) -> dict:
        lifecycle = runtime_services.get("lifecycle")
        if not lifecycle:
            return {"status": "error", "message": "lifecycle 不可用"}
        inst_id = _os_find_instance(lifecycle, app_id)
        if not inst_id:
            _os_audit(event, app_id, result="failure", error="instance not found")
            return {"status": "error", "message": f"未找到 App 实例: {app_id}"}
        try:
            lifecycle.transition(inst_id, event, reason=reason)
            _os_audit(event, app_id, result="success", details={"app_instance_id": inst_id})
            return {"status": "success", "message": f"App {app_id} 已 {event}", "app_id": app_id, "app_instance_id": inst_id}
        except Exception as e:
            _os_audit(event, app_id, result="failure", error=str(e))
            return {"status": "error", "message": str(e), "app_id": app_id}

    @router.post("/api/os/apps/create")
    def os_create_app(payload: dict):
        """确定性自由设计 App：intent 分析 + 底层 skill 组合设计 + 装配安装，一步完成。

        替代"通用对话 LLM 自主漫游探索"式创建（慢且不确定）。
        由运行中的 server 执行，产物经其 store 持久化。
        """
        orch = runtime_services.get("app_design_orchestrator")
        if not orch:
            return {"status": "error", "error": "app_design_orchestrator 不可用"}
        body = payload or {}
        description = body.get("description") or body.get("goal") or ""
        if not description:
            return {"status": "error", "error": "缺少 description/goal"}
        from app.models.app_design import DesignConfirmation
        result = orch.design_app(description)
        if result.status == "needs_clarification":
            return {"status": "needs_clarification", "result": result.model_dump(mode="json")}
        if result.status == "needs_confirmation":
            result = orch.confirm_and_create(result.design, DesignConfirmation(approved=True))
        # confirm_and_create 成功返回 AppCreationResult(status="success")，blueprint_id 为最终 App id
        if result.status in ("ok", "success"):
            app_id = getattr(result, "blueprint_id", "") or ""
            _os_audit("create_app", app_id or description[:40], result="success")
        return {"status": "ok", "result": result.model_dump(mode="json")}

    @router.post("/api/os/apps/{app_id}/start")
    def os_app_start(app_id: str):
        return _os_app_transition(app_id, "start", "os_workbench.start")

    @router.post("/api/os/apps/{app_id}/stop")
    def os_app_stop(app_id: str):
        return _os_app_transition(app_id, "stop", "os_workbench.stop")

    @router.post("/api/os/apps/{app_id}/pause")
    def os_app_pause(app_id: str):
        return _os_app_transition(app_id, "pause", "os_workbench.pause")

    @router.post("/api/os/apps/{app_id}/resume")
    def os_app_resume(app_id: str):
        return _os_app_transition(app_id, "resume", "os_workbench.resume")

    @router.delete("/api/os/apps/{app_id}")
    def os_app_delete(app_id: str):
        lifecycle = runtime_services.get("lifecycle")
        if not lifecycle:
            return {"status": "error", "message": "lifecycle 不可用"}
        inst_id = _os_find_instance(lifecycle, app_id)
        if not inst_id:
            _os_audit("delete_app", app_id, result="failure", error="instance not found")
            return {"status": "error", "message": f"未找到 App 实例: {app_id}"}
        try:
            lifecycle.delete_app(inst_id)
            _os_audit("delete_app", app_id, result="success", details={"app_instance_id": inst_id})
            return {"status": "success", "message": f"App {app_id} 已删除", "app_id": app_id}
        except Exception as e:
            return {"status": "error", "message": str(e), "app_id": app_id}

    @router.get("/api/os/skills/{skill_id}")
    def os_skill_detail(skill_id: str):
        """Skill 详情：适配器、依赖、能力画像、标签（工作台可发现性）"""
        sc = runtime_services.get("skill_control")
        entry = None
        if sc:
            try:
                entry = sc.get_skill(skill_id)
            except Exception:
                entry = None
        if entry is None:
            # 回退：overview 的 skill 库含 SYSTEM_SKILL_SPECS 静态声明，
            # 但这些条目未 register 进 skill_control，须从同一来源构建详情，
            # 否则工作台列出的 skill 点详情必然失败（数据源不一致）。
            try:
                from app.skills.system_skill_registry import SYSTEM_SKILL_SPECS
                spec = SYSTEM_SKILL_SPECS.get(skill_id)
            except Exception:
                spec = None
            if spec is None:
                return {"status": "error", "error": f"Skill not found: {skill_id}"}
            manifest = spec.get("manifest")
            profile = spec.get("capability_profile")
            return {
                "status": "ok",
                "skill": {
                    "skill_id": skill_id,
                    "name": spec.get("name", skill_id),
                    "description": (getattr(manifest, "description", "") or "") if manifest else "",
                    "runtime_adapter": (getattr(manifest, "runtime_adapter", "") or "") if manifest else "callable",
                    "dependencies": [],
                    "tags": list(getattr(manifest, "tags", []) or []) if manifest else [],
                    "active_version": spec.get("version", "1.0.0"),
                    "origin": "system",
                    "status": "active",
                    "immutable_interface": bool(spec.get("immutable_interface", False)),
                    "capability_profile": profile.model_dump(mode="json") if profile else {},
                },
            }
        manifest = entry.manifest
        desc = (getattr(manifest, "description", "") or "") if manifest else ""
        tags = list(getattr(manifest, "tags", []) or []) if manifest else []
        profile = entry.capability_profile.model_dump(mode="json") if entry.capability_profile else {}
        return {
            "status": "ok",
            "skill": {
                "skill_id": entry.skill_id,
                "name": entry.name,
                "description": desc,
                "runtime_adapter": entry.runtime_adapter,
                "dependencies": entry.dependencies,
                "tags": tags,
                "active_version": entry.active_version,
                "origin": entry.origin,
                "status": entry.status,
                "immutable_interface": entry.immutable_interface,
                "capability_profile": profile,
            },
        }

    @router.get("/api/os/governance")
    def os_governance():
        """治理概览：审计事件、按动作分类统计（工作台治理看板）"""
        audit = runtime_services.get("audit_logger")
        out = {"status": "ok", "audit": {"count": 0, "recent": []}, "actions": {}}
        if not audit:
            return out
        try:
            entries = audit.get_entries(limit=60)
        except Exception as e:
            out["audit"]["error"] = str(e)
            return out
        out["audit"]["count"] = len(entries)
        action_counter: dict = {}
        for e in entries:
            action = getattr(e, "action", "unknown")
            action_counter[action] = action_counter.get(action, 0) + 1
        out["actions"] = action_counter
        out["audit"]["recent"] = [
            e.to_dict() if hasattr(e, "to_dict") else e
            for e in entries[:8]
        ]
        return out

    @router.get("/api/os/overview")
    def os_overview():
        """AI 操作系统统一工作台数据：App 目录 + Skill 库 + 运行时状态。"""
        apps = []
        registry = runtime_services.get("app_registry")
        lifecycle = runtime_services.get("lifecycle")
        instance_map: dict[str, Any] = {}
        if lifecycle:
            try:
                instance_map = {inst.id: inst for inst in lifecycle.list_instances()}
            except Exception:
                instance_map = {}
        if registry:
            for entry in registry.list_entries():
                inst_id = next(
                    (
                        iid for iid in instance_map
                        if iid == entry.blueprint_id or iid.startswith(entry.blueprint_id + ":")
                    ),
                    None,
                )
                inst = instance_map.get(inst_id) if inst_id else None
                apps.append({
                    "app_id": entry.blueprint_id,
                    "app_instance_id": inst_id or "",
                    "name": entry.name,
                    "version": entry.version,
                    "description": entry.description,
                    "status": (inst.status if inst else ("running" if entry.release_status == "active" else "stopped")),
                    "release_status": entry.release_status,
                    "app_shape": entry.app_shape,
                })

        skills = []
        seen_skills: set[str] = set()

        def _add_skill(sid: str, name: str, desc: str) -> None:
            if sid and sid not in seen_skills:
                seen_skills.add(sid)
                skills.append({"skill_id": sid, "name": name or sid, "description": desc or ""})

        sc = runtime_services.get("skill_control")
        if sc and hasattr(sc, "list_skills"):
            try:
                for s in sc.list_skills():
                    _add_skill(
                        getattr(s, "skill_id", None) or getattr(s, "id", None),
                        getattr(s, "name", ""),
                        getattr(s, "description", ""),
                    )
            except Exception:
                pass

        # 操作系统内置能力清单（Skill 库）：保证工作台总能展示可复用能力
        try:
            from app.skills.system_skill_registry import SYSTEM_SKILL_SPECS
            for sid, spec in SYSTEM_SKILL_SPECS.items():
                _add_skill(sid, spec.get("name", ""), spec.get("description", ""))
        except Exception:
            pass

        lifecycle = runtime_services.get("lifecycle")
        instances = []
        if lifecycle and hasattr(lifecycle, "list_instances"):
            try:
                for inst in lifecycle.list_instances():
                    instances.append({
                        "instance_id": getattr(inst, "id", None),
                        "blueprint_id": getattr(inst, "blueprint_id", None),
                        "status": getattr(inst, "status", "unknown"),
                    })
            except Exception:
                pass

        return {
            "success": True,
            "apps": apps,
            "skills": skills,
            "instances": instances,
            "app_count": len(apps),
            "skill_count": len(skills),
            "running_count": sum(1 for a in apps if a["status"] == "running"),
        }

    return router
