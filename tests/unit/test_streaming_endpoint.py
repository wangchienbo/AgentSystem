"""Tests for the SSE streaming chat endpoint.

Uses the main app directly (not the test helper) since the streaming
endpoint is only registered in app.api.main.
"""

import json

from fastapi.testclient import TestClient
from pathlib import Path

from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.bootstrap.catalog import bootstrap_demo_catalog
from fastapi import FastAPI


def _build_streaming_test_app(tmp_path: Path) -> FastAPI:
    """Build a minimal test app that includes the streaming endpoint."""
    from app.api.main import app as main_app

    # Build the runtime services so the main app has what it needs
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    bootstrap_builtin_skills(services["skill_runtime"], services)
    bootstrap_demo_catalog(services["app_registry"], services["app_catalog"])

    # The main app already has streaming endpoint registered at module load
    # We just need to return it with the test services injected
    return main_app


def test_streaming_endpoint_returns_sse(tmp_path: Path) -> None:
    """Verify POST /chat/message/stream returns text/event-stream."""
    from app.api.main import app
    with TestClient(app) as client:
        response = client.post(
            "/chat/message/stream",
            json={
                "user_id": "test-stream",
                "channel": "webchat",
                "message": "hello",
            },
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_streaming_endpoint_chunks_are_valid_sse(tmp_path: Path) -> None:
    """Verify streamed data lines parse as valid SSE events."""
    from app.api.main import app
    with TestClient(app) as client:
        response = client.post(
            "/chat/message/stream",
            json={
                "user_id": "test-stream",
                "channel": "webchat",
                "message": "test streaming",
            },
        )
        text = response.text
        lines = text.strip().split("\n\n")

        # Should have at least chunk events and a complete event
        assert len(lines) >= 2

        # Parse each SSE event
        chunk_count = 0
        has_complete = False
        for block in lines:
            assert block.startswith("data: ")
            data = json.loads(block[6:])  # strip "data: " prefix
            if data["type"] == "chunk":
                chunk_count += 1
                assert "content" in data
            elif data["type"] == "complete":
                has_complete = True
                assert "content" in data
                assert "session_id" in data
                assert "actions" in data

        assert chunk_count > 0
        assert has_complete


def test_streaming_endpoint_complete_event_has_session_id(tmp_path: Path) -> None:
    """Verify the complete event includes a session_id for session tracking."""
    from app.api.main import app
    with TestClient(app) as client:
        response = client.post(
            "/chat/message/stream",
            json={
                "user_id": "test-session",
                "channel": "webchat",
                "message": "create session",
            },
        )
        text = response.text
        last_block = text.strip().split("\n\n")[-1]
        data = json.loads(last_block[6:])

        assert data["type"] == "complete"
        assert data["session_id"]
        assert isinstance(data["actions"], list)


def test_streaming_endpoint_error_handling(tmp_path: Path) -> None:
    """Verify streaming endpoint returns 422 on invalid request."""
    from app.api.main import app
    with TestClient(app) as client:
        # Send invalid message (empty)
        response = client.post(
            "/chat/message/stream",
            json={
                "user_id": "test-error",
                "channel": "webchat",
                "message": "",  # empty message should trigger validation error
            },
        )
        # FastAPI should reject invalid request
        assert response.status_code == 422
