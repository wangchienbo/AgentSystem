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
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path
from pydantic import BaseModel, Field

# Setup paths
import sys
sys.path.insert(0, '/root/project/AgentSystem')

# ---------------------------------------------------------------------------
# Load global ``app`` configuration from ~/.config/agentsystem/config.yaml
# This ensures API layer parameters are not hard-coded.
# ---------------------------------------------------------------------------
GLOBAL_CONFIG_PATH = Path("/root/.config/agentsystem/config.yaml")

def _load_app_config() -> dict:
    """Load the top-level ``app`` section from the global config.
    
    Returns a dict with defaults if the file or the ``app`` key is missing.
    """
    defaults = {"max_turns": 30, "port": 80, "host": "0.0.0.0"}
    try:
        cfg = yaml.safe_load(GLOBAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        app_cfg = cfg.get("app", {}) or {}
        defaults.update(app_cfg)
    except Exception:
        # Fallback to hard-coded defaults if config is missing or invalid
        pass
    return defaults

_APP_GLOBALS = _load_app_config()

# Bootstrap
from app.bootstrap.runtime import build_runtime
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.services.light_brain_memory import LightBrainMemory
from app.services.light_brain_interpreter import LightBrainInterpreter

logger = logging.getLogger(__name__)
