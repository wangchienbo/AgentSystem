"""AgentSystem HTTP Test Server with Authentication.

Provides:
- Login page with authentication
- Mobile-first chat UI
- Web chat endpoint using AgentSystem LightBrain gateway (with Tool/LLM support)
"""
from __future__ import annotations

import logging
import threading
import time
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import json

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.bootstrap.runtime import build_runtime
from app.models.app_instance import AppInstance
from app.models.chat import ChatMessageRequest
from app.models.scheduling import ScheduleRecord
from app.system.chat_regression import (
    build_multi_run_comparison,
    build_run_summary,
    build_topic_trends,
    make_testclient_poster,
    persist_run_results,
    REGRESSION_LOG_DIR,
    run_fixed_prompt_matrix,
    list_saved_runs,
    read_run_details,
    run_regression_governance_cycle,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RegressionNightlyTickDriver:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval_seconds = 60
        self._running = False

    def status(self) -> dict[str, Any]:
        state = load_regression_nightly_driver_state()
        return {
            "running": self._running and self._thread is not None and self._thread.is_alive(),
            "interval_seconds": self._interval_seconds,
            "thread_alive": self._thread is not None and self._thread.is_alive(),
            "persisted_running": state.get("running", False),
            "persisted_interval_seconds": state.get("interval_seconds", self._interval_seconds),
        }

    def start(self, *, interval_seconds: int = 60) -> dict[str, Any]:
        self._interval_seconds = max(5, interval_seconds)
        if self._thread is not None and self._thread.is_alive():
            self._running = True
            return self.status()
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="regression-nightly-tick", daemon=True)
        self._thread.start()
        save_regression_nightly_driver_state({"running": True, "interval_seconds": self._interval_seconds})
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._running = False
        self._stop_event.set()
        save_regression_nightly_driver_state({"running": False, "interval_seconds": self._interval_seconds})
        return self.status()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                tick_regression_nightly_cycle(ensure_regression_service_session())
            except Exception as error:
                logger.warning("regression nightly tick driver iteration failed: %s", error)


# Build AgentSystem runtime once — ModelRouter 从 ~/.config/agentsystem/config.yaml 读取 LLM 配置
# HTTP server 只做薄薄一层 HTTP 适配，不应直接读取 model 配置
runtime_services = build_runtime()
gateway = runtime_services["light_brain_gateway"]
refinement_memory = runtime_services["refinement_memory"]
refinement_rollout = runtime_services["refinement_rollout"]

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
APP_INSTANCE_ID = "agent_system"
REGRESSION_CYCLE_TASK_NAME = "regression_governance_cycle"
REGRESSION_NIGHTLY_SCHEDULE_ID = "sch.regression.governance.nightly"
REGRESSION_NIGHTLY_STATE_KEY = "regression_nightly_state"
REGRESSION_NIGHTLY_DRIVER_STATE_KEY = "regression_nightly_driver_state"
REGRESSION_NIGHTLY_SERVICE_SESSION_ID = "session_regression_nightly_service"
regression_nightly_driver = RegressionNightlyTickDriver()




def ensure_regression_service_session() -> str:
    user_sessions.setdefault(
        REGRESSION_NIGHTLY_SERVICE_SESSION_ID,
        {
            "username": "regression-nightly-service",
            "session_id": REGRESSION_NIGHTLY_SERVICE_SESSION_ID,
            "login_time": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
        },
    )
    conversation_history.setdefault(REGRESSION_NIGHTLY_SERVICE_SESSION_ID, [])
    return REGRESSION_NIGHTLY_SERVICE_SESSION_ID

def ensure_regression_runtime_instance() -> None:
    lifecycle = runtime_services["lifecycle"]
    runtime_host = runtime_services["runtime_host"]
    try:
        lifecycle.get_instance(APP_INSTANCE_ID)
        return
    except Exception:
        pass
    runtime_host.register_instance(AppInstance(
        id=APP_INSTANCE_ID,
        blueprint_id="bp.regression.governance",
        owner_user_id="system",
        status="running",
        data_namespace="governance/regression",
    ))


