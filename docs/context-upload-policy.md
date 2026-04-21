# Context Upload Policy (上下文上传策略)

> **Phase H+ 固化项**：Context upload 白名单与 system note 模板  
> **生效日期**：2026-04-22  
> **适用范围**：所有正式 turn 结束后的上下文沉淀

---

## 1. 设计原则

上下文是**给后续交互用的正式记录**，不是把完整执行流水倒进去的容器。

- **正式性**：上下文是交互历史的一部分，必须简洁、可续读
- **最小性**：只保留后续交互理解需要的正式记录
- **结构化**：system note 只能作为结构化附加索引，不替代原始消息

---

## 2. Upload 白名单

### 2.1 允许上传的内容类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `user_message` | 用户原始消息 | `"帮我创建一个记账 App"` |
| `assistant_reply` | assistant 最终回复 | `"好的，正在为你创建记账 App..."` |
| `dispatch_decision` | 最终 dispatch decision | `{"intent": "create_app", "target_app": "记账"}` |
| `structured_result` | 最终结构化结果 | `{"app_id": "xxx", "status": "created"}` |
| `system_note` | 极短的 system note（见第 3 节） | `{"type": "app_created", "actor": "app_mgmt"}` |

### 2.2 禁止上传的内容类型

| 类型 | 原因 |
|------|------|
| `scratchpad` | 中间思考过程，非正式记录 |
| `chain_of_thought` | 推理链，非交互必要内容 |
| `full_tool_trace` | 全量工具调用流水，应查日志 |
| `failed_attempts` | 中间失败尝试，污染上下文 |
| `long_freeform_summary` | 长篇自由文本总结，应结构化 |

---

## 3. System Note 模板

### 3.1 最小字段结构

```json
{
  "type": "string (必填)",
  "actor": "string (必填)",
  "resolved_session_id": "string (可选)",
  "decision": "string (可选)",
  "outcome": "string (可选)",
  "pending": "boolean (可选)"
}
```

### 3.2 常用 type 枚举

| type | 说明 | 使用场景 |
|------|------|----------|
| `intent_dispatch` | 意图分发记录 | 交互层决策后 |
| `app_created` | App 创建完成 | `create_app` 成功后 |
| `app_modified` | App 修改完成 | `modify_app` 成功后 |
| `app_query` | App 查询记录 | `query_app` 执行后 |
| `lifecycle_change` | 生命周期变更 | 启动/停止/暂停/恢复 |
| `child_session_forked` | 子会话创建 | 创建 child session 时 |
| `clarification_required` | 需要澄清 | 意图不明确时 |

### 3.3 使用示例

```json
// App 创建成功
{
  "type": "app_created",
  "actor": "app_mgmt",
  "resolved_session_id": "sess-abc123",
  "outcome": "success"
}

// 需要澄清
{
  "type": "clarification_required",
  "actor": "interaction",
  "pending": true
}

// 子会话创建
{
  "type": "child_session_forked",
  "actor": "orchestration",
  "resolved_session_id": "sess-abc123.orch.modify_app"
}
```

---

## 4. ContextCenter 写入规范

### 4.1 写入时机

- **用户消息进入后** → 立即写入 `user_message`
- **Assistant 回复后** → 立即写入 `assistant_reply`
- **Turn 结束后** → 可选写入 `system_note`（如需要索引）

### 4.2 写入接口

```python
# ContextCenter 接口
context_center.append_context_record(
    session_id="sess-abc123",
    record=SessionContextRecord(
        session_id="sess-abc123",
        kind="message",  # 或 "system_note"
        role="user",     # 或 "assistant", "system"
        content="用户原始消息",
        metadata={}      # 可选的结构化元数据
    )
)
```

### 4.3 长度限制

| 类型 | 最大长度 | 超出处理 |
|------|---------|---------|
| `user_message` | 10,000 chars | 截断 + `"..."` |
| `assistant_reply` | 10,000 chars | 截断 + `"..."` |
| `system_note` | 500 chars | 拒绝写入 |

---

## 5. 日志 vs 上下文 分层

| 维度 | 日志 | 上下文 |
|------|------|--------|
| **目的** | 调试/审计/排障 | 交互理解 |
| **内容** | 详细流水、错误细节 | 正式记录 |
| **分级** | 支持 (INFO/WARN/ERROR) | 不支持 |
| **可查询性** | 支持复杂查询 | 仅支持 session/区间查询 |
| **保留策略** | 长期保存 | 最近窗口优先 |

**硬约束**：
- 日志不能直接冒充上下文
- 上下文不能被调试流水污染
- 想看完整执行链就查日志，不是查 ContextCenter 正文

---

## 6. 实施检查清单

在代码审查时检查：

- [ ] 是否只上传了白名单内的内容类型
- [ ] system note 是否符合最小字段结构
- [ ] 是否避免了 scratchpad/CoT 上传
- [ ] system note 长度是否 < 500 chars
- [ ] 日志和上下文是否分层清晰

---

## 7. 相关文档

- `tasklist_phase_h.md` - Phase H 执行设计
- `docs/phase-h-execution-design.md` - Phase H 架构说明
- `app/models/context.py` - SessionContextRecord 模型定义
- `app/services/context_center.py` - ContextCenter 实现

---

**维护规则**：任何对 context upload 行为的修改（新增/删除白名单类型、修改 system note 模板）都必须同步更新本文件。
