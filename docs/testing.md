# App OS 测试文档

## 1. 测试目标

本测试文档用于验证 App OS 的核心能力是否满足需求文档，重点覆盖：
- App 持久化与生命周期
- Builder App 生成能力
- Foundation Modules 的确定性执行
- Intelligence Skills 的受控调用
- 用户/应用/系统数据隔离
- 稳定性、恢复能力和可观测性
- 大模型供应商配置可用性

---

## 2. 测试范围

### 2.1 功能测试范围
- App Draft 创建
- 需求澄清
- Blueprint 生成
- App 安装与启动
- App 修改与升级
- App 数据持久化
- Role / Task / Workflow 基本运行
- Builder App 的创建和修改能力

### 2.2 技术测试范围
- Foundation Modules 正确性
- Intelligence Skills 集成
- 模型调用配置正确性
- 失败重试与恢复
- 审计日志完整性

---

## 3. 测试环境

### 3.1 模型测试配置
以下配置用于集成测试和智能能力测试：

```toml
model_provider = "OpenAI"
model = "gpt-5.4"
review_model = "gpt-5.4"
model_reasoning_effort = "xhigh"
disable_response_storage = true
network_access = "enabled"
windows_wsl_setup_acknowledged = true
model_context_window = 1000000
model_auto_compact_token_limit = 900000

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://crs.ruinique.com"
wire_api = "openai-responses"
requires_openai_auth = true
```

### 3.2 环境要求
- 可访问外部网络
- 已正确注入 OpenAI 鉴权信息
- 支持 openai-responses wire API
- 测试环境可访问 App OS Runtime

### 3.3 鉴权与接口说明
测试环境应以环境变量方式注入鉴权信息：

```bash
export OPENAI_API_KEY="<provided-secret>"
```

注意事项：
- 不应将真实密钥硬编码进代码仓库、日志、截图或测试报告
- 测试脚本中应读取环境变量 `OPENAI_API_KEY`
- 当前主测试协议按 `wire_api = "openai-responses"` 执行
- 主测试接口应优先尝试：
  - `POST https://crs.ruinique.com/v1/responses`
- 若网关实现存在兼容差异，可追加兼容性验证：
  - `POST https://crs.ruinique.com/v1/chat/completions`
- 文档中提到的 `openai-responses` 可视为当前首选 API 后缀/协议模式

---

## 4. 测试策略

### 4.1 测试分层
建议按以下层级测试：
- Unit Test：Foundation Modules、规则与校验器
- Integration Test：Builder + Runtime + Storage + Model Provider
- End-to-End Test：用户创建 App、安装 App、运行 App、修改 App
- Regression Test：Blueprint 版本升级、运行恢复

### 4.2 大模型测试策略
大模型相关测试仅覆盖以下场景：
- requirement.clarify
- blueprint.generate
- definition.diagnose
- role.infer
- workflow.suggest

原则：
- 不用大模型测试基础模块
- 大模型测试结果应记录输入、输出、结构化字段和异常信息
- 所有大模型调用应有超时与失败兜底

---

## 5. 关键测试用例

## 5.1 App 生命周期测试

### TC-LC-001 创建 Draft
前置条件：用户存在
步骤：
1. 调用 Builder App 创建 App 草稿
2. 输入应用目标、角色、任务简要定义
预期结果：
- Draft 创建成功
- Draft 被持久化
- Draft 状态为 draft

### TC-LC-002 Draft 校验
步骤：
1. 对缺少角色或输出定义的 Draft 触发校验
预期结果：
- 返回缺失项
- 系统生成追问
- 不允许直接进入 installed

### TC-LC-003 Compile 与 Install
步骤：
1. 对完整 Draft 执行 compile
2. 执行 install
预期结果：
- 生成 Blueprint
- 生成 AppInstance
- 安装状态更新为 installed
- 分配 App 数据空间

### TC-LC-004 Start / Stop / Pause / Resume
预期结果：
- App 可正常进入 running / stopped / paused 状态
- 状态变化记录可追踪

### TC-LC-005 Upgrade / Rollback
预期结果：
- 新版本可安装
- 失败时可回滚到旧版本

---

## 5.2 Builder App 测试

### TC-BLD-001 需求澄清
步骤：
1. 输入不完整需求，如“我想做个文件同步软件”
预期结果：
- Builder 调用 requirement.clarify
- 输出角色、目标、输入输出、失败策略等追问
- 问题结构化保存

### TC-BLD-002 Blueprint 生成
步骤：
1. 提供完整需求
2. 触发 blueprint.generate
预期结果：
- 返回结构化 Blueprint
- 包含 roles/tasks/workflows/views/storage_plan

### TC-BLD-003 修改现有 App
步骤：
1. 对已安装 App 提出修改需求
预期结果：
- 生成新版本草稿
- 原版本保持可回滚

---

## 5.3 Foundation Modules 测试

### TC-FM-001 file.read
输入：有效文本文件路径
预期结果：
- 正确读取内容
- 返回 mime、size 等信息

### TC-FM-002 file.write
输入：目标路径和内容
预期结果：
- 文件写入成功
- 内容一致

### TC-FM-003 http.get
输入：有效 URL
预期结果：
- 返回状态码、响应头、body

### TC-FM-004 http.post
输入：目标 URL 和 body
预期结果：
- 正确发送请求
- 返回远端响应

### TC-FM-005 auth.check
预期结果：
- 对无权限角色返回拒绝
- 对有权限角色返回通过

---

## 5.4 Intelligence Skills 测试

### TC-IS-001 requirement.clarify
输入：模糊需求
预期结果：
- 输出缺失字段
- 输出建议提问
- 输出格式符合 schema

