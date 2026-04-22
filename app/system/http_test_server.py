"""AgentSystem HTTP Test Server with Authentication.

Provides:
- Login page with authentication
- Redirect to专属 chat interface after login
- REST API for testing intent understanding
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Build runtime once
runtime_services = build_runtime()
gateway = runtime_services["light_brain_gateway"]

# FastAPI app
app = FastAPI(
    title="AgentSystem Test Server",
    description="HTTP interface for testing AgentSystem intent understanding",
    version="1.0.0"
)

# Security
security = HTTPBasic()

# In-memory user sessions (for testing only)
user_sessions: dict[str, dict[str, Any]] = {}

# Templates
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


# Pydantic models
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


# Auth dependency
async def get_current_user(request: Request):
    """Get current user from session."""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_sessions[session_id]


# Routes
@app.get("/", response_class=RedirectResponse)
async def root():
    """Redirect to login or chat based on auth."""
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Login - AgentSystem"}
    )


@app.post("/login")
async def login(request: Request, username: str, password: str):
    """Handle login."""
    # Simple auth (for testing only)
    session_id = f"session_{username}_{datetime.now().timestamp()}"
    user_sessions[session_id] = {
        "username": username,
        "session_id": session_id,
        "login_time": datetime.now().isoformat(),
    }
    
    response = RedirectResponse(url="/chat", status_code=302)
    response.set_cookie(key="session_id", value=session_id, max_age=3600)
    return response


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, user: dict = Depends(get_current_user)):
    """Chat interface."""
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "title": "Chat - AgentSystem",
            "user": user,
        }
    )


@app.post("/api/chat")
async def api_chat(
    req: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Process chat message through gateway."""
    session_id = req.session_id or user["session_id"]
    
    chat_request = ChatMessageRequest(
        message=req.message,
        session_id=session_id,
        user_id=user["username"],
    )
    
    try:
        response = await gateway.receive_message(chat_request)
        return {
            "success": True,
            "response": response.content,
            "session_id": session_id,
        }
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@app.get("/api/status")
async def api_status():
    """System status."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(user_sessions),
    }


@app.get("/logout")
async def logout():
    """Logout user."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_id")
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
