#!/usr/bin/env python3
"""E2E LLM Tool Calling test - reads API key from config only."""
import sys
sys.path.insert(0, '/root/project/AgentSystem')

from app.ai.tool_calling_engine import ToolCallingEngine, ToolDef
from app.ai.model_router import ModelRouter

# Setup - API key loaded from config.yaml
router = ModelRouter()
engine = ToolCallingEngine(router)

# Register simple tools
def get_weather(city: str):
    return {'city': city, 'temperature': 25, 'condition': 'sunny', 'humidity': 60}

def calculate(a: float, b: float, operation: str):
    ops = {'add': a + b, 'subtract': a - b, 'multiply': a * b, 'divide': a / b if b != 0 else None}
    return ops.get(operation, 'unknown operation')

engine.register_tool('get_weather', get_weather)
engine.register_tool('calculate', calculate)

# Tool definitions
tools = [
    ToolDef(
        name='get_weather',
        description='Get current weather for a city',
        parameters={
            'type': 'object',
            'properties': {
                'city': {'type': 'string', 'description': 'City name'}
            },
            'required': ['city']
        }
    ),
    ToolDef(
        name='calculate',
        description='Perform arithmetic operation',
        parameters={
            'type': 'object',
            'properties': {
                'a': {'type': 'number', 'description': 'First number'},
                'b': {'type': 'number', 'description': 'Second number'},
                'operation': {'type': 'string', 'enum': ['add', 'subtract', 'multiply', 'divide'], 'description': 'Operation'}
            },
            'required': ['a', 'b', 'operation']
        }
    )
]

print('=== LLM E2E Tool Calling Test ===')
print(f'Router API key from config: {router._fallback_api_key[:20] if router._fallback_api_key else "None"}...')

result = engine.execute_turns(
    skill_id='test_skill',
    asset_id='app_test_001',
    system_prompt='You are a helpful assistant. Use tools when needed. Always call calculate for math.',
    user_message='What is 123 * 456? Also, what is the weather in Tokyo?',
    tools=tools,
    max_turns=3,
    temperature=0.3,
    max_tokens=2048,
    model_override='gpt-5.4'
)

print(f'\n✅ LLM E2E completed!')
print(f'   Turns: {result.turns}, Truncated: {result.truncated}')
print(f'   Final: {result.final_text[:200]}...' if len(result.final_text) > 200 else f'   Final: {result.final_text}')
print(f'   Tool calls: {len(result.tool_calls)}')
for tc in result.tool_calls:
    print(f'     - {tc.tool_name}({tc.args}) => {tc.result}')
print(f'   Usage: {result.usage}')
