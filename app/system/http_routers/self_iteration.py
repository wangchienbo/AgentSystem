"""自治进化域路由：确定性 HTTP 入口。

打通用户直接触发诊断/提议/造技能/审查/裁决/进化历史的固化线路——
此前这些流程只能通过 LLM 对话（call_asset_method）碰巧触发，不可靠、不可发现。
现在提供 /api/self-iteration/* 端点 + Web 面板，让用户能"自由地"让系统自我扩展与约束。

依赖通过 deps 持有器获取 runtime_services 中的 self_iteration_asset_service。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.system.http_routers.deps import get_current_user, get_runtime_services, get_self_review_tick


def _service():
    svc = get_runtime_services().get("self_iteration_asset_service")
    if svc is None:
        raise HTTPException(status_code=503, detail="自治进化服务未就绪")
    return svc


class DiagnoseReq(BaseModel):
    include_god_objects: bool = True


class ReviewReq(BaseModel):
    force: bool = False


class BootstrapReq(BaseModel):
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    template_type: str = "text_transform"
    status: str = "candidate"
    source_workflow: str | None = None


class PromoteReq(BaseModel):
    skill_id: str = Field(min_length=1)
    accepted_by: str = ""


class TodoDecisionReq(BaseModel):
    file: str = Field(min_length=1)
    target: str = Field(min_length=1)
    status: str = "declined"
    rationale: str = ""


def create_self_iteration_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/self-iteration",
        tags=["self-iteration"],
        dependencies=[Depends(get_current_user)],
    )

    @router.get("/overview")
    def overview():
        """全系统自进化视图 + 推荐下一个待办目标。"""
        return _service().get_self_iteration_strategy_overview()

    @router.get("/assets")
    def assets():
        """列出自治进化资产摘要。"""
        return _service().list_self_iteration_assets()

    @router.get("/history")
    def history(limit: int = 20):
        """跨会话进化历史（周期审查快照）。"""
        return _service().get_evolution_history(limit=limit)

    @router.post("/diagnose")
    def diagnose(payload: DiagnoseReq):
        """运行只读代码健康诊断（导入缺陷 + God Object）。"""
        return _service().diagnose_codebase(include_god_objects=payload.include_god_objects)

    @router.post("/propose")
    def propose(payload: DiagnoseReq):
        """基于诊断生成代码重构方案（供人类审批，不自动应用）。"""
        return _service().propose_code_improvements(include_god_objects=payload.include_god_objects)

    @router.post("/review")
    def review(payload: ReviewReq):
        """触发周期代码审查（force=true 强制重跑，否则走 24h 间隔判断）。"""
        return _service().run_periodic_review(force=payload.force)

    @router.post("/bootstrap")
    def bootstrap(payload: BootstrapReq):
        """能力自举：生成新 skill 资产脚手架（默认 candidate，供审批后 promote）。"""
        return _service().bootstrap_skill_asset(
            skill_id=payload.skill_id,
            name=payload.name,
            description=payload.description,
            template_type=payload.template_type,
            status=payload.status,
            source_workflow=payload.source_workflow,
        )

    @router.get("/bootstrapped")
    def bootstrapped(status: str | None = None):
        """列出已自举的 skill 资产。"""
        return _service().list_bootstrapped_skills(status=status)

    @router.post("/promote")
    def promote(payload: PromoteReq):
        """人类审批：把 candidate skill 提升为 core。"""
        return _service().promote_skill_asset(payload.skill_id, accepted_by=payload.accepted_by)

    @router.post("/verify")
    def verify():
        """校验已自举 skill 资产的完整性。"""
        return _service().verify_bootstrapped_skills()

    @router.get("/todo-decisions")
    def todo_decisions():
        """列出全部已裁决重构目标（done/declined）。"""
        return _service().list_todo_decisions()

    @router.post("/todo-decision")
    def record_todo(payload: TodoDecisionReq):
        """记录对某重构目标的裁决，实现自动待办跨会话收敛。"""
        return _service().record_todo_decision(
            payload.file, payload.target, status=payload.status, rationale=payload.rationale,
        )

    @router.get("/tick-status")
    def tick_status():
        """周期审查驱动状态（固化线路是否在跑）。"""
        driver = get_self_review_tick()
        if driver is None:
            return {"running": False, "message": "周期审查驱动未实例化"}
        return driver.status()

    return router
