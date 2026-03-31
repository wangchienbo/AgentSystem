# App OS 详细测试文档

## 1. 文档信息

- 项目名称：AgentSystem / App OS
- 代码仓库：https://github.com/wangchienbo/AgentSystem
- 关联文档：
  - `README.md`
  - `DESIGN.md`
  - `TESTING.md`

---

## 2. 测试目标

本测试文档面向实现阶段，覆盖：
- 系统级行为
- App 生命周期
- Builder App
- 数据持久化和隔离
- Foundation Modules
- Intelligence Skills
- 模型供应商连通性
- 稳定性与恢复

---

## 3. 测试分层

### 3.1 单元测试
目标：验证 Foundation Modules、policy、schema validator。

### 3.2 集成测试
目标：验证 Builder、Runtime、Storage、Model Provider 联动。

### 3.3 端到端测试
目标：从“用户创建 App”到“App 安装并运行”全链路验证。

### 3.4 回归测试
目标：验证版本升级、回滚、诊断、持久化兼容性。

---

## 4. 模型测试配置

测试环境采用以下模型配置：

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

鉴权要求：
- 通过环境变量 `OPENAI_API_KEY` 注入
- 不将真实密钥写入仓库、日志或测试报告

主测试接口：
- `POST https://crs.ruinique.com/v1/responses`

兼容回退接口（可选）：
- `POST https://crs.ruinique.com/v1/chat/completions`

当前仓库内现有测试入口：
- `scripts/model_probe.py`：最小外部连通性探针
- `tests/e2e/test_external_model_api_flow.py`：通过内置 skill runtime 验证外部模型 API 流程
- `tests/unit/test_model_client_smoke.py`：客户端级 smoke tests，覆盖 JSON / SSE / 5xx 错误映射

---

## 5. 系统级测试

### SYS-001 App Registry 基本行为
验证：
- 能注册 App Blueprint
- 能创建 AppInstance
- 能查询已安装 App 列表

### SYS-002 Lifecycle 管理
验证：
- draft → compiled → installed → running
- running → paused → running
- running → upgrading → rollback

### SYS-003 Builder App 可用性
验证：
- Builder 能创建其他 App
- Builder 能修改其他 App
- Builder 的历史记录可追溯

### SYS-004 数据分层
验证：
- 用户数据、App 数据、系统元数据分开存储和访问

---

## 6. App 生命周期测试用例

### LC-001 创建 Draft
输入：一个最小 App 描述
期望：
- Draft 创建成功
- 状态为 draft
- 可继续编辑

### LC-002 Draft 校验失败
输入：缺失角色和输出定义的 Draft
期望：
- 返回缺失项
- Builder 发起补问
- 不可安装

### LC-003 编译成功
输入：完整 Draft
期望：
- 生成 Blueprint
- Blueprint 含 roles/tasks/views/workflows/storage_plan

### LC-004 安装成功
期望：
- 生成 AppInstance
- 分配数据命名空间
- 记录安装日志

### LC-005 运行成功
期望：
- App 进入 running
- 可触发 workflow

### LC-006 升级与回滚
期望：
- 新版本可安装
- 升级失败可恢复原版本

---

## 7. Builder App 测试用例

### BLD-001 requirement.clarify
输入："我想做个文件同步软件"
期望：
- 输出结构化缺失项
- 提问包含角色、输入源、输出目标、失败策略

### BLD-002 blueprint.generate
输入：完整需求
期望：
- 输出结构化 Blueprint
- 字段包含 roles/tasks/interactions/views/workflows

### BLD-003 definition.diagnose
输入：存在角色权限冲突的 Blueprint
期望：
- 输出冲突点
- 输出修正建议

### BLD-004 修改 App
输入：对已安装 App 发起变更
期望：
- 生成新版本 Draft
- 原版本保留

---

## 8. Foundation Modules 测试用例

### FM-001 file.read
期望：正确读取文本文件并返回元信息

### FM-002 file.write
期望：正确写入并校验内容一致

### FM-003 file.list
期望：正确列出目录项

### FM-004 http.get
期望：返回状态码、头、响应体

### FM-005 http.post
期望：成功提交数据并收到响应

### FM-006 state.get/state.set
期望：状态可写可读

### FM-007 auth.check
期望：权限正确判定

### FM-008 event.emit/event.subscribe
期望：事件能够发送和被消费

---

## 9. Intelligence Skills 测试用例

### IS-001 requirement.clarify
接口：`POST /v1/responses`
期望：
- 输出结构化追问
- 输出缺失字段列表

