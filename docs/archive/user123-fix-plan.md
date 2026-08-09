# 用户123交互问题改造方案

## 背景

用户123的108次交互记录中暴露三类高频失败：
- 22次 `null` 回复（ModelClientError 无容错）
- 14次 `[Reached max turns (6)]`（TurnBudget 太低）
- 同一问题反复失败（memory_context 丢失 + 无收敛机制）

## 根因链路

```
http_test_server.py                    light_brain_gateway.py
─────────────────────                 ──────────────────────
构建 memory_context ✅                 receive_message()
    │                                      │
    ├─ 会话事实板（姓王/辰时/闺女）        ├─ request.memory_context ❌ 从未读取
    ├─ 最近历史摘要                        ├─ _append_context_record() ← 没写 memory_context
    └─ style hint                         ├─ _enrich_command() ← 注入12个字段，不含 memory_context
          │                               │
          └──→ ChatMessageRequest ───────→│
                                         ├─ _execute_command()
                                         │   └─ ModelClientError → 直接向上抛 ❌ 无 catch
                                         │
                                         └─ 返回 null 给用户 ❌

model_client.py / tool_calling_engine.py
───────────────────────────────────────
TurnBudgetPolicy.CHAT = 6 ❌
    → 工具类对话需要 8~15 轮，超了直接 [Reached max turns (6)]
    → 无收敛提示，模型不知道该停
```

## 改造项

### Phase 1：TurnBudget + 收敛提示（已完成 ✅）

| 文件 | 改动 | 状态 |
|------|------|------|
| `app/services/turn_budget_policy.py` | HARD_CAP 50→200, CHAT 6→50, EXECUTION 15→80, ENGINEERING 30→120, BACKGROUND 50→200, 新增 CONVERGENCE_HINT_TURN=50 | ✅ |
| `app/ai/model_client.py` | turn==50 时注入系统收敛提示 | ✅ |
| `app/ai/tool_calling_engine.py` | 同上 | ✅ |

### Phase 2：memory_context 注入链路（待改）

**Task 2.1：`light_brain_gateway.py` — receive_message() 中注入 memory_context**

位置：`receive_message()` 中，`_append_context_record(user message)` 之后

```python
# 在已有 _append_context_record(user message) 之后
if request.memory_context:
    self._append_context_record(
        session_id=session_id,
        role="system",
        content=f"[跨会话上下文]\n{request.memory_context}",
        kind="memory_context",
    )
```

效果：用户123之前说的"姓王"、"辰时"等事实进入 ContextCenter，interpreter 通过 `_enrich_command()` 的 `recent_session_context` 可以读到。

**Task 2.2：验证 _enrich_command 的 recent_session_context 能读到 memory_context**

确认 ContextCenter.get_recent_context() 返回的记录包含 kind="memory_context" 的条目。如有问题需调整 limit 或过滤逻辑。

### Phase 3：ModelClientError 容错（待改）

**Task 3.1：`light_brain_gateway.py` — _execute_command() 外层 catch**

位置：`receive_message()` 中 `_execute_command()` 调用处

```python
# 改前
result = await self._execute_command(command, session_id, available_apps)

# 改后
try:
    result = await self._execute_command(command, session_id, available_apps)
except ModelClientError as e:
    logger.error("Model call failed: session=%s error=%s", session_id, e)
    result = ChatMessageResponse(
        type="text",
        content=f"系统暂时无法处理这个请求，请稍后重试。({str(e)[:80]})",
        session_id=session_id,
    )
except Exception as e:
    logger.error("Unexpected error in _execute_command: session=%s error=%s", session_id, e, exc_info=True)
    result = ChatMessageResponse(
        type="text",
        content="系统内部错误，请稍后重试。",
        session_id=session_id,
    )
```

**Task 3.2：`http_test_server.py` — api_chat() 异常处理美化**

当前 api_chat() 的 except 块返回 `{success: False, error: ...}`，前端可能直接显示 JSON。

```python
# 改 except 块中的 visible_error 生成逻辑
visible_error = f"系统暂时无法处理这个请求，请稍后重试。({error_type})"
```

确保 response 格式与正常回复一致（包含 content 字段）。

### Phase 4：端到端验证

**Task 4.1：用户123典型场景回归**

用 user-123-full-interaction-2026-05-03.md 中的失败场景测试：

| 场景 | 预期结果 |
|------|---------|
| "姓王" + "辰时"（连续补参数） | 不再重复追问已说过的事实 |
| "调用工具查找你的源码仓库位置" | 能完成，不再 [Reached max turns] |
| "看下你上下文中心的代码" | 能完成或给出阶段性成果 |
| 模拟 ModelClientError | 返回友好提示，不返回 null |

**Task 4.2：TurnBudget 收敛验证**

构造需要 50+ 轮工具调用的任务，验证 turn==50 时注入收敛提示，模型停止调用并输出阶段性成果。

---

## 改动文件清单

| 文件 | 改动内容 | 风险 |
|------|---------|------|
| `app/services/turn_budget_policy.py` | 已改 ✅ | 低 |
| `app/ai/model_client.py` | 已改 ✅ | 低 |
| `app/ai/tool_calling_engine.py` | 已改 ✅ | 低 |
| `app/system/gateway/light_brain_gateway.py` | Task 2.1 + Task 3.1 | 中 |
| `app/system/http_test_server.py` | Task 3.2 | 低 |

## 实施顺序

```
Phase 1 ✅ → Phase 2 → Phase 3 → Phase 4
(TurnBudget)   (memory)    (容错)     (验证)
```

## 不改的（明确排除）

- 不降级回复（会驴头不对马嘴）
- 不分 CHAT / CHAT_WITH_TOOLS（误判风险）
- 不做同题反复检测（靠 Phase 2+3 自然解决）
