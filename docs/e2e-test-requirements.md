# 端到端测试需求文档 — 用户交互 → 系统执行全链路

> 2026-04-14 · 覆盖从用户输入到系统执行的完整指令链
> 目标：发现链路断裂、设计不合理、权限漏洞、状态丢失等问题

---

## 链路全景图

```
用户 (QQ/Web)
  ↓
POST /chat/message (FastAPI)
  ↓
LightBrainGateway.process_message()
  ├── 1. 会话管理 → LightBrainMemory
  ├── 2. 记录消息 → record_user_message()
  ├── 3. 多轮续对话检查 → _handle_active_skill_continuation()
  ├── 4. 获取可用 App → _get_available_apps()
  ├── 5. 意图解析 → LightBrainInterpreter.interpret()
  │     ├── 规则匹配（内置 handler）
  │     └── LLM 意图分析（_llm_responder）
  ├── 6. 命令执行 → _execute_command()
  │     ├── G.1/G.2 新链路：GatewayOrchestratorBridge → AppOrchestrator → MessageBus
  │     └── 传统链路：直接 handler (_handle_create_app, _handle_start_app, ...)
  ├── 7. LLM 增强回复 → _llm_responder.generate_reply()
  └── 8. 持久化 → _auto_save()
```

---

## 关键子链路

### A. App 创建链路
```
用户: "帮我建一个小说 App"
  → interpret → create_app
  → _handle_create_app → _execute_create_app
  → MetaAppCreationOrchestrator.create_app_through_meta_app()
  → SkillFactory → 生成 skill 代码
  → AppInstaller → 安装 App
  → AppRegistry → 注册
  → 权限检查: 新 skill 需要 admin?
  → PersistenceService.save_state()
  → 返回 ChatMessageResponse
```

### B. App 修改链路
```
用户: "给小说 App 加个插画功能"
  → interpret → modify_app
  → _handle_modify_app (Phase 1: 确认框)
  → 用户确认 → _execute_modify_app
  → 权限检查: user role >= app owner role?
  → Dry-run 分析: 需要哪些新 skill?
  → 需要新 skill + 非 admin → 拦截
  → AppRefinementOrchestrator.refine_closure()
  → 生成 skill → 安装 → 更新 App 状态
```

### C. App 生命周期链路
```
用户: "启动小说 App"
  → interpret → start_app
  → _handle_start_app
  → RuntimeHost.start(app_id)
  → Lifecycle 状态更新
```

### D. 多轮对话链路
```
用户: "帮我建个 App"
  → interpret → create_app (需要更多信息)
  → reply.requires_input = True
  → _set_active_skill(session_id, "create_app", state)
  → 用户: "写小说的"
  → _handle_active_skill_continuation()
  → 路由到 create_app handler 带上下文
```

### E. 资产表链路 (新增)
```
App 启动 → AssetRegistry.register(asset)
Skill 启动 → AssetRegistry.register(skill)
用户请求 → get_visible_assets(caller_name)
  → 组装概览注入 Prompt
  → LLM 选择 → query_asset_detail → 路由执行
```

---

## 测试需求清单

### 第一类：用户交互层 (E2E-UI-001 ~ 010)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-UI-001 | 用户首次对话，发 "你好" | 返回自我介绍 + 能力列表 + 示例指令 | _handle_greet 是否正确读取 identity |
| E2E-UI-002 | 用户说 "帮我建一个小说 App" | 进入创建流程，可能追问细节或创建确认 | create_app 是否需要多轮交互 |
| E2E-UI-003 | 用户说 "看看我的 App" | 返回 App 列表，按状态分组，带操作按钮 | list_apps 是否正确读取 lifecycle |
| E2E-UI-004 | 用户说 "启动小说 App" | 尝试启动，返回成功/失败 | runtime_host.start 是否正确路由 |
| E2E-UI-005 | 用户说 "系统状态" | 返回 App 总数、运行数 | query_status 数据源是否正确 |
| E2E-UI-006 | 用户发送模糊指令 "那个啥" | 返回澄清问题 + 建议操作 | interpreter 是否正确识别 requires_clarification |
| E2E-UI-007 | 用户点击确认按钮 (execute_action) | 执行对应操作，如确认创建 App | execute_action 是否正确重建 command |
| E2E-UI-008 | 用户说 "帮助" | 返回帮助文档 + 示例 | _handle_query_help 内容是否完整 |
| E2E-UI-009 | 用户发送超长消息 (>4000 字) | 不崩溃，正常处理或截断 | 消息长度限制是否合理 |
| E2E-UI-010 | 用户快速连续发送多条消息 | 不丢失消息，按序处理 | 并发安全、session 锁 |

