"""共享认证依赖 — 所有 API 路由统一使用 cookie 会话。

Usage::

    from app.system.auth import require_auth

    @router.get("/api/protected")
    async def handler(user: dict = Depends(require_auth)):
        return {"username": user["username"]}
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request


async def require_auth(request: Request) -> dict:
    """FastAPI 依赖：检查 session_id cookie，返回用户信息。

    与 http_test_server.py 的 get_current_user 使用相同的 user_sessions 字典。
    使用延迟导入避免循环依赖（http_test_server → bootstrap → api → auth → http_test_server）。

    未认证时抛出 401。
    """
    from app.system.http_test_server import user_sessions

    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    existing = user_sessions.get(session_id)
    if existing:
        return existing

    raise HTTPException(status_code=401, detail="会话不存在或已过期")
