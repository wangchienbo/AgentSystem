"""AgentSystem HTTP API — Runtime + LightBrainGateway with user auth.

Design:
- Runtime: 160 components (MasterControl, ConfigCenter, ModelRouter, etc.)
- Gateway: LightBrainGateway handles message → intent → workflow
- Auth: Bearer token → user_id (simulates Gateway auth layer)
- APIs: /chat, /tool-call, /dynamic-path, /admin/*
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# Setup paths
import sys
sys.path.insert(0, '/root/project/AgentSystem')

# Bootstrap
from app.bootstrap.runtime import build_runtime
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.services.light_brain_memory import LightBrainMemory
from app.services.light_brain_interpreter import LightBrainInterpreter

logger = logging.getLogger(__name__)

# ============================================================================
# Global State
# ============================================================================

_runtime: dict[str, Any] | None = None
_gateway: LightBrainGateway | None = None

security = HTTPBearer(auto_error=False)


def get_runtime() -> dict[str, Any]:
    """Get or initialize runtime singleton."""
    global _runtime
    if _runtime is None:
        _runtime = build_runtime(
            runtime_store_base_dir=os.getenv("RUNTIME_STORE", "/mnt/data/runtime"),
            app_data_base_dir=os.getenv("APP_DATA", "/mnt/data/apps"),
        )
        logger.info(f"Runtime initialized: {len(_runtime)} components")
    return _runtime


def get_gateway() -> LightBrainGateway:
    """Get or initialize Gateway singleton."""
    global _gateway
    if _gateway is None:
        rt = get_runtime()
        
        # Build Gateway with runtime deps
        memory = LightBrainMemory()
        interpreter = LightBrainInterpreter()
        
        _gateway = LightBrainGateway(
            memory=memory,
            interpreter=interpreter,
            skill_runner=rt.get("skill_runner"),
            lifecycle=rt.get("app_lifecycle_service"),
            log_center=rt.get("log_center"),
            persistence=rt.get("persistence_service"),
            master_control=rt.get("master_control"),
        )
        
        # Inject runtime refs
        _gateway.set_orchestrator_bridge(rt.get("gateway_orchestrator_bridge"))
        _gateway.set_runtime_host(rt.get("app_runtime_host"))
        _gateway.set_catalog(rt.get("catalog"))
        
        logger.info("LightBrainGateway initialized")
    return _gateway


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    """Extract user_id from Bearer token.
    
    Simulates Gateway auth layer. In production, this validates JWT/signature.
    Token obtained via POST /v1/auth/login.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization. POST /v1/auth/login first.",
        )
    
    token = credentials.credentials
    
    # Lookup token in active sessions
    if token in _active_tokens:
        return _active_tokens[token]
    
    # Dev mode: accept raw user_id as token
    if os.getenv("DEV_MODE", "0") == "1" and token.startswith("user_"):
        return token
    
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ============================================================================
# Simple Session Store (in-memory, prod would use Redis/DB)
# ============================================================================

_active_tokens: dict[str, str] = {}  # token -> user_id


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize Runtime and Gateway."""
    logger.info("🚀 Starting AgentSystem...")
    
    rt = get_runtime()
    gw = get_gateway()
    
    logger.info(f"✅ Runtime: {len(rt)} components loaded")
    logger.info(f"✅ Gateway: {gw._name or 'LightBrainGateway'} ready")
    
    yield
    
    logger.info("🛑 Shutting down...")


app = FastAPI(
    title="AgentSystem API",
    version="Phase H",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("DEV_MODE", "0") == "1" else None,
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    """Send a message to LightBrain."""
    message: str = Field(..., min_length=1, description="User's natural language message")
    session_id: str | None = Field(default=None, description="Existing session ID")
    channel: str = Field(default="web", description="Channel: web, qqbot, etc.")
    context: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class ChatResponse(BaseModel):
    """LightBrain reply."""
    reply: str
    session_id: str
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    inline_items: list[dict[str, Any]] = Field(default_factory=list)


class ToolCallRequest(BaseModel):
    """Direct LLM tool calling (bypass Gateway NLP)."""
    skill_id: str = Field(..., description="Skill identifier")
    system_prompt: str = Field(default="You are a helpful assistant.")
    user_message: str = Field(..., min_length=1)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    max_turns: int = Field(default=5, ge=1, le=20)
    model_override: str | None = None


class ToolCallResponse(BaseModel):
    """Tool calling result."""
    final_text: str
    tool_calls: list[dict[str, Any]]
    turns: int
    truncated: bool
    usage: dict[str, Any]


class DynamicPathRequest(BaseModel):
    """Plan skill chain for a request."""
    request: dict[str, Any] = Field(..., description="UserRequest object")
    context: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    runtime_components: int
    gateway_ready: bool


# ============================================================================
# Auth Endpoints
# ============================================================================

class LoginRequest(BaseModel):
    """Login credentials."""
    user_id: str = Field(..., min_length=3, description="User identifier")
    secret: str | None = Field(default=None, description="Password/secret (optional for dev)")


class LoginResponse(BaseModel):
    """Token response."""
    token: str
    user_id: str
    expires: str


@app.post("/v1/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and return Bearer token.
    
    Dev mode: accepts any user_id without password.
    Production: validates against user database + MasterControl auth.
    """
    # Validate user_id format
    if not req.user_id.isalnum() and not all(c in "_-" for c in req.user_id if not c.isalnum()):
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    
    # Generate token
    token = f"tok_{uuid.uuid4().hex[:24]}"
    
    # Store token → user_id mapping
    _active_tokens[token] = req.user_id
    
    return LoginResponse(
        token=token,
        user_id=req.user_id,
        expires="session",
    )


