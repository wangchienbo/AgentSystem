# Phase E: 混合意图解析 + Tool Calling 架构

## 设计原则
1. **离线优先**: 明显意图（正则匹配）直接执行，不依赖 LLM
2. **LLM 优先**: 可用 LLM 时，优先让 LLM 解析意图并选择工具
3. **工具感知**: LLM 必须知道所有可执行单元（handler + skill）
4. **统一接口**: 所有可执行单元注册为 Tool，统一调用方式

## 当前架构问题

```
当前: 用户 → 正则解析 → Handler 执行 → LLM润色文字 → 回复
问题: LLM 不知道工具存在，只负责"润色"
```

```
理想: 用户 → 正则快路径(离线) → 执行 → 回复
          ↓ (正则不匹配 + LLM可用)
      LLM(知道所有工具) → 选择工具 → 执行 → 结果给LLM → 回复
```

## 可执行单元清单

### A. Gateway Handlers (20个意图 → 14个处理函数)
- App CRUD: create/start/stop/pause/resume/query/modify/delete
- 系统: list_apps, query_status, query_help, greet
- 交互App: modify_interactive_app, self_modify
- 权限: grant_admin/grant_root/revoke_role/show_permissions/list_users/show_self

### B. System Skills (6个技能)
- memory: 用户记忆/偏好管理
- permission: 权限命令解析与执行
- app_config: App 配置快照/历史
- context: 上下文压缩/管理
- maoxuan: 决策分析/心智模型
- state_audit: 系统审计/记录

### C. Pipeline Executors (4种)
- ShellExecutor, PythonExecutor, LLMExecutor, APIExecutor

## 实现方案

### E.1: 工具注册表 (Tool Registry)
- 定义 Tool 数据结构: name, description, parameters, handler
- 所有 Gateway Handler 注册为 Tool
- System Skills 注册为 Tool
- 支持动态注册/注销

### E.2: 混合意图解析器
- 阶段1: 正则匹配 → 直接执行 (离线路径)
- 阶段2: 正则不匹配 + LLM可用 → LLM 选择工具
- 阶段3: 执行选中的工具 → 获取结果
- 阶段4: 结果给 LLM 生成最终回复

### E.3: LLM Tool Calling
- 使用 OpenAI function calling 格式
- 系统提示词包含完整工具列表 + 当前状态
- 支持多步工具调用 (ReAct 循环)

### E.4: 回复生成
- 工具执行结果 → 注入 LLM 上下文
- LLM 生成自然语言回复
- 保留结构化回复 (type, actions)

## 文件变更
- 新建: app/services/tool_registry.py
- 修改: app/services/light_brain_interpreter.py
- 修改: app/services/llm_responder.py
- 修改: app/services/light_brain_gateway.py
- 修改: app/models/chat.py (可能需要 ToolCall 模型)
