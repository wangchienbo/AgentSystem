"""认证与会话管理域路由（login / logout / sessions / status）。

从 http_test_server.py 拆出（原 login POST + logout + /api/sessions* + /api/status）。
依赖通过 deps 持有器获取（会话状态、lobster_sessions、get_current_user）。
"""
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.ai.model_client import describe_tool_route_budget
from app.system.http_routers.deps import (
    get_conversation_history,
    get_current_user,
    get_lobster_sessions,
    get_user_sessions,
)


def create_auth_router(build_marker: str) -> APIRouter:
    router = APIRouter()
    user_sessions = get_user_sessions()
    conversation_history = get_conversation_history()

    @router.post("/login")
    async def login(request: Request):
        username = "testuser"
        content_type = (request.headers.get("content-type") or "").lower()
        lobster_sessions = get_lobster_sessions()
        if "application/json" in content_type:
            payload = await request.json()
            if isinstance(payload, dict):
                username = payload.get("username", username)
        else:
            try:
                form_data = await request.form()
                username = form_data.get("username", username)
            except AssertionError:
                raw_body = (await request.body()).decode("utf-8", errors="ignore")
                parsed = parse_qs(raw_body, keep_blank_values=True)
                username = parsed.get("username", [username])[0]
        # 按用户名生成稳定的 session_id（同一用户每次登录都恢复同一会话）
        session_id = f"session_{username}"
        # 确保 LobsterSessionStore 有此会话
        ls = lobster_sessions._ensure_user(username)
        if session_id not in ls["sessions"]:
            ls["sessions"][session_id] = {
                "label": "默认对话",
                "created_at": datetime.now(UTC).isoformat(),
                "last_active": datetime.now(UTC).isoformat(),
            }
            ls["current"] = session_id
        if session_id in user_sessions:
            # 已存在 → 更新登录时间，不重建会话
            user_sessions[session_id]["login_time"] = datetime.now().isoformat()
            user_sessions[session_id]["last_active"] = datetime.now().isoformat()
        else:
            # 新建会话
            user_sessions[session_id] = {
                "username": username,
                "session_id": session_id,
                "login_time": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
            }
            conversation_history[session_id] = []
        hist = conversation_history.get(session_id, [])
        resp = JSONResponse(content={
            "success": True,
            "session_id": session_id,
            "history": hist,
            "username": username,
        })
        resp.set_cookie(key="session_id", value=session_id, max_age=86400, httponly=False)
        return resp

    @router.get("/logout")
    async def logout():
        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie("session_id")
        return response

    @router.get("/api/status")
    async def api_status():
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "active_sessions": len(user_sessions),
            "build_marker": build_marker,
            "tool_route_budget": describe_tool_route_budget(),
        }

    @router.get("/api/sessions")
    async def api_list_sessions(user: dict = Depends(get_current_user)):
        """列出当前用户的所有会话"""
        lobster_sessions = get_lobster_sessions()
        username = user["username"]
        # 确保有会话
        ls = lobster_sessions._ensure_user(username)
        if not ls["sessions"]:
            lobster_sessions.create_session(username, "默认对话")
        sessions = lobster_sessions.list_sessions(username)
        return {"success": True, "sessions": sessions}

    @router.post("/api/sessions")
    async def api_create_session(user: dict = Depends(get_current_user), request: Request = None):
        """创建新会话"""
        lobster_sessions = get_lobster_sessions()
        label = ""
        if request:
            try:
                body = await request.json()
                label = body.get("label", "") if isinstance(body, dict) else ""
            except Exception:
                pass
        sid = lobster_sessions.create_session(user["username"], label or None)
        return {"success": True, "session_id": sid}

    @router.post("/api/sessions/{session_id}/switch")
    async def api_switch_session(session_id: str, user: dict = Depends(get_current_user)):
        """切换到指定会话"""
        lobster_sessions = get_lobster_sessions()
        ok = lobster_sessions.switch_session(user["username"], session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True, "session_id": session_id}

    @router.delete("/api/sessions/{session_id}")
    async def api_delete_session(session_id: str, user: dict = Depends(get_current_user)):
        """删除指定会话"""
        lobster_sessions = get_lobster_sessions()
        ok = lobster_sessions.delete_session(user["username"], session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}

    @router.get("/api/sessions/{session_id}/history")
    async def api_session_history(session_id: str, user: dict = Depends(get_current_user), limit: int = 50, offset: int = 0):
        """获取指定会话的历史记录（分页）"""
        lobster_sessions = get_lobster_sessions()
        # 安全检查：验证会话属于当前用户
        username = user["username"]
        ls = lobster_sessions._ensure_user(username)
        if session_id not in ls["sessions"]:
            raise HTTPException(status_code=403, detail="Forbidden")
        history = conversation_history.get(session_id, [])
        total = len(history)
        # 倒序截取（最新的在后面）
        start = max(0, total - offset - limit)
        end = max(0, total - offset)
        page = history[start:end] if start < end else []
        return {"success": True, "history": page, "total": total, "offset": offset, "limit": limit}

    return router
