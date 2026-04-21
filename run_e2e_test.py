"""Run E2E test to verify asset tool execution chain."""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/e2e/test_qwen_gateway_e2e.py", "-v", "--tb=short"],
    cwd="/root/project/AgentSystem",
    capture_output=True,
    text=True,
    timeout=120
)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nReturn code: {result.returncode}")
