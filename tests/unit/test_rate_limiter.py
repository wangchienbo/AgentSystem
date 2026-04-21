"""Tests for rate limiter service."""
import pytest
from app.services.rate_limiter import RateLimiter, RateLimitConfig


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_allows_within_concurrent_limit(self):
        """Test that queries within concurrent limit are allowed."""
        config = RateLimitConfig(max_concurrent_queries_per_session=3)
        limiter = RateLimiter(config)
        
        allowed, _ = limiter.is_session_allowed("session_1")
        assert allowed
    
    def test_blocks_over_concurrent_limit(self):
        """Test that queries over concurrent limit are blocked."""
        config = RateLimitConfig(max_concurrent_queries_per_session=2)
        limiter = RateLimiter(config)
        
        limiter.increment_concurrent("session_1")
        limiter.increment_concurrent("session_1")
        
        allowed, reason = limiter.is_session_allowed("session_1")
        assert not allowed
        assert "Concurrent query limit exceeded" in reason
    
    def test_records_query_timestamps(self):
        """Test that query timestamps are recorded."""
        limiter = RateLimiter()
        limiter.record_query("session_1")
        
        allowed, _ = limiter.is_session_allowed("session_1")
        assert allowed  # Should still be allowed
    
    def test_blocks_over_query_rate_limit(self):
        """Test that queries over rate limit are blocked."""
        config = RateLimitConfig(max_queries_per_session_per_minute=2)
        limiter = RateLimiter(config)
        
        limiter.record_query("session_1")
        limiter.record_query("session_1")
        
        allowed, reason = limiter.is_session_allowed("session_1")
        assert not allowed
        assert "Query rate limit exceeded" in reason
    
    def test_tool_call_limit_per_command(self):
        """Test tool call limit per command."""
        config = RateLimitConfig(max_tool_calls_per_command=3)
        limiter = RateLimiter(config)
        
        allowed, _ = limiter.is_tool_call_allowed("session_1", 0)
        assert allowed
        
        allowed, _ = limiter.is_tool_call_allowed("session_1", 2)
        assert allowed
        
        allowed, reason = limiter.is_tool_call_allowed("session_1", 3)
        assert not allowed
        assert "Tool call limit per command exceeded" in reason
    
    def test_tool_call_limit_per_session(self):
        """Test tool call limit per session."""
        config = RateLimitConfig(max_tool_calls_per_session=5, max_tool_calls_per_command=100)
        limiter = RateLimiter(config)
        
        # Record 5 tool calls
        for _ in range(5):
            limiter.record_tool_call("session_1")
        
        allowed, reason = limiter.is_tool_call_allowed("session_1", 0)
        assert not allowed
        assert "Tool call limit per session exceeded" in reason
    
    def test_decrement_concurrent(self):
        """Test decrementing concurrent queries."""
        limiter = RateLimiter()
        limiter.increment_concurrent("session_1")
        limiter.increment_concurrent("session_1")
        
        allowed_before, _ = limiter.is_session_allowed("session_1")
        # Should be blocked if limit is 1
        config = RateLimitConfig(max_concurrent_queries_per_session=1)
        limiter2 = RateLimiter(config)
        limiter2.increment_concurrent("session_1")
        allowed, _ = limiter2.is_session_allowed("session_1")
        assert not allowed
        
        limiter2.decrement_concurrent("session_1")
        allowed, _ = limiter2.is_session_allowed("session_1")
        assert allowed
    
    def test_reset_session(self):
        """Test resetting session state."""
        limiter = RateLimiter()
        limiter.record_query("session_1")
        limiter.increment_concurrent("session_1")
        limiter.record_tool_call("session_1")
        
        limiter.reset_session("session_1")
        
        allowed, _ = limiter.is_session_allowed("session_1")
        assert allowed  # Should be allowed after reset
