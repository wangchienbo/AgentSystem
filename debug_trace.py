"""Debug script to trace ToolCallingInterpreter behavior."""
import asyncio
from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest

services = build_runtime()
gateway = services["light_brain_gateway"]
interpreter = gateway._interpreter

# Check what tools are available
print("=== Hot Tool Manager ===")
hot_tools = interpreter._hot_tool_manager.get_tools_for_session("test-session")
for t in hot_tools:
    print(f"  - {t.get('name')}: {t.get('description')[:60]}...")

print("\n=== Test interpret ===")
from app.models.chat import InterpretedCommand
command = interpreter.interpret(
    message="查看资产 asset:runtime_center:v1 的详情",
    user_id="test-user",
    session_id="e2e-test-detail",
    available_apps=[],
)
print(f"Intent: {command.intent}")
print(f"Parameters: {command.parameters}")
print(f"Source: {command.source}")
print(f"Requires clarification: {command.requires_clarification}")
print(f"Raw input: {command.raw_input}")
