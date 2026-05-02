"""AgentSystem HTTP API entrypoint.

This compatibility module exposes a FastAPI app for the unit/API regression
suite. It reuses the long-lived isolated test app and layers the missing public
API compatibility endpoints that some tests import from ``app.api.main``.
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