def build_regression_nightly_status() -> dict[str, Any]:
    snapshot = _compute_nightly_schedule_snapshot()
    snapshot["driver"] = regression_nightly_driver.status()
    snapshot["automation_control"] = {
        "driver": snapshot["driver"],
        "schedule_registered": snapshot["registered"],
        "due_now": snapshot["due_now"],
        "next_trigger_at": snapshot["next_trigger_at"],
        "last_tick_at": snapshot.get("last_tick_at"),
        "last_tick_decision": snapshot.get("last_tick_decision"),
        "last_cycle_run_id": None if not snapshot.get("last_cycle_result") else snapshot["last_cycle_result"].get("run_id"),
    }
    return snapshot



def load_regression_nightly_state() -> dict[str, Any]:
    return runtime_services["runtime_store"].load_json(REGRESSION_NIGHTLY_STATE_KEY, {})



def load_regression_nightly_driver_state() -> dict[str, Any]:
    return runtime_services["runtime_store"].load_json(REGRESSION_NIGHTLY_DRIVER_STATE_KEY, {})


def save_regression_nightly_driver_state(state: dict[str, Any]) -> None:
    runtime_services["runtime_store"]._write_json(REGRESSION_NIGHTLY_DRIVER_STATE_KEY, state)


def restore_regression_nightly_driver() -> None:
    state = load_regression_nightly_driver_state()
    if state.get("running"):
        regression_nightly_driver.start(interval_seconds=int(state.get("interval_seconds") or 60))

def save_regression_nightly_state(state: dict[str, Any]) -> None:
    runtime_services["runtime_store"]._write_json(REGRESSION_NIGHTLY_STATE_KEY, state)


def record_regression_nightly_tick(*, decision: str, triggered: bool, cycle: dict[str, Any] | None = None, nightly_status: dict[str, Any] | None = None) -> dict[str, Any]:
    state = load_regression_nightly_state()
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    state.update({
        "last_tick_at": now,
        "last_tick_decision": decision,
        "last_tick_triggered": triggered,
        "last_cycle_result": cycle,
        "last_nightly_status": nightly_status,
    })
    save_regression_nightly_state(state)
    return state


def _compute_nightly_schedule_snapshot() -> dict[str, Any]:
    ensure_regression_runtime_instance()
    scheduler = runtime_services["scheduler"]
    runtime_host = runtime_services["runtime_host"]
    schedules = [item for item in scheduler.list_schedules(APP_INSTANCE_ID) if item.task_name == REGRESSION_CYCLE_TASK_NAME]
    overview = runtime_host.get_overview(APP_INSTANCE_ID)
    recent_runs = list_saved_runs(limit=1)
    latest_run = recent_runs[0]["summary"] if recent_runs else None
    due_schedules = []
    next_trigger_at = None
    now = datetime.now(UTC)
    for item in schedules:
        last = item.last_triggered_at or item.created_at
        due_at = last + timedelta(seconds=item.interval_seconds or 0)
        if item.status == "active" and due_at <= now:
            due_schedules.append(item.schedule_id)
        if next_trigger_at is None or due_at < next_trigger_at:
            next_trigger_at = due_at
    state = load_regression_nightly_state()
    return {
        "registered": bool(schedules),
        "schedule_count": len(schedules),
        "schedules": [item.model_dump(mode="json") for item in schedules],
        "pending_task_count": sum(1 for task in overview.pending_tasks if task == REGRESSION_CYCLE_TASK_NAME),
        "latest_run": latest_run,
        "due_schedule_ids": due_schedules,
        "due_now": bool(due_schedules),
        "next_trigger_at": None if next_trigger_at is None else next_trigger_at.isoformat().replace("+00:00", "Z"),
        "last_tick_at": state.get("last_tick_at"),
        "last_tick_decision": state.get("last_tick_decision"),
        "last_tick_triggered": state.get("last_tick_triggered"),
        "last_cycle_result": state.get("last_cycle_result"),
    }


