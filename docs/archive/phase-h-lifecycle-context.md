# Phase H+ Context 消费扩展：生命周期管理

> **完成时间**: 2026-04-22  
> **核心目标**: 将 Phase H context 注入到 App 生命周期控制链路（启动/停止/暂停/恢复）

## 背景

Phase H 已建立完整的上下文注入与消费闭环：
- Interpreter 消费 `recent_session_context` / `linked_session_context` / `child_session_contexts`
- 生成 `context_hints` 回填到 `command.parameters`
- Gateway 归一化为 `target_app` / `context_hints` / `related_session_ids`
- Worker 和 Refinement 内部消费这些字段

Phase H+ 扩展目标：将 context 消费扩展到生命周期管理（启动/停止/暂停/恢复），支持用户模糊指代如"启动它"、"停止刚才那个"。

## 消费链路

```
用户模糊指令（如"启动它"）
  → LightBrainInterpreter.interpret()
    - 消费 Phase H context (recent_session_context 等)
    - 生成 context_hints = ["target_app=小说 App"]
  → Gateway (回填到 command.parameters)
  → AppCommandService.execute()
  → AppLifecycleQueryExecutor.handle_start_app()
    - 当 command.target_app 缺失时，从 context_hints 提取 target_app
  → 执行启动操作
```

## 关键代码变更

### 修改文件：`app/services/app_lifecycle_query_executor.py`

#### `handle_start_app` 方法

```python
async def handle_start_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
    if command.requires_clarification:
        return ChatMessageResponse(
            type="text",
            content=command.clarification_question or "你想启动哪个 App？",
            session_id=session_id,
            actions=command.suggested_actions,
            requires_input=True,
        )
    
    # Phase H+ Context 消费：从 context_hints 推断 target_app
    target_input = command.target_app or "未知 App"
    params = command.parameters or {}
    context_hints = list(params.get("context_hints") or [])
    if not command.target_app and context_hints:
        for hint in context_hints:
            if hint.startswith("target_app="):
                target_input = hint.split("=", 1)[1]
                break
    
    target = self._resolve_instance_id(target_input)
    precheck = await self._ensure_static_presence(
        target=target,
        session_id=session_id,
        display_name=target_input,
        intent="start_app",
    )
    # ... 后续逻辑不变
```

#### `handle_stop_app` 方法

```python
async def handle_stop_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
    if command.requires_clarification:
        return ChatMessageResponse(
            type="text",
            content=command.clarification_question or "你想停止哪个 App？",
            session_id=session_id,
            actions=command.suggested_actions,
            requires_input=True,
        )
    
    # Phase H+ Context 消费：从 context_hints 推断 target_app
    target_input = command.target_app or "未知 App"
    params = command.parameters or {}
    context_hints = list(params.get("context_hints") or [])
    if not command.target_app and context_hints:
        for hint in context_hints:
            if hint.startswith("target_app="):
                target_input = hint.split("=", 1)[1]
                break
    
    target = self._resolve_instance_id(target_input)
    # ... 后续逻辑不变
```

## 关键文件

| 文件 | 职责 |
|------|------|
| `app/services/app_lifecycle_query_executor.py` | 生命周期查询执行器，消费 context_hints |
| `app/system/gateway/light_brain_interpreter.py` | 生成 context_hints |
| `app/services/app_command_service.py` | parameters 归一化与透传 |
| `app/services/app_presenter.py` | 响应展示（上下文摘要） |

## 对应测试

- 现有测试：`tests/unit/test_light_brain.py`（66 tests passed）
- 待补充测试：
  - `tests/unit/test_lifecycle_query_executor.py` - 生命周期场景的 context_hints 消费测试
  - 测试用例应包括：
    - 当 `command.target_app` 存在时，优先使用显式值
    - 当 `command.target_app` 缺失但 `context_hints` 包含 `target_app=` 时，正确提取
    - 当两者都缺失时，使用默认值"未知 App"
    - 多轮对话中"启动它"、"停止它"等模糊指代的正确解析

## 影响范围

修改此部分会影响：

1. **生命周期命令处理** - `app/services/app_lifecycle_query_executor.py`
2. **context_hints 生成逻辑** - `app/system/gateway/light_brain_interpreter.py`
3. **主路径测试** - `tests/unit/test_light_brain.py`
4. **待创建的测试文件** - `tests/unit/test_lifecycle_query_executor.py`

## 与 system-relationship-map.md 的关联

本文档是 `docs/system-relationship-map.md` 第 3.12 节的详细展开，补充了 Phase H context 在生命周期管理中的消费细节。

## 下一步

- [ ] 补充生命周期场景的 context_hints 消费测试
- [ ] 将 Phase H+ context 消费扩展到 pause_app / resume_app
- [ ] 完善 system-relationship-map.md 第 3.12 节
