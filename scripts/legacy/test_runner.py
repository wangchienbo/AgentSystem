#!/usr/bin/env python3
"""Quick test runner for E2E tests."""
import pytest
import sys

sys.exit(pytest.main(["tests/e2e/test_qwen_gateway_e2e.py", "-v", "--tb=short"]))