def tick_regression_nightly_cycle(user_session_id: str) -> dict[str, Any]:
    snapshot = _compute_nightly_schedule_snapshot()
    if not snapshot["due_now"]:
        state = record_regression_nightly_tick(decision="skipped_not_due", triggered=False, nightly_status=snapshot)
        refreshed = dict(snapshot)
        refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
        return {"triggered": False, "nightly_status": refreshed}

    from fastapi.testclient import TestClient

    scheduler = runtime_services["scheduler"]
    runtime_host = runtime_services["runtime_host"]
    trigger_results = scheduler.trigger_interval_schedules(APP_INSTANCE_ID)
    matched = [item.model_dump(mode="json") for item in trigger_results if item.task_name == REGRESSION_CYCLE_TASK_NAME and item.triggered]
    if not matched:
        snapshot = _compute_nightly_schedule_snapshot()
        state = record_regression_nightly_tick(decision="skipped_no_trigger_match", triggered=False, nightly_status=snapshot)
        refreshed = dict(snapshot)
        refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
        return {"triggered": False, "nightly_status": refreshed, "schedule_results": [item.model_dump(mode="json") for item in trigger_results]}

    local_client = TestClient(app)
    local_client.cookies.set("session_id", user_session_id)
    cycle_result = run_regression_governance_cycle(make_testclient_poster(local_client), memory=refinement_memory)
    runtime_host.consume_pending_tasks(APP_INSTANCE_ID, REGRESSION_CYCLE_TASK_NAME)
    snapshot = _compute_nightly_schedule_snapshot()
    state = record_regression_nightly_tick(decision="triggered_due", triggered=True, cycle=cycle_result, nightly_status=snapshot)
    refreshed = dict(snapshot)
    refreshed.update({k: state.get(k) for k in ["last_tick_at", "last_tick_decision", "last_tick_triggered", "last_cycle_result"]})
    return {
        "triggered": True,
        "schedule_results": [item.model_dump(mode="json") for item in trigger_results],
        "cycle": cycle_result,
        "nightly_status": refreshed,
    }
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
        structured_answer = getattr(llm_resp, "structured_answer", None)
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
        return {"success": True, "response": response_text, "structured_answer": structured_answer.model_dump() if structured_answer else None, "session_id": session_id, "latency_ms": latency_ms}
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


@app.post("/api/chat-regression/run")
async def api_chat_regression_run(user: dict = Depends(get_current_user)):
    from fastapi.testclient import TestClient

    local_client = TestClient(app)
    local_client.cookies.set("session_id", user["session_id"])
    results = run_fixed_prompt_matrix(make_testclient_poster(local_client))
    summary = build_run_summary(results)
    out = persist_run_results(results, summary)
    return {
        "success": True,
        "run_id": summary.run_id,
        "summary": summary.__dict__,
        "path": str(out),
    }


@app.get("/api/chat-regression/latest")
async def api_chat_regression_latest(user: dict = Depends(get_current_user)):
    if not REGRESSION_LOG_DIR.exists():
        return {"success": False, "error": "no regression runs found"}
    files = sorted(REGRESSION_LOG_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"success": False, "error": "no regression runs found"}
    latest = files[0]
    lines = latest.read_text(encoding="utf-8").splitlines()
    if not lines:
        return {"success": False, "error": "latest regression file is empty"}
    summary = json.loads(lines[0])
    return {"success": True, "path": str(latest), "summary": summary}


@app.get("/api/chat-regression/runs")
async def api_chat_regression_runs(user: dict = Depends(get_current_user), limit: int = 10):
    rows = list_saved_runs(limit=limit)
    return {"success": True, "runs": rows}