### IS-002 blueprint.generate
接口：`POST /v1/responses`
期望：
- 生成 Blueprint JSON 草案
- 不只是自由文本

### IS-003 role.infer
期望：
- 根据目标推荐角色集合
- 结果是建议而非硬约束

### IS-004 definition.diagnose
期望：
- 能指出冲突和风险

### IS-005 data.analyze
期望：
- 能对输入数据做语义分析并输出结构化结果

### IS-006 模型客户端 smoke tests
期望：
- OpenAI-compatible responses 客户端可正确构造 `/v1/responses` 请求
- `application/json` 响应可被直接解析为结构化结果
- `text/event-stream` 响应可返回安全的 stream preview，便于轻量连通性验证
- 5xx 错误可映射为带 `retryable=true` 的 `ModelClientError`

### IS-007 意图理解路由测试
期望：
- 明确 app 需求可被识别为 `app`
- 明确 skill 需求可被识别为 `skill`
- 包含页面点击/演示线索的需求会被判定为优先示范
- 过于抽象的战略/架构型需求会先进入 clarify 路径
- 含多约束或 workflow 线索的需求不会被过早误判为必须示范

### IS-008 需求澄清与结构化提取测试
期望：
- 可输出最小 requirement spec（goal / roles / inputs / outputs / constraints / permissions / failure strategy）
- 可识别 `ready | needs_clarification | needs_demo | conflicting_constraints` 等 readiness 状态
- 缺失关键信息时返回可执行的补充问题
- API 层可通过 `/requirements/clarify`、`/requirements/extract`、`/requirements/readiness` 暴露同一套轻量 intake 能力
- app-oriented 且 ready 的需求可通过 `/requirements/blueprint-draft` 生成最小 handoff blueprint
- handoff blueprint 会根据需求信号区分 `structured_transform` / `pipeline_chain` 等轻量 app shape，并给出相应 runtime profile / execution mode

### IS-009 证据晋升与索引测试
期望：
- repeated workflow failures 可先形成 draft，再提升为 suspicious signal，并在阈值满足时生成 promoted evidence
- repeated policy-blocked events 可形成 policy-pressure signals/evidence
- repeated clarify-unresolved cases 可形成 intake-side suspicious signals
- API 层可通过 `/evidence/drafts`、`/evidence/signals`、`/evidence/promoted`、`/evidence/index`、`/evidence/stats` 暴露第一版 evidence promotion surfaces
- context compaction / working set 元数据中可包含 evidence summary，从而减少后续 prompt 对 raw 历史的依赖

### IS-010 系统能力 Skill 化测试
期望：
- requirement clarify/extract/readiness/blueprint handoff 可通过统一 system capability skill 暴露
- evidence list/stats/context-summary/search-index 可通过统一 system capability skill 暴露
- context compact/working-set/layers/select-for-prompt 可通过统一 system capability skill 暴露
- workflow overview/timeline/stats/dashboard 可通过统一 system capability skill 暴露
- risk governance events/stats/dashboard/override 可通过统一 system capability skill 暴露
- prompt selection / evidence search 可通过统一 system capability skill 暴露
- 这些 system capability skills 具备稳定 manifest、schema ref、capability profile 和 runtime handler 绑定

### IS-011 Prompt selection 高级契约测试
期望：
- `select_for_prompt` 可返回 working_set、selected_evidence、selection_policy、prompt_budget、prompt_sections，以及可选的 assembled prompt
- ranking 可根据 query/category 进行显式排序，并暴露 `match_score`、`rank_score` 等可检查字段
- promoted evidence 在同等条件下优先于 signal
- token-aware budget 能正确减少 selected evidence 数量，而不是仅使用 count limit
- capability skill `prompt.selection.skill` 可透传 budget / strategy / prompt assembly 参数
- `model_ready_prompt` 路径可在测试中以 fake model client 验证 assembled prompt 被正确送入模型调用层
- 独立 `PromptInvocationService` 应可在 service-level 测试中通过 fake loader/client 验证 selection 输出与 model invocation 被统一编排
- workflow executor 应支持 `module + ref=prompt.invoke` 的步骤，并验证其输出进入 workflow step outputs 与 context artifacts
- prompt invocation service 应验证 `normalized_response`、interaction/step telemetry 记录，以及 evaluation 记录的落盘/可读性
- requirement blueprint builder 应验证 transform-style requirement draft 会产出 `prompt.invoke` step，并同步暴露 `normalized_response` / `model_invocation` 输出契约
- 至少应有一条端到端测试：从 requirement clarify 到 blueprint draft、registry/install、workflow 执行、prompt invocation 输出与 telemetry/evaluation 落盘全部跑通
- policy guard / workflow executor 应验证 prompt invocation 被 runtime policy 禁用或要求用户批准时会被阻断并给出可审计的 policy_blocked 信号
- prompt invocation 的治理事件应验证会流入 risk policy 事件流，并可进一步触发 evidence promotion
- core replay / acceptance / archive summary 能力应验证 prompt invocation 专属视图，包括 failed replay 选择、acceptance rate、以及 success/latency/token regression 聚合