### 第二类：App 创建全链路 (E2E-CREATE-001 ~ 010)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-CREATE-001 | 普通用户创建简单 App (只用已有 skill) | 创建成功，App 注册并安装 | MetaApp orchestrator 是否正确组装 |
| E2E-CREATE-002 | 普通用户创建需要新 skill 的 App | 被拦截，提示需要管理员 | 权限检查是否在 skill 创建前拦截 |
| E2E-CREATE-003 | 管理员创建需要新 skill 的 App | 创建成功，新 skill 生成并安装 | SkillFactory 是否正确生成代码 |
| E2E-CREATE-004 | 创建 App 后查看列表 | 新 App 出现在列表中 | AppRegistry 是否正确注册 |
| E2E-CREATE-005 | 创建 App 后重启服务 | App 仍然存在（持久化） | PersistenceService.save_state |
| E2E-CREATE-006 | 创建同名 App | 冲突处理（拒绝 or 覆盖） | AppRegistry 是否有去重逻辑 |
| E2E-CREATE-007 | 创建 App 时 MetaApp orchestrator 不可用 | 降级为确认卡片，不崩溃 | Fallback 机制是否健全 |
| E2E-CREATE-008 | 创建 App 过程中 SkillFactory 失败 | 返回错误信息，不产生半安装状态 | 事务性 / 回滚机制 |
| E2E-CREATE-009 | 用户通过多轮对话逐步提供 App 信息 | 信息逐步累积，最终创建 | 多轮 state 是否正确维护 |
| E2E-CREATE-010 | 创建 App 后立即启动 | 启动成功 | lifecycle 状态机是否正确 |

### 第三类：App 修改全链路 (E2E-MODIFY-001 ~ 010)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-MODIFY-001 | 用户修改自己的 App (不需要新 skill) | 修改成功 | _check_app_modify_permission |
| E2E-MODIFY-002 | 用户修改别人的 App | 被拦截 | 权限检查: user level >= owner level |
| E2E-MODIFY-003 | 普通用户修改 App 需要新 skill | 被拦截 + 提示 | dry-run 分析 + 权限门控 |
| E2E-MODIFY-004 | 管理员修改 App 需要新 skill | 修改成功 | refine_closure 正确执行 |
| E2E-MODIFY-005 | 修改 App 后执行 | 新功能可用 | skill 安装后 App 状态更新 |
| E2E-MODIFY-006 | 修改确认 → 用户取消 | 不执行修改 | 确认框的 cancel action |
| E2E-MODIFY-007 | 修改确认 → 用户确认 → refinement orchestrator 不可用 | 返回友好提示 | 降级处理 |
| E2E-MODIFY-008 | 修改 App 后重启服务 | 修改保留 | 持久化 |
| E2E-MODIFY-009 | 连续修改同一 App 多次 | 每次修改正确叠加 | App 版本管理 |
| E2E-MODIFY-010 | 修改 App 删除某个 skill | skill 从 App 中移除 | skill 卸载逻辑 |

### 第四类：App 生命周期 (E2E-LIFECYCLE-001 ~ 008)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-LIFECYCLE-001 | 启动已安装的 App | 状态变为 running | runtime_host.start |
| E2E-LIFECYCLE-002 | 停止运行中的 App | 状态变为 stopped | runtime_host.stop |
| E2E-LIFECYCLE-003 | 暂停运行中的 App | 状态变为 paused | lifecycle pause |
| E2E-LIFECYCLE-004 | 恢复暂停的 App | 状态变为 running | lifecycle resume |
| E2E-LIFECYCLE-005 | 删除运行中的 App | 先停止再删除 | 级联清理 |
| E2E-LIFECYCLE-006 | 启动不存在的 App | 返回错误提示 | 异常处理 |
| E2E-LIFECYCLE-007 | 查看 App 详情 | 返回状态、描述、ID | query_app 数据准确性 |
| E2E-LIFECYCLE-008 | App 状态转换合法性 | running↔stopped↔paused 合法转换 | 状态机校验 |

