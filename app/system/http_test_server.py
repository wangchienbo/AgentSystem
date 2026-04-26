"""AgentSystem HTTP Test Server with Authentication.

Provides:
- Login page with authentication
- Mobile-first chat UI
- Web chat endpoint using AgentSystem LightBrain gateway (with Tool/LLM support)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
import json

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Build AgentSystem runtime once — ModelRouter 从 ~/.config/agentsystem/config.yaml 读取 LLM 配置
# HTTP server 只做薄薄一层 HTTP 适配，不应直接读取 model 配置
runtime_services = build_runtime()
gateway = runtime_services["light_brain_gateway"]

app = FastAPI(
    title="AgentSystem Test Server",
    description="HTTP interface for testing AgentSystem intent understanding",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

user_sessions: dict[str, dict[str, Any]] = {}  # session_id -> user_data
conversation_history: dict[str, list[dict[str, str]]] = {}  # session_id -> messages
CHAT_LOG_DIR = BASE_DIR / "data" / "chat_logs"
CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _append_chat_log(session_id: str, event: dict[str, Any]) -> None:
    log_path = CHAT_LOG_DIR / f"{session_id}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _build_memory_context(session_id: str, limit: int = 12) -> str:
    history = conversation_history.get(session_id, [])[-limit:]
    return "\n".join(
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in history
    )


def _extract_session_facts(session_id: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    history = conversation_history.get(session_id, [])
    for item in history:
        if item.get("role") != "user":
            continue
        content = item.get("content", "")
        if "闺女" in content or "女儿" in content:
            facts["child_gender"] = "女"
        if "姓王" in content:
            facts["child_surname"] = "王"
        if "辰时" in content:
            facts["birth_time"] = "辰时"
        if "2026年7月16" in content:
            facts["birth_date"] = "2026年7月16日"
        if "起名字" in content or "起名" in content:
            facts["task"] = "给孩子起名"
    return facts


def _build_session_fact_board(session_id: str) -> str:
    facts = _extract_session_facts(session_id)
    if not facts:
        return ""
    labels = {
        "task": "当前任务",
        "child_gender": "孩子性别",
        "child_surname": "孩子姓氏",
        "birth_date": "出生日期",
        "birth_time": "出生时辰",
    }
    lines = ["[当前会话已知事实]"]
    for key in ["task", "child_gender", "child_surname", "birth_date", "birth_time"]:
        if key in facts:
            lines.append(f"- {labels[key]}: {facts[key]}")
    lines.append("- 对已明确给出的事实，不要重复追问。")
    return "\n".join(lines)


def _build_effective_memory_context(session_id: str) -> str:
    parts = []
    fact_board = _build_session_fact_board(session_id)
    history = _build_memory_context(session_id)
    if fact_board:
        parts.append(fact_board)
    if history:
        parts.append("[最近对话历史]\n" + history)
    return "\n\n".join(parts)


def _augment_user_message(raw_message: str, session_id: str) -> str:
    history = conversation_history.get(session_id, [])
    style_anchor = "回答时必须先给结论，再给细节。"
    action_first_triggers = ["查看上下文", "看下上下文", "查代码", "源码仓库", "仓库位置", "调用工具查找"]
    if not history:
        return raw_message
    prefix_lines = ["[对话约束]", f"- {style_anchor}"]
    if any(trigger in raw_message for trigger in action_first_triggers):
        prefix_lines.append("- 当前请求属于系统自省/检索类请求，必须优先尝试真实工具动作或真实检索，再根据结果回复；不要直接只做泛化能力解释。")
        prefix_lines.append("- 若无法完成，也要明确说明已尝试了什么、为什么失败、还缺什么权限或信息。")
    return "\n".join(prefix_lines) + f"\n\n[用户当前消息]\n{raw_message}"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    payload: dict[str, Any] | None = None


async def get_current_user(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_sessions[session_id]


@app.get("/", response_class=FileResponse)
async def root():
    # Ensure the index.html exists; if not, fall back to a minimal placeholder
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        # Create a simple placeholder page on‑the‑fly
        placeholder = """<html><head><title>AgentSystem</title></head><body><h1>AgentSystem 已启动</h1><p>请检查 static/index.html 是否存在。</p></body></html>"""
        return HTMLResponse(content=placeholder, status_code=200)
    return FileResponse(index_path)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Login - AgentSystem"},
    )


@app.post("/login")
async def login(request: Request):
    form_data = await request.form()
    username = form_data.get("username", "testuser")
    # 按用户名生成稳定的 session_id（同一用户每次登录都恢复同一会话）
    session_id = f"session_{username}"
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
    from fastapi.responses import JSONResponse
    hist = conversation_history.get(session_id, [])
    resp = JSONResponse(content={
        "success": True,
        "session_id": session_id,
        "history": hist,
        "username": username,
    })
    resp.set_cookie(key="session_id", value=session_id, max_age=86400, httponly=False)
    return resp


@app.get("/chat")
async def chat_page(user: dict = Depends(get_current_user)):
    return RedirectResponse(url="/")


@app.get("/api/history/{session_id}")
async def api_get_history(session_id: str, user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "history": conversation_history.get(session_id, []),
    }


@app.post("/api/chat")
async def api_chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    session_id = req.session_id or user["session_id"]
    started_at = datetime.now()
    user_sessions.setdefault(session_id, {
        "username": user.get("username", "anonymous"),
        "session_id": session_id,
        "login_time": started_at.isoformat(),
        "last_active": started_at.isoformat(),
    })
    conversation_history.setdefault(session_id, [])
    user_sessions[session_id]["last_active"] = started_at.isoformat()

    try:
        # Build ChatMessageRequest for LightBrain gateway
        chat_req = ChatMessageRequest(
            user_id=user.get("username", "anonymous"),
            channel="webchat",
            message=_augment_user_message(req.message, session_id),
            session_id=session_id,
            memory_context=_build_effective_memory_context(session_id),
        )
        # Call AgentSystem LightBrain gateway (which handles LLM routing and Tool calls)
        llm_resp = await gateway.receive_message(chat_req)
        response_text = getattr(llm_resp, "content", "") or ""
        finished_at = datetime.now()
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)

        # Store in conversation history
        conversation_history.setdefault(session_id, []).append({
            "role": "user",
            "content": req.message,
            "timestamp": started_at.isoformat(),
        })
        conversation_history.setdefault(session_id, []).append({
            "role": "assistant",
            "content": response_text,
            "timestamp": finished_at.isoformat(),
        })
        _append_chat_log(session_id, {
            "timestamp": finished_at.isoformat(),
            "session_id": session_id,
            "username": user.get("username", "anonymous"),
            "request": req.message,
            "response": response_text,
            "success": True,
            "error_type": None,
            "latency_ms": latency_ms,
        })
        return {"success": True, "response": response_text, "session_id": session_id, "latency_ms": latency_ms}
    except Exception as e:
        finished_at = datetime.now()
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)
        error_text = str(e)
        error_type = type(e).__name__
        logger.exception("Error processing message")
        conversation_history.setdefault(session_id, []).append({
            "role": "user",
            "content": req.message,
            "timestamp": started_at.isoformat(),
        })
        _append_chat_log(session_id, {
            "timestamp": finished_at.isoformat(),
            "session_id": session_id,
            "username": user.get("username", "anonymous"),
            "request": req.message,
            "response": None,
            "success": False,
            "error": error_text,
            "error_type": error_type,
            "latency_ms": latency_ms,
        })
        return {"success": False, "error": f"LLM request failed: {error_text}", "error_type": error_type, "session_id": session_id, "latency_ms": latency_ms}


# ---------- 新增 Action 接口（前端按钮 / Tool 调用） ----------
from pydantic import Field

class ActionRequest(BaseModel):
    action_id: str = Field(..., description="前端发送的按钮/工具标识")
    action_params: dict[str, Any] = Field(default_factory=dict, description="可选参数")

@app.post("/api/action")
async def api_action(req: ActionRequest, user: dict = Depends(get_current_user)):
    """把前端的 Action 转发给 LightBrain gateway，触发对应 Tool/Skill。"""
    session_id = user["session_id"]
    try:
        # 构造 LightBrain 的请求，payload 中放置 action 信息
        # 使用占位信息满足 ChatMessageRequest 的必填字段
        chat_req = ChatMessageRequest(
            user_id=user.get("username", "anonymous"),
            channel="webchat",
            message=f"[action:{req.action_id}]",  # 简短占位，实际行为在 payload 中
            session_id=session_id,
            memory_context=_build_effective_memory_context(session_id),
        )
        # 注入 payload 让 LightBrain 能识别要调用的工具
        chat_req = chat_req.copy(update={"payload": {"action_id": req.action_id, "params": req.action_params}})
        llm_resp = await gateway.receive_message(chat_req)
        response_text = getattr(llm_resp, "content", "") or ""
        # 记录到对话历史（assistant）
        conversation_history.setdefault(session_id, []).append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
        })
        return {"success": True, "response": response_text}
    except Exception as e:
        logger.exception("LLM action failed")
        return {"success": False, "error": f"LLM action failed: {str(e)}"}


# ---------- 旧的状态与登出接口继续保留 ----------
@app.get("/api/status")
async def api_status():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(user_sessions),
    }


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_id")
    return response


# ---------- 会话管理接口 ----------
@app.get("/api/sessions")
async def api_list_sessions(user: dict = Depends(get_current_user)):
    """列出当前用户的所有会话"""
    username = user["username"]
    # 当前只有按用户名的单一稳定会话
    return {
        "success": True,
        "sessions": [
            {
                "session_id": user["session_id"],
                "username": username,
                "login_time": user.get("login_time", ""),
                "message_count": len(conversation_history.get(user["session_id"], [])),
                "is_current": True,
            }
        ],
    }


@app.get("/api/sessions/{session_id}/history")
async def api_session_history(session_id: str, user: dict = Depends(get_current_user)):
    """获取指定会话的历史记录"""
    # 安全检查：只能查看自己的会话
    if session_id != user["session_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    history = conversation_history.get(session_id, [])
    return {"success": True, "history": history}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "80"))
    uvicorn.run(app, host="0.0.0.0", port=port)