---

## 10. 数据与隔离测试

### DATA-001 用户隔离
- 用户 A 不可读用户 B 数据

### DATA-002 App 隔离
- App A 不可默认访问 App B 数据

### DATA-003 Runtime 隔离
- 一个 workflow run 的上下文不污染另一个 run

### DATA-004 Secret 安全
- secret 不写入普通日志
- secret 不出现在返回给普通角色的视图里

---

## 11. 观测与审计测试

### OBS-001 生命周期日志
验证 create/install/start/stop/update 均有记录

### OBS-002 Workflow Trace
验证每个 workflow run 都有 trace id、步骤记录、耗时

### OBS-003 Skill / Module 调用日志
验证调用均可追踪

### OBS-004 模型调用日志
验证：
- 记录 provider/model/接口/耗时/状态
- 不回显完整密钥

---

## 12. 恢复与异常测试

### REC-001 模块执行失败
期望：
- 正确记录错误
- 按策略重试或人工接管

### REC-002 Skill 调用失败
期望：
- 返回受控错误
- Builder 或 Runtime 不崩溃

### REC-003 网络抖动
期望：
- 超时正确处理
- 支持可配置重试

### REC-004 中断恢复
期望：
- 从 checkpoint 恢复
- 不丢失关键状态

---

## 13. 模型联调测试示例

### 13.1 Responses API 最小连通性
请求：
```http
POST https://crs.ruinique.com/v1/responses
Authorization: Bearer $OPENAI_API_KEY
Content-Type: application/json
```

请求体：
```json
{
  "model": "gpt-5.4",
  "input": "hello"
}
```

校验点：
- HTTP 200 或兼容成功响应
- 返回可解析文本或结构化内容

### 13.2 requirement.clarify 测试
请求体：
```json
{
  "model": "gpt-5.4",
  "input": "我想做一个文件同步应用，请列出还缺哪些需求。"
}
```

校验点：
- 是否返回缺失项
- 是否有结构化问题列表

### 13.3 chat/completions 兼容性回退测试（可选）
目标：验证网关是否兼容旧接口
主结论仍以 `/v1/responses` 为准。

### 13.4 当前项目接入状态

当前仓库已补充本地模型配置与联通脚手架：
- `app/models/model_config.py`
- `app/services/model_config_loader.py`
- `app/services/model_client.py`
- `scripts/model_probe.py`
- `config/model.local.example.json`
- `.env.local.example`

默认私有配置路径位于仓库外：
- `/root/.config/agentsystem/config.yaml`

兼容旧私有路径（迁移期）：
- `/root/.config/agentsystem/model.local.json`
- `/root/.config/agentsystem/model.local.env`

仓库内只保留模板：
- `config/config.local.example.yaml`
- `config/model.local.example.json`
- `.env.local.example`

已完成一次实际 `/v1/responses` 联通探测，返回 `MODEL_PROBE_OK`。

---

## 14. 验收标准

首期通过条件：
- 能创建、安装并运行至少一个 App
- Builder App 能创建并修改其他 App
- Foundation Modules 关键测试全部通过
- 至少 3 个 Intelligence Skills 能通过模型接口完成测试
- 生命周期、日志、恢复、隔离验证通过
- 模型主接口 `/v1/responses` 联调通过

---

## 15. 测试执行说明

当前阶段文档已形成，但系统实现尚未完成，因此现阶段测试状态应标记为：
- 文档测试设计：已完成
- 实际代码测试：待实现后执行
- 模型接口联调：待接入测试脚本后执行

建议后续新增：
- curl 测试脚本
- Python 联调脚本
- CI 集成测试脚本

## 16. 观测与升级日志设计补充

当前测试详细文档应补充一条新的实施方向：

- 正常运行所需的结构化 telemetry 与升级分析所需的 append-only 日志分离
- 升级日志按时间切分，建议使用 JSONL
- 采集策略分级，默认轻度开启
- 用户可按 app / skill / 全局控制升级信息采集与落盘
- token 消耗、延迟、成功率、反馈信号应进入候选版本验收维度

这部分目前首先属于架构与文档设计要求，后续实现后应补充对应的联调和回放测试脚本。
