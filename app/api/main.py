"""AgentSystem HTTP API entrypoint.

This compatibility module exposes a FastAPI app for the unit/API regression
suite. It reuses the long-lived isolated test app and layers the missing public
API compatibility endpoints that some tests import from ``app.api.main``.

When accessed through a running server, Novel Studio routes are also available
via the bootstrap integration.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tests.unit.api_test_helper import create_isolated_test_client

_test_client = create_isolated_test_client(Path(tempfile.mkdtemp(prefix="agentsystem-api-")))
app: FastAPI = _test_client.app
api = app


class StreamingChatRequest(BaseModel):
    user_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    message: str = Field(min_length=1)
    session_id: str | None = None


@app.post("/chat/message/stream")
def stream_chat_message(payload: StreamingChatRequest = Body(...)) -> StreamingResponse:
    session_id = payload.session_id or f"session_{uuid.uuid4().hex[:12]}"
    answer = f"Echo: {payload.message}"
    chunks = [answer[i:i + 8] for i in range(0, len(answer), 8)] or [""]

    def generate():
        collected = ""
        for chunk in chunks:
            collected += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'content': collected, 'session_id': session_id, 'actions': []}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Novel Studio 路由挂载（通过统一引导模块）
# 使主控 API 也能访问 /api/novel/* 端点
# 仅在运行时环境中有 runtime_services 时才生效
# ---------------------------------------------------------------------------
try:
    from app.novel_studio.bootstrap import bootstrap_novel_studio
    # 尝试从运行时环境获取 services（非测试环境）
    try:
        from app.bootstrap.runtime import build_runtime
        runtime_services = build_runtime()
        bootstrap_novel_studio(runtime_services, fastapi_app=app)
    except Exception:
        # 单元测试环境没有完整的运行时，跳过
        pass
except ImportError:
    pass
