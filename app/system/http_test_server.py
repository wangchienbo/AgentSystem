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

# LLM client import
import os
from openai import AsyncOpenAI

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Build runtime once
runtime_services = build_runtime()
gateway = runtime_services["light_brain_gateway"]

# LLM client setup
llm_client = AsyncOpenAI(
    api_key=os.getenv("LLM_API_KEY", "sk-placeholder"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
)
llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

# FastAPI app
app = FastAPI(
    title="AgentSystem Test Server",
    description="HTTP interface for testing AgentSystem intent understanding",
    version="1.0.0"
)

# Serve static files (including the new mobile UI)
static_dir = Path(__file__).parent.parent / "app" / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
# Security
security = HTTPBasic()

# In-memory user sessions (for testing only)
user_sessions: dict[str, dict[str, Any]] = {}

# Conversation history storage: session_id -> list of messages
conversation_history: dict[str, list[dict[str, str]]] = {}

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
from fastapi.responses import FileResponse

@app.get("/", response_class=FileResponse)
async def root():
    """Serve the main chat UI (static index.html)."""
    static_dir = Path(__file__).parent.parent / "app" / "static"
    return FileResponse(static_dir / "index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Login - AgentSystem"}
    )


@app.post("/login")
async def login(request: Request):
    """Handle login."""
    # Get form data
    form_data = await request.form()
    username = form_data.get("username", "testuser")
    password = form_data.get("password", "testpass")
    
    # Simple auth (for testing only)
    session_id = f"session_{username}_{int(datetime.now().timestamp())}"
    user_sessions[session_id] = {
        "username": username,
        "session_id": session_id,
        "login_time": datetime.now().isoformat(),
    }
    
    response = RedirectResponse(url="/chat", status_code=302)
    response.set_cookie(key="session_id", value=session_id, max_age=3600, httponly=False)
    return response


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, user: dict = Depends(get_current_user)):
    """Chat interface."""
    session_id = user["session_id"]
    # Initialize conversation history if not exists
    if session_id not in conversation_history:
        conversation_history[session_id] = []
    
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "title": "Chat - AgentSystem",
            "user": user,
            "session_id": session_id,
            "history": conversation_history.get(session_id, []),
        }
    )

@app.get("/api/history/{session_id}")
async def api_get_history(session_id: str):
    """Get conversation history for a session."""
    return {
        "success": True,
        "history": conversation_history.get(session_id, []),
    }


@app.post("/api/chat")
async def api_chat(
    req: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Process chat message through LLM client."""
    session_id = req.session_id or user["session_id"]
    
    # Prepare message history (last 10 messages)
    history = conversation_history.get(session_id, [])[-10:]
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for h in history:
        role = "assistant" if h["role"] == "assistant" else "user"
        messages.append({"role": role, "content": h["content"]})
    messages.append({"role": "user", "content": req.message})
    
    try:
        # Call LLM
        llm_response = await llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
        )
        response_text = llm_response.choices[0].message.content
        
        # Store in conversation history
        if session_id not in conversation_history:
            conversation_history[session_id] = []
        # User message
        conversation_history[session_id].append({
            "role": "user",
            "content": req.message,
            "timestamp": datetime.now().isoformat(),
        })
        # Assistant response
        conversation_history[session_id].append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
        })
        
        return {
            "success": True,
            "response": response_text,
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
    # Use port 80 (HTTP default) for production, fallback to 8000 for dev
    import os
    port = int(os.environ.get("PORT", "80"))
    uvicorn.run(app, host="0.0.0.0", port=port)