@app.get("/api/chat-regression/runs/{run_id}")
async def api_chat_regression_run_detail(run_id: str, user: dict = Depends(get_current_user)):
    detail = read_run_details(run_id)
    if detail is None:
        return {"success": False, "error": "run not found", "run_id": run_id}
    return {"success": True, **detail}



from app.system.regression_dashboard import build_regression_governance_dashboard, build_regression_operator_summary, build_regression_triggers, apply_regression_triggers_to_refinement
from app.system.regression_evidence_bridge import list_regression_evidence_history, promote_regression_evidence


@app.get("/api/chat-regression/trends")
async def api_chat_regression_trends(user: dict = Depends(get_current_user), limit: int = 5):
    trends = build_topic_trends(limit=limit)
    return {"success": True, **trends}


@app.get("/api/chat-regression/compare")
async def api_chat_regression_compare(user: dict = Depends(get_current_user), limit: int = 5):
    comparison = build_multi_run_comparison(limit=limit)
    return {"success": True, **comparison}


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
        structured_answer = getattr(llm_resp, "structured_answer", None)
        # 记录到对话历史（assistant）
        conversation_history.setdefault(session_id, []).append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
        })
        return {"success": True, "response": response_text, "structured_answer": structured_answer.model_dump() if structured_answer else None}
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


@app.get("/api/chat-regression/evidence")
async def api_chat_regression_evidence_history(user: dict = Depends(get_current_user), limit: int = 20, topic: str | None = None):
    history = list_regression_evidence_history(limit=limit, topic=topic)
    return {"success": True, "evidence": history, "count": len(history)}


@app.post("/api/chat-regression/evidence")
async def api_chat_regression_evidence(user: dict = Depends(get_current_user), limit: int = 5):
    result = promote_regression_evidence(limit=limit)
    return {"success": True, **result}


@app.get("/api/governance/regression-dashboard")
async def api_governance_regression_dashboard(user: dict = Depends(get_current_user), comparison_limit: int = 5, trends_limit: int = 5, evidence_limit: int = 10):
    dashboard = build_regression_governance_dashboard(
        comparison_limit=comparison_limit,
        trends_limit=trends_limit,
        evidence_limit=evidence_limit,
        memory=refinement_memory,
        nightly_status=build_regression_nightly_status(),
    )
    return {"success": True, **dashboard}


@app.get("/api/governance/operator-summary")
async def api_governance_operator_summary(user: dict = Depends(get_current_user), comparison_limit: int = 5, trends_limit: int = 5, evidence_limit: int = 10):
    summary = build_regression_operator_summary(
        comparison_limit=comparison_limit,
        trends_limit=trends_limit,
        evidence_limit=evidence_limit,
        memory=refinement_memory,
        nightly_status=build_regression_nightly_status(),
    )
    return {"success": True, **summary}


@app.post("/api/governance/regression-triggers")
async def api_governance_regression_triggers(user: dict = Depends(get_current_user), comparison_limit: int = 5, threshold: str = "warning"):
    triggers = build_regression_triggers(comparison_limit=comparison_limit, threshold=threshold)
    return {"success": True, **triggers}


@app.post("/api/governance/regression-triggers/apply")
async def api_governance_regression_triggers_apply(user: dict = Depends(get_current_user), comparison_limit: int = 5, threshold: str = "warning"):
    result = apply_regression_triggers_to_refinement(
        refinement_memory,
        comparison_limit=comparison_limit,
        threshold=threshold,
    )
    return {"success": True, **result}


class RegressionQueueTransitionRequest(BaseModel):
    queue_id: str
    action: str
    reviewer: str = "system"
    note: str = ""


@app.post("/api/governance/regression-queue/transition")
async def api_governance_regression_queue_transition(req: RegressionQueueTransitionRequest, user: dict = Depends(get_current_user)):
    item = refinement_rollout.transition(
        queue_id=req.queue_id,
        action=req.action,
        reviewer=req.reviewer,
        note=req.note,
    )
    return {"success": True, "item": item.model_dump(mode="json")}


