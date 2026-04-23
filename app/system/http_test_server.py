"""AgentSystem HTTP Test Server with Authentication.

Provides:
- Login page with authentication
- Mobile-first chat UI
- Isolated plain-LLM chat endpoint for web testing
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from openai import AsyncOpenAI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

user_sessions: dict[str, dict[str, Any]] = {}
conversation_history: dict[str, list[dict[str, str]]] = {}

llm_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "sk-placeholder",
    base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
)
llm_model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


async def get_current_user(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_sessions[session_id]


@app.get("/", response_class=FileResponse)
async def root():
    return FileResponse(STATIC_DIR / "index.html")


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
    session_id = f"session_{username}_{int(datetime.now().timestamp())}"
    user_sessions[session_id] = {
        "username": username,
        "session_id": session_id,
        "login_time": datetime.now().isoformat(),
    }
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="session_id", value=session_id, max_age=3600, httponly=False)
    return response


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
    history = conversation_history.get(session_id, [])[-10:]

    messages = [{
        "role": "system",
        "content": "You are a helpful coding assistant inside AgentSystem. Reply in Chinese unless the user asks otherwise.",
    }]
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message})

    try:
        resp = await llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
        )
        response_text = resp.choices[0].message.content or ""

        conversation_history.setdefault(session_id, []).append(
            {
                "role": "user",
                "content": req.message,
                "timestamp": datetime.now().isoformat(),
            }
        )
        conversation_history.setdefault(session_id, []).append(
            {
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.now().isoformat(),
            }
        )
        return {"success": True, "response": response_text, "session_id": session_id}
    except Exception as e:
        logger.exception("Error processing message")
        return {"success": False, "error": f"LLM request failed: {str(e)}"}


@app.get("/api/status")
async def api_status():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(user_sessions),
        "llm_model": llm_model,
    }


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_id")
    return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "80"))
    uvicorn.run(app, host="0.0.0.0", port=port)