### TC-IS-002 blueprint.generate
输入：完整需求描述
预期结果：
- 生成结构化 Blueprint
- 不应只输出自然语言长文

### TC-IS-003 definition.diagnose
输入：存在冲突的 Blueprint
预期结果：
- 返回冲突点
- 返回修正建议

### TC-IS-004 role.infer
输入：目标和任务
预期结果：
- 推荐合理角色集合
- 标记为建议而非强制结果

---

## 5.5 数据持久化与隔离测试

### TC-DATA-001 用户数据隔离
预期结果：
- 用户 A 无法读取用户 B 的数据

### TC-DATA-002 App 数据隔离
预期结果：
- App A 无法默认访问 App B 的业务数据

### TC-DATA-003 系统元数据隐藏
预期结果：
- 普通用户不可直接看到内部 trace / secret / execution log 明细

### TC-DATA-004 Runtime State 持久化
预期结果：
- App 重启后可恢复关键运行状态或检查点

---

## 5.6 稳定性与恢复测试

### TC-REC-001 Workflow 中断恢复
步骤：
1. 在 workflow 进行中模拟异常
预期结果：
- 记录错误
- 按失败策略执行重试、补偿或人工接管

### TC-REC-002 模型调用失败兜底
步骤：
1. 模拟模型接口不可用或超时
预期结果：
- Intelligence Skill 返回受控错误
- Builder 或 Runtime 不崩溃
- 系统给出可恢复提示

### TC-REC-003 网络抖动
步骤：
1. 模拟 http.get/post 超时
预期结果：
- 模块正确报错
- 若配置了重试则按策略执行

---

## 5.7 审计与观测测试

### TC-OBS-001 App 生命周期日志
预期结果：
- create/install/start/stop/update 均有审计记录

### TC-OBS-002 Workflow Trace
预期结果：
- 每次执行都可追踪到 workflow run id、步骤、结果、耗时

### TC-OBS-003 Intelligence Skill 调用日志
预期结果：
- 记录模型、provider、耗时、结果状态、错误信息

---

## 6. 模型供应商联通性测试

### TC-MODEL-001 基础连通性（Responses API）
目标：验证 OpenAI provider 配置可用
接口：
- `POST https://crs.ruinique.com/v1/responses`
检查项：
- base_url 可访问
- wire_api 为 openai-responses
- 鉴权存在
- 请求可正常返回响应
- 返回内容可被解析

建议最小请求体：
```json
{
  "model": "gpt-5.4",
  "input": "hello"
}
```

### TC-MODEL-002 模型能力验证
目标：验证 gpt-5.4 可用于 requirement.clarify / blueprint.generate
接口：
- `POST https://crs.ruinique.com/v1/responses`
预期结果：
- 能输出结构化内容
- 支持较高 reasoning effort
- 在给定上下文窗口限制内运行正常
- 对需求澄清与蓝图生成类任务有可用输出

### TC-MODEL-003 Review 模型一致性
目标：验证 review_model = gpt-5.4 配置正常
接口：
- `POST https://crs.ruinique.com/v1/responses`
预期结果：
- 可用于定义审阅与诊断任务

### TC-MODEL-004 Chat Completions 兼容性回退测试（可选）
目标：当网关对 Responses API 存在兼容差异时，验证是否支持兼容回退
接口：
- `POST https://crs.ruinique.com/v1/chat/completions`
预期结果：
- 若支持，则记录为兼容回退路径
- 若不支持，不影响主测试结论
- 主路径仍应以 `/v1/responses` 为准

### TC-MODEL-005 鉴权安全测试
目标：验证测试脚本通过环境变量读取鉴权信息，而不是硬编码密钥
检查项：
- 脚本从 `OPENAI_API_KEY` 读取凭证
- 日志中不回显完整密钥
- 报告中不落盘真实密钥

---

## 7. 验收标准

项目首期验收通过标准：
- 能创建、编译、安装并运行至少 1 个 App
- Builder App 能引导用户生成一个结构化 App Blueprint
- Foundation Modules 基础能力测试全部通过
- 至少 3 个 Intelligence Skills 可正常调用并返回结构化结果
- 用户数据 / App 数据 / 系统数据隔离验证通过
- 生命周期、日志、审计、恢复关键路径可用
- 模型供应商配置验证通过

---

## 8. 后续扩展测试建议

后续建议增加：
- 压力测试
- 多用户并发测试
- 长周期 App 稳定性测试
- Blueprint 升级兼容性测试
- 多版本迁移测试
- 权限越权攻击测试


## 6. Requirement Router 测试

### TC-RTR-001 App 需求分类
预期结果：输出 `requirement_type=app`，并给出 `optional` 或更明确的示范建议。

### TC-RTR-002 Skill 需求分类
预期结果：输出 `requirement_type=skill`，且默认优先直接生成而非先示范。

### TC-RTR-003 示范优先判断
预期结果：当输入明显包含页面点击、演示、示范等信号时，输出 `demonstration_decision=required`。

### TC-RTR-004 抽象需求澄清
预期结果：对战略、长期规划等抽象目标输出 `clarify`，而不是误判为可直接示范。


## 7. Skill Control Interface 测试

### TC-SCI-001 列出 Skill
预期结果：能够读取系统当前登记的 skill 列表与当前激活版本。

### TC-SCI-002 替换 Skill
预期结果：对可变 skill 替换后，active_version 更新为新版本。

### TC-SCI-003 回退 Skill
预期结果：可切换回指定历史版本，并保留回退状态记录。

### TC-SCI-004 禁用 / 启用 Skill
预期结果：技能可被人工禁用并重新启用。

### TC-SCI-005 保护不可变接口
预期结果：对 immutable skill 的替换或修改请求被拒绝。