@app.post("/v1/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    """Invalidate token."""
    if credentials and credentials.credentials in _active_tokens:
        del _active_tokens[credentials.credentials]
    return {"status": "ok"}


# ============================================================================
# API Endpoints (require auth)
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check."""
    rt = get_runtime()
    gw = get_gateway()
    return HealthResponse(
        status="ok",
        runtime_components=len(rt),
        gateway_ready=gw is not None,
    )


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
):
    """Send message to LightBrain Gateway — main interaction entry.
    
    Flow: message → interpret intent → execute workflow → return reply.
    """
    from app.models.chat import ChatMessageRequest
    
    gateway = get_gateway()
    
    request = ChatMessageRequest(
        user_id=user_id,
        channel=req.channel,
        message=req.message,
        session_id=req.session_id,
        memory_context=req.context.get("memory_context"),
    )
    
    # Get available apps for this user from catalog
    rt = get_runtime()
    catalog = rt.get("catalog")
    available_apps = []
    if catalog and hasattr(catalog, "list_apps"):
        available_apps = catalog.list_apps(user_id=user_id)
    
    # Process through Gateway
    response = await gateway.receive_message(
        request=request,
        available_apps=available_apps,
        log_center=rt.get("log_center"),
    )
    
    return ChatResponse(
        reply=response.reply,
        session_id=response.session_id,
        suggestions=[s.model_dump() for s in (response.suggestions or [])],
        inline_items=[i.model_dump() for i in (response.inline_items or [])],
    )


@app.post("/v1/tool-call", response_model=ToolCallResponse)
async def tool_call(
    req: ToolCallRequest,
    user_id: str = Depends(get_current_user),
):
    """Direct LLM tool calling — for skill developers.
    
    Bypasses Gateway NLP, calls LLM directly with tools.
    """
    from app.ai.tool_calling_engine import ToolCallingEngine, ToolDef
    from app.ai.model_router import ModelRouter
    
    router = ModelRouter()
    engine = ToolCallingEngine(router)
    
    # Build ToolDef objects
    tools = [ToolDef(**t) for t in req.tools]
    
    # Execute with asset-aware routing
    result = engine.execute_turns(
        skill_id=req.skill_id,
        asset_id=f"user_{user_id}",  # User as asset context
        system_prompt=req.system_prompt,
        user_message=req.user_message,
        tools=tools,
        max_turns=req.max_turns,
        model_override=req.model_override,
    )
    
    return ToolCallResponse(
        final_text=result.final_text,
        tool_calls=[
            {"name": tc.tool_name, "args": tc.args, "result": tc.result, "error": tc.error}
            for tc in result.tool_calls
        ],
        turns=result.turns,
        truncated=result.truncated,
        usage=result.usage,
    )


@app.post("/v1/dynamic-path")
async def dynamic_path(
    req: DynamicPathRequest,
    user_id: str = Depends(get_current_user),
):
    """Plan skill chain via DynamicPathComposer.
    
    Used by Gateway when intent interpretation yields "orchestrate".
    """
    from app.orchestration.dynamic_path.dynamic_path_composer import DynamicPathComposer
    from app.models.dynamic_path import UserRequest
    
    rt = get_runtime()
    bridge = rt.get("gateway_orchestrator_bridge")
    config_center = rt.get("config_center")
    
    composer = DynamicPathComposer(
        bridge=bridge,
        config_center=config_center,
    )
    
    try:
        user_req = UserRequest(**req.request)
        plan = await composer.compose_path(user_req, context=req.context)
        
        return {
            "skill_chain": plan.skill_chain,
            "execution_plan": plan.execution_plan if hasattr(plan, "execution_plan") else None,
            "source": plan.source if hasattr(plan, "source") else "composed",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/runtime/components")
async def list_components(user_id: str = Depends(get_current_user)):
    """List loaded runtime components (admin only)."""
    # TODO: Check admin role via MasterControl
    rt = get_runtime()
    return {"components": list(rt.keys()), "count": len(rt)}


@app.get("/v1/config/models")
async def list_models(user_id: str = Depends(get_current_user)):
    """List available LLM models."""
    from app.ai.model_router import ModelRouter
    router = ModelRouter()
    return router.get_available_models()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    dev_mode = os.getenv("DEV_MODE", "0") == "1"
    
    # Auto-enable dev mode for local testing
    if host == "127.0.0.1":
        dev_mode = True
        os.environ["DEV_MODE"] = "1"
    
    logging.basicConfig(
        level=logging.INFO if not dev_mode else logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info(f"Starting AgentSystem API on {host}:{port}")
    logger.info(f"Dev mode: {dev_mode}")
    logger.info(f"API docs: http://{host}:{port}/docs" if dev_mode else "Docs disabled")
    
    uvicorn.run(
        "app.api.main:app",
        host=host,
        port=port,
        reload=dev_mode,
        log_level="info" if not dev_mode else "debug",
    )
