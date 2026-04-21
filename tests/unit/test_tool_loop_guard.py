"""Tests for tool loop guard service."""
import pytest
import time
from app.services.tool_loop_guard import ToolLoopGuard, ToolLoopConfig


class TestToolLoopGuard:
    """Test tool loop guard functionality."""
    
    def test_allows_normal_tool_calls(self):
        """Test that normal tool calls are allowed."""
        guard = ToolLoopGuard()
        timestamp = time.time()
        
        allowed, _ = guard.check_allowed("test_tool", {"arg": "value"}, timestamp)
        assert allowed
    
    def test_blocks_over_command_limit(self):
        """Test that tool calls over command limit are blocked."""
        config = ToolLoopConfig(max_tool_calls_per_command=3)
        guard = ToolLoopGuard(config)
        
        # Make 3 calls
        for i in range(3):
            guard.record_call("test_tool", {}, time.time())
        
        allowed, reason = guard.check_allowed("test_tool", {}, time.time())
        assert not allowed
        assert "Tool call limit per command exceeded" in reason
    
    def test_blocks_rapid_calls(self):
        """Test that rapid tool calls are blocked."""
        config = ToolLoopConfig(
            max_rapid_calls=5,
            rapid_call_window_seconds=5.0
        )
        guard = ToolLoopGuard(config)
        base_time = time.time()
        
        # Make 5 rapid calls
        for i in range(5):
            guard.record_call("test_tool", {}, base_time)
        
        allowed, reason = guard.check_allowed("test_tool", {}, base_time)
        assert not allowed
        assert "Rapid tool call limit exceeded" in reason
    
    def test_detects_repeating_pattern(self):
        """Test detection of repeating tool call patterns."""
        config = ToolLoopConfig(max_tool_calls_per_command=100)
        guard = ToolLoopGuard(config)
        base_time = time.time()
        
        # Record 3 identical calls
        for _ in range(3):
            guard.record_call("same_tool", {"arg": "value"}, base_time)
        
        # 4th identical call should be blocked as repeating pattern
        allowed, reason = guard.check_allowed("same_tool", {"arg": "value"}, base_time)
        assert not allowed
        assert "Repeating tool call pattern detected" in reason
    
    def test_allows_different_tool_calls(self):
        """Test that different tool calls are allowed even in sequence."""
        guard = ToolLoopGuard()
        base_time = time.time()
        
        # Record different tool calls
        guard.record_call("tool_a", {"arg": 1}, base_time)
        guard.record_call("tool_b", {"arg": 2}, base_time)
        guard.record_call("tool_c", {"arg": 3}, base_time)
        
        # Different 4th call should be allowed
        allowed, _ = guard.check_allowed("tool_d", {"arg": 4}, base_time)
        assert allowed
    
    def test_reset_command(self):
        """Test resetting command counters."""
        config = ToolLoopConfig(max_tool_calls_per_command=2)
        guard = ToolLoopGuard(config)
        
        # Make 2 calls
        for _ in range(2):
            guard.record_call("test_tool", {}, time.time())
        
        # Should be blocked
        allowed, _ = guard.check_allowed("test_tool", {}, time.time())
        assert not allowed
        
        # Reset and try again
        guard.reset_command()
        allowed, _ = guard.check_allowed("test_tool", {}, time.time())
        assert allowed
    
    def test_get_stats(self):
        """Test statistics reporting."""
        guard = ToolLoopGuard()
        base_time = time.time()
        
        guard.record_call("tool_a", {}, base_time)
        guard.record_call("tool_b", {}, base_time)
        guard.record_call("tool_a", {}, base_time)
        
        stats = guard.get_stats()
        assert stats["total_calls"] == 3
        assert stats["command_calls"] == 3
        assert stats["unique_tools"] == 2
    
    def test_pattern_detection_with_different_args(self):
        """Test that different arguments break pattern detection."""
        guard = ToolLoopGuard()
        base_time = time.time()
        
        # Record calls with different arguments
        guard.record_call("same_tool", {"arg": 1}, base_time)
        guard.record_call("same_tool", {"arg": 2}, base_time)
        guard.record_call("same_tool", {"arg": 3}, base_time)
        
        # Should not be blocked (different args)
        allowed, _ = guard.check_allowed("same_tool", {"arg": 4}, base_time)
        assert allowed