### 第五类：多轮对话与状态 (E2E-MULTITURN-001 ~ 008)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-MULTITURN-001 | 创建 App 过程中用户补充信息 | active skill 状态正确累积 | _set_active_skill / _get_active_skill |
| E2E-MULTITURN-002 | 多轮后用户发送不相关消息 | 清除 active skill，重新意图分析 | _clear_active_skill 时机 |
| E2E-MULTITURN-003 | 会话切换 | 不同会话的 active skill 独立 | session_id 隔离 |
| E2E-MULTITURN-004 | 重启服务后加载历史会话 | 会话记录保留，active skill 可恢复 | persistence 加载 active_skills |
| E2E-MULTITURN-005 | 用户通过按钮执行操作 | execute_action 正确路由 | action_id → intent 映射 |
| E2E-MULTITURN-006 | 按钮操作丢失 last_command (页面刷新) | 从 action_params 重建 command | execute_action 的 fallback |
| E2E-MULTITURN-007 | 长对话 (>50 轮) | 不丢失消息，不崩溃 | memory 容量管理 |
| E2E-MULTITURN-008 | 同一用户多个并发会话 | 会话隔离 | session 并发安全 |

### 第六类：权限与安全 (E2E-PERMISSION-001 ~ 008)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-PERMISSION-001 | 普通用户修改别人的 App | 被拒绝 | _check_app_modify_permission |
| E2E-PERMISSION-002 | 普通用户创建需新 skill 的 App | 被拒绝 + 提示 | can_create_skills 检查 |
| E2E-PERMISSION-003 | 管理员创建需新 skill 的 App | 允许 | admin role_level = 1 |
| E2E-PERMISSION-004 | root 用户修改任何 App | 允许 | root role_level = 2 |
| E2E-PERMISSION-005 | 用户查询自己权限 | 返回正确权限信息 | show_permissions handler |
| E2E-PERMISSION-006 | 用户查看他人 App | 是否可见？(当前实现) | 可见性规则 |
| E2E-PERMISSION-007 | 越权 API 直接调用 | 是否有 API 层鉴权？ | FastAPI 中间件 |
| E2E-PERMISSION-008 | 用户删除自己的 App | 允许 | delete_app 权限 |

### 第七类：资产表集成 (E2E-ASSET-001 ~ 008)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-ASSET-001 | App 启动时自动注册到资产表 | register() 被调用 | 生命周期钩子是否接入 |
| E2E-ASSET-002 | Skill 启动时注册到拥有者表 | owner_id 正确 | App vs User 拥有者 |
| E2E-ASSET-003 | 用户请求 → 获取可见资产 | get_visible_assets 正确过滤 | 系统/用户/App 视图 |
| E2E-ASSET-004 | LLM prompt 注入资产概览 | assemble_asset_overview_prompt 正确 | prompt 格式 |
| E2E-ASSET-005 | LLM 查询资产详情 → 路由执行 | query_asset_detail + execute_path_by_key | 工具执行器 |
| E2E-ASSET-006 | App 停止 → 级联注销 skill | unregister 级联清理 | cascade unregister |
| E2E-ASSET-007 | 用户 A 看不到用户 B 的私有资产 | 可见性隔离 | _get_user_view |
| E2E-ASSET-008 | 共享资产被目标用户看到 | USER_SHARED 逻辑 | shared_with 列表 |

### 第八类：持久化与恢复 (E2E-PERSIST-001 ~ 006)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-PERSIST-001 | 创建 App 后重启 | App 仍然存在 | save_state / load_state |
| E2E-PERSIST-002 | 多轮对话中途重启 | 会话记录保留 | memory 持久化 |
| E2E-PERSIST-003 | 修改 App 后重启 | 修改保留 | refinement 持久化 |
| E2E-PERSIST-004 | 运行时状态重启恢复 | runtime_host 恢复实例状态 | RuntimeStateStore |
| E2E-PERSIST-005 | 活跃 skill 状态重启恢复 | active_skills 恢复 | persistence 包含 active_skills? |
| E2E-PERSIST-006 | 持久化失败不影响正常操作 | 降级处理 | _auto_save 的 try/except |