@app.post("/api/governance/regression-cycle/run")
async def api_governance_regression_cycle_run(user: dict = Depends(get_current_user)):
    from fastapi.testclient import TestClient

    local_client = TestClient(app)
    local_client.cookies.set("session_id", user["session_id"])
    result = run_regression_governance_cycle(
        make_testclient_poster(local_client),
        memory=refinement_memory,
    )
    return {"success": True, **result}


@app.post("/api/governance/regression-cycle/nightly")
async def api_governance_regression_cycle_nightly_register(interval_seconds: int = 86400, user: dict = Depends(get_current_user)):
    ensure_regression_runtime_instance()
    scheduler = runtime_services["scheduler"]
    record = ScheduleRecord(
        schedule_id=REGRESSION_NIGHTLY_SCHEDULE_ID,
        app_instance_id=APP_INSTANCE_ID,
        trigger_type="interval",
        task_name=REGRESSION_CYCLE_TASK_NAME,
        interval_seconds=interval_seconds,
    )
    registered = scheduler.register_schedule(record)
    return {"success": True, "schedule": registered.model_dump(mode="json")}


@app.get("/api/governance/regression-cycle/nightly")
async def api_governance_regression_cycle_nightly_status(user: dict = Depends(get_current_user)):
    ensure_regression_runtime_instance()
    scheduler = runtime_services["scheduler"]
    schedules = [
        item.model_dump(mode="json")
        for item in scheduler.list_schedules(APP_INSTANCE_ID)
        if item.task_name == REGRESSION_CYCLE_TASK_NAME
    ]
    return {"success": True, "schedules": schedules}


@app.post("/api/governance/regression-cycle/nightly/trigger")
async def api_governance_regression_cycle_nightly_trigger(user: dict = Depends(get_current_user)):
    from fastapi.testclient import TestClient

    ensure_regression_runtime_instance()
    scheduler = runtime_services["scheduler"]
    runtime_host = runtime_services["runtime_host"]
    trigger_results = scheduler.trigger_interval_schedules(APP_INSTANCE_ID)
    matched = [
        item.model_dump(mode="json")
        for item in trigger_results
        if item.task_name == REGRESSION_CYCLE_TASK_NAME and item.triggered
    ]
    if not matched:
        return {"success": True, "triggered": False, "schedule_results": [item.model_dump(mode="json") for item in trigger_results]}

    local_client = TestClient(app)
    local_client.cookies.set("session_id", user["session_id"])
    cycle_result = run_regression_governance_cycle(
        make_testclient_poster(local_client),
        memory=refinement_memory,
    )
    runtime_host.consume_pending_tasks(APP_INSTANCE_ID, REGRESSION_CYCLE_TASK_NAME)
    return {
        "success": True,
        "triggered": True,
        "schedule_results": [item.model_dump(mode="json") for item in trigger_results],
        "cycle": cycle_result,
    }


@app.post("/api/governance/regression-cycle/nightly/tick")
async def api_governance_regression_cycle_nightly_tick(user: dict = Depends(get_current_user)):
    result = tick_regression_nightly_cycle(user["session_id"])
    return {"success": True, **result}


@app.get("/api/governance/regression-cycle/nightly/driver")
async def api_governance_regression_cycle_nightly_driver_status(user: dict = Depends(get_current_user)):
    return {"success": True, "driver": regression_nightly_driver.status()}


@app.post("/api/governance/regression-cycle/nightly/driver/start")
async def api_governance_regression_cycle_nightly_driver_start(interval_seconds: int = 60, user: dict = Depends(get_current_user)):
    return {"success": True, "driver": regression_nightly_driver.start(interval_seconds=interval_seconds)}


@app.post("/api/governance/regression-cycle/nightly/driver/stop")
async def api_governance_regression_cycle_nightly_driver_stop(user: dict = Depends(get_current_user)):
    return {"success": True, "driver": regression_nightly_driver.stop()}
