"""技能执行域路由：确定性 HTTP 入口，触发 core skill 真实执行。

打通用户直接触发已 promote 到 core 的 skill（如 release-and-launch）的固化线路——
此前缺少公开执行入口，用户说「发布并启动」时没有通道能真正执行它。

依赖通过 deps 持有器获取 runtime_services 中的 skill_runtime。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.models.skill_runtime import SkillExecutionRequest
from app.system.http_routers.deps import get_current_user, get_runtime_services


def _skill_runtime():
    svc = get_runtime_services().get("skill_runtime")
    if svc is None:
        raise HTTPException(status_code=503, detail="技能运行时未就绪")
    return svc


class SkillExecuteReq(BaseModel):
    skill_id: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    # 安全闸：危险技能（改版本/打 tag/起服务）必须显式确认
    confirm: bool = False
    # 标识位：dry_run 透传给 handler 的 config
    dry_run: bool = False
    user_id: str = ""


# 需要显式 confirm 的敏感技能（真实副作用）
_DANGEROUS_SKILLS = {"release-and-launch"}


def create_skill_execute_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/skill",
        tags=["skill-execute"],
        dependencies=[Depends(get_current_user)],
    )

    @router.post("/execute")
    def execute(payload: SkillExecuteReq):
        if payload.skill_id in _DANGEROUS_SKILLS and not payload.confirm:
            raise HTTPException(
                status_code=400,
                detail=f"技能 {payload.skill_id} 有真实副作用（改版本/打 tag/起服务），需显式传 confirm=true",
            )
        cfg = {**payload.config}
        if payload.dry_run:
            cfg["dry_run"] = True
        req = SkillExecutionRequest(
            skill_id=payload.skill_id,
            app_instance_id="api:skill:execute",
            workflow_id="api:skill:execute",
            step_id="skill-execute",
            inputs=payload.inputs,
            config=cfg,
            user_id=payload.user_id,
        )
        result = _skill_runtime().execute(req)
        if result.status == "failed":
            raise HTTPException(status_code=500, detail={
                "error": result.error,
                "error_detail": result.error_detail,
            })
        return result

    @router.get("/list")
    def list_skills():
        """列出当前已注册进 skill_runtime 的技能（调试用）。"""
        svc = _skill_runtime()
        return {"skill_ids": sorted(getattr(svc, "_entries", {}).keys())}

    return router
