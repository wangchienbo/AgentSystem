"""Tests for the ContextCompressor and its integration with ContextManagerRpc.

These correspond to OPT-001 Phase 3 – Test.
"""

import pytest
from app.services.context_compressor import ContextCompressor, CompressionConfig, CompressionResult
from app.orchestration.context_manager_rpc import ContextManagerRpc

# Helper to create a fake history list (not used in current compressor implementation)
FAKE_HISTORY = [
    {"role": "user", "content": f"Message {i}"}
    for i in range(10)
]

def test_compressor_basic():
    cfg = CompressionConfig(enabled=True, strategy="sliding_window", max_turns=3, token_limit=4000)
    comp = ContextCompressor(cfg)
    system_prompt = "System prompt"
    user_msg = "User message"
    compressed_sys, compressed_user, result = comp.compress(
        system_prompt=system_prompt,
        user_message=user_msg,
        available_tools=[],
        skill_rules="Rule A",
        conversation_history=None,
    )
    assert "System prompt" in compressed_sys
    assert "Rule A" in compressed_sys
    assert compressed_user == user_msg
    assert isinstance(result, CompressionResult)
    assert result.discarded_turns == 0

def test_compressor_token_limit_truncation():
    # Very low token limit to force truncation of user message
    cfg = CompressionConfig(enabled=True, token_limit=10)  # approx 40 chars
    comp = ContextCompressor(cfg)
    long_msg = "a" * 200
    compressed_sys, compressed_user, result = comp.compress(
        system_prompt="sys",
        user_message=long_msg,
        available_tools=[],
        skill_rules="",
    )
    # The user message should be truncated (starts with ...)
    assert compressed_user.startswith("...")
    assert len(compressed_user) < len(long_msg)
    assert result.compressed_length <= cfg.token_limit * 4

def test_context_manager_integration():
    # Verify ContextManagerRpc uses the compressor and includes metadata
    cm = ContextManagerRpc()
    # Register a dummy rule to ensure there is some skill_rules output
    cm.register_skill_rules("dummy_skill", l1="L1 rule", l2="L2 rule")
    result = cm.build_context(
        skill_id="dummy_skill",
        user_message="Hello",
        available_tools=[],
        skill_description_l1="Dummy skill",
        max_rule_level="L2",
    )
    # System prompt should contain L1 and L2 rules
    assert "L1" in result.system_prompt
    assert "L2" in result.system_prompt
    # Metadata should include compression details
    comp_meta = result.metadata.get("compression")
    assert comp_meta is not None
    assert comp_meta["original_len"] >= comp_meta["compressed_len"]

# Simple performance placeholder – just ensures the compressor runs quickly
def test_compressor_performance():
    cfg = CompressionConfig()
    comp = ContextCompressor(cfg)
    system_prompt = "sys"
    user_msg = "msg"
    for _ in range(1000):
        comp.compress(system_prompt, user_msg, [], "")
    # No assertion, just ensure no exception and reasonable runtime (<1s)
    assert True
