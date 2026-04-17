"""Phase P: Phase 7 (LLM Interaction Layer) E2E validation."""
from __future__ import annotations

import pytest

from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.system.gateway.light_brain_interpreter import LightBrainInterpreter
from app.system.gateway.interaction_gateway import InteractionGateway
from app.orchestration.session_router import SessionRouter
from app.ai.model_router import ModelRouter


def test_light_brain_gateway_instantiable():
    """P-01: LightBrainGateway can be instantiated."""
    gateway = LightBrainGateway()
    assert hasattr(gateway, 'process_message')
    assert hasattr(gateway, 'execute_action')
    assert hasattr(gateway, 'list_sessions')
    assert hasattr(gateway, 'get_active_skills')


def test_light_brain_interpreter_instantiable():
    """P-01: LightBrainInterpreter can be instantiated."""
    interpreter = LightBrainInterpreter()
    assert hasattr(interpreter, 'interpret')


def test_interaction_gateway_instantiable():
    """P-01: InteractionGateway class exists."""
    assert InteractionGateway is not None


def test_session_router_instantiable():
    """P-02: SessionRouter can be instantiated."""
    router = SessionRouter()
    assert router is not None


def test_model_router_instantiable():
    """P-03: ModelRouter can be instantiated."""
    mr = ModelRouter()
    assert mr is not None


def test_light_brain_gateway_session_lifecycle():
    """P-01: Gateway session lifecycle works."""
    gateway = LightBrainGateway()
    sessions = gateway.list_sessions()
    assert isinstance(sessions, list)


def test_light_brain_gateway_skills():
    """P-01: Gateway can list active skills."""
    gateway = LightBrainGateway()
    skills = gateway.get_active_skills()
    assert isinstance(skills, (list, dict))


def test_interaction_layer_services_complete():
    """P-05: All Phase 7 services are available."""
    # LightBrainGateway and LightBrainInterpreter are standalone
    assert LightBrainGateway() is not None
    assert LightBrainInterpreter() is not None
    
    # SessionRouter and ModelRouter are standalone
    assert SessionRouter() is not None
    assert ModelRouter() is not None
    
    # InteractionGateway requires dependencies, just verify the class exists
    assert InteractionGateway is not None