### 第九类：异常与降级 (E2E-ERROR-001 ~ 008)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-ERROR-001 | LLM 服务不可用 | 降级为规则引擎，不崩溃 | llm_responder.available 检查 |
| E2E-ERROR-002 | MetaApp orchestrator 不可用 | 降级为确认卡片 | _execute_create_app fallback |
| E2E-ERROR-003 | Refinement orchestrator 不可用 | 友好提示 | _execute_modify_app fallback |
| E2E-ERROR-004 | Runtime host 不可用 | 提示服务未启动 | runtime_host null check |
| E2E-ERROR-005 | 数据库/文件写入失败 | 不崩溃，记录日志 | persistence try/except |
| E2E-ERROR-006 | 消息解析异常 | 返回友好错误 | process_message try/except |
| E2E-ERROR-007 | Bridge 执行异常 | 降级到传统 handler | _execute_command bridge fallback |
| E2E-ERROR-008 | 资产表查询异常 | 不阻断正常流程 | asset registry error handling |

### 第十类：复杂场景组合 (E2E-COMPLEX-001 ~ 010)

| ID | 场景 | 预期 | 风险点 |
|----|------|------|--------|
| E2E-COMPLEX-001 | 创建 App → 启动 → 执行 → 修改 → 再执行 | 全链路打通 | 各子系统协同 |
| E2E-COMPLEX-002 | 用户 A 创建 App → 用户 B 尝试修改 → 被拒 → 用户 A 修改 → 成功 | 权限隔离 | 多用户场景 |
| E2E-COMPLEX-003 | 创建 App → 重启 → 查看列表 → 启动 → 执行 | 持久化 + 恢复 | 重启后全链路 |
| E2E-COMPLEX-004 | 多轮创建 App → 中途取消 → 重新开始创建 | 状态清理 | cancel action |
| E2E-COMPLEX-005 | 用户连续创建 3 个不同 App → 查看列表 | 全部出现 | 并发创建 |
| E2E-COMPLEX-006 | 修改 App 需要新 skill → admin 批准 → 执行 | 跨用户协作 | 权限 + 审批流 |
| E2E-COMPLEX-007 | App 运行中修改 → 热更新 or 需重启 | 修改后的执行行为 | 运行时更新 |
| E2E-COMPLEX-008 | 用户通过 Web 创建 → 通过 QQ 查看 | 跨渠道会话一致 | channel 隔离 |
| E2E-COMPLEX-009 | 创建 App → 固化流程 → 执行固化流程 | 资产表 + Path 执行 | solidify → execute |
| E2E-COMPLEX-010 | 全系统压力测试：10 用户各创建 2 个 App + 修改 + 执行 | 系统稳定 | 并发 + 资源 |

---

## 测试实施优先级

### P0 (立即实施) — 核心链路
- E2E-CREATE-001/002/003: 创建 App 权限门控
- E2E-MODIFY-001/002/003/004: 修改 App 权限 + dry-run
- E2E-LIFECYCLE-001/002: 启动/停止
- E2E-PERSIST-001: 创建后重启
- E2E-ERROR-001/002/007: 降级处理

### P1 (高优先级) — 多轮 + 资产表
- E2E-MULTITURN-001/002/005/006: 多轮对话 + 按钮操作
- E2E-ASSET-001/002/003/006: 资产注册/可见性/级联
- E2E-PERMISSION-001/002/003/004: 权限矩阵
- E2E-COMPLEX-001: 创建→启动→执行→修改→再执行

### P2 (中优先级) — 复杂场景
- E2E-COMPLEX-002/003/004/006/009
- E2E-PERSIST-002/003/004/005
- E2E-ERROR-003/004/005/006/008

### P3 (低优先级) — 边缘情况
- E2E-UI-009/010: 超长消息 + 并发
- E2E-MULTITURN-007/008: 长对话 + 并发会话
- E2E-COMPLEX-005/007/008/010: 压力测试

---

## 需要 mock 的外部依赖

1. **LLM Responder**: mock `generate_reply()` 返回预设回复
2. **Runtime Host**: mock `start()` / `stop()` / `get_instance()`
3. **MetaApp Orchestrator**: mock `create_app_through_meta_app()` 返回预设结果
4. **Refinement Orchestrator**: mock `refine_closure()` 返回预设 skill 列表
5. **Persistence**: mock `save_state()` / `load_state()`
6. **Skill Factory**: mock skill 生成，返回测试 skill 代码

---

## 测试框架要求

- 使用 pytest + pytest-asyncio
- 每个测试独立初始化 `LightBrainGateway` + 所有依赖服务
- 支持同步和异步测试
- 测试结果输出详细的链路追踪信息
- 支持测试覆盖率报告
