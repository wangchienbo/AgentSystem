"""http_routers 共享依赖持有器。

拆分前，http_test_server.py 的所有路由直接引用模块级变量（runtime_services 等）。
拆分后，各功能域 router 通过本模块访问共享依赖，避免与 http_test_server.py 形成循环导入。

主文件在启动时调用对应 setter 注入。
"""
from datetime import datetime

from fastapi import HTTPException, Request

_runtime_services: dict = {}
_templates = None
_static_dir = None
_user_sessions: dict = {}
_conversation_history: dict = {}
_lobster_sessions = None


def set_runtime_services(services: dict) -> None:
    """由 http_test_server.py 在构建 runtime_services 后调用注入。"""
    global _runtime_services
    _runtime_services = services


def get_runtime_services() -> dict:
    return _runtime_services


def set_templates(tpl) -> None:
    global _templates
    _templates = tpl


def get_templates():
    return _templates


def set_static_dir(path) -> None:
    global _static_dir
    _static_dir = path


def get_static_dir():
    return _static_dir


def set_sessions(user_sessions: dict, conversation_history: dict) -> None:
    """注入会话状态（由 http_test_server.py 传入共享可变 dict）。"""
    global _user_sessions, _conversation_history
    _user_sessions = user_sessions
    _conversation_history = conversation_history


def get_user_sessions() -> dict:
    return _user_sessions


def get_conversation_history() -> dict:
    return _conversation_history


def set_lobster_sessions(store) -> None:
    global _lobster_sessions
    _lobster_sessions = store


def get_lobster_sessions():
    return _lobster_sessions


_self_review_tick = None


def set_self_review_tick(driver) -> None:
    """注入周期审查驱动（由 http_test_server.py 在实例化后调用）。"""
    global _self_review_tick
    _self_review_tick = driver


def get_self_review_tick():
    return _self_review_tick


def get_current_user(request: Request):
    """认证依赖：从 cookie 解析 session_id 并水合用户会话。"""
    user_sessions = get_user_sessions()
    conversation_history = get_conversation_history()
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    existing = user_sessions.get(session_id)
    if existing:
        return existing

    username = session_id[len("session_"):] if session_id.startswith("session_") and len(session_id) > len("session_") else "anonymous"
    hydrated = {
        "username": username,
        "session_id": session_id,
        "login_time": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
    }
    user_sessions[session_id] = hydrated
    conversation_history.setdefault(session_id, [])
    return hydrated
