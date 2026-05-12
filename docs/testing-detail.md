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


### 3.12.1 Phase P 调用运行时闭环
目标：验证统一调用信封、session binding 真值层、运行时治理层、上下文收窄、错误分类与恢复链路已经闭环。

覆盖文件：
- `tests/unit/test_invocation_envelope_and_session_binding.py`
- `tests/unit/test_asset_invocation_runtime_layer.py`
- `tests/unit/test_runtime_center_invocation_runtime_integration.py`
- `tests/unit/test_tool_context_contract_and_context_center.py`
- `tests/unit/test_context_bundle_assembly_and_tool_runtime.py`
- `tests/unit/test_routing_registry_and_governance.py`
- `tests/unit/test_invocation_compliance_installer.py`
- `tests/unit/test_standard_asset_protocol.py`
- `tests/unit/test_skill_asset_service.py`
- `tests/unit/test_runtime_topology_and_validation_harness.py`
- `tests/unit/test_error_taxonomy_and_recovery.py`
- `tests/unit/test_phase_p_remaining_regressions.py`

覆盖要点：
- asset session binding 的注册、唯一性、持久化重载、冷启动恢复
- envelope 中 root / parent / upstream / local session 关系传递
- runtime layer 对 local session 的解析与 envelope 注入
- context center 与 tool-context contract 的查询/收窄行为
- routing registry 与 governance service 的路径治理判定
- topology / audit / replay 的读侧与验证侧基线
- dispatcher/runtime-center 的结构化 error taxonomy
- deterministic / LLM-assisted / mixed multi-hop representative chains

结果：
- Focused Phase P slice：69/69 通过
- 全量本地回归：`pytest -q` → 1033 passed, 15 skipped, 5 xfailed

### 3.12.2 Phase Q / Context Center 与工作流收口
目标：验证 pending-task 工作流、Context Center working memory、summary/detail 检索、HTTP 兼容扩展、以及 bounded continuation recovery 已形成兼容闭环。

覆盖文件：
- `tests/unit/test_pending_task_orchestrator.py`
- `tests/unit/services/test_context_detail_events.py`
- `tests/unit/services/test_context_center_service_layout.py`
- `tests/unit/services/test_context_center_focused.py`
- `tests/unit/services/test_context_reorder_window.py`
- `tests/unit/services/test_durable_context_buffer.py`
- `tests/unit/services/test_context_summary_worker.py`
- `tests/unit/test_gateway_workflow_context_integration.py`
- `tests/unit/test_light_brain_gateway_pending_task.py`
- `tests/unit/test_http_test_server.py`

覆盖要点：
- canonical workflow stage / status transition helper
- repo / upgrade / acceptance 计划事实写入 pending-task state
- Context Center detail day-file、durable pending buffer、reorder window、startup recovery
- recent stable + pending working memory 合并与 detail reference lookup
- provisional summary 与 finalized summary replacement
- workflow hook、app-side write、governance observation write 进入共享上下文
- continuation recovery 的 pending-task-first + Context Center fallback
- `/api/chat` 与 `/api/action` 的 `workflow_contract` / `context_view` 兼容输出
- service-up 自迭代脚本现在额外检查 tool-required 路由在当前 upstream timeout profile 下不会退化为空响应或 `[Reached max turns ...]`，并保持 `structured_answer.self_model.answer_mode == tool_required`
- service-up E2E 脚本已扩展 context-view / restart-style recovery / tool-required route 探针，完整跑绿仍受外部模型可用性影响

结果：
- focused Context Center / workflow / HTTP slice 已按波次分别通过
- `tests/scripts/e2e_self_iteration_service_up.py` 已完成脚本增强，但真实服务闭环当前受上游模型 key 暂时不可用阻塞

### 3.12.3 Executable workflow action chain
目标：验证 post-Phase-Q 的可执行 workflow action skeleton 已经贯通 solution review、task-list、repo-context、implementation、acceptance，并且 HTTP `/api/action` 暴露与 handoff 结构稳定。

覆盖文件：
- `tests/unit/test_light_brain_gateway_pending_task.py`
- `tests/unit/test_http_test_server.py`

覆盖要点：
- `approve_solution_draft` 推进到 `tasklist_preparing`
- `revise_solution_draft` 返回 input-required / blocked review state
- `materialize_task_list` 生成 bounded task list 并 handoff 到 `locate_repo_context`
- `locate_repo_context` 解析真实仓库路径、README、key docs、target modules
- `implement_app_change` 生成结构化 `implementation_plan` 并 handoff 到 `run_acceptance`
- `run_acceptance` 执行 bounded probe commands、落盘 evidence、通过时推进到 `done`，失败时回到 blocked retry posture
- `/api/action` compatibility payload 包含 `task_list` / `repo_context` / `implementation_plan` / `acceptance_plan` / `acceptance_result` / `context_view`
- richer payload fields now covered on the live HTTP path:
  - repo truth: `repo_valid`, `primary_readme_exists`, `git_branch`, `git_dirty`
  - implementation truth: `changed_files_intent`, `changed_files_intent[].source_hint`, `work_items[].rationale`, `work_items[].source`, `validation_map`, `validation_map[].mapped_work_item_id`
  - acceptance evidence truth: normalized command evidence, summary counts, distinct/multi-command `matched_work_item_ids`, top-level `acceptance_plan.evidence_summary`, and compact `change_execution_summary`
- real `/api/action` live slices 已覆盖：
  - task-list -> repo
  - repo -> implementation
  - implementation -> acceptance(done)

结果：
- 当前 executable workflow chain 已有 gateway unit、HTTP compatibility、以及 bounded live `/api/action` 连续 handoff 覆盖

### 3.5 Iteration 10 ~ 12 v2 端到端回归
目标：验证 Phase H 主路径在复杂创建、修改 refinement、execute_action 回流、权限审批、持久化一致性上的稳定性。

#### Iteration 10：北星目标 v2 场景实施
测试文件：`tests/e2e/test_iteration10_v2_scenarios_e2e.py`

覆盖：
- 复杂创建场景的澄清与需求累积
- 按钮 / 卡片 / execute_action 回流执行
- 权限和审批链路行为一致性

关键用例：
- `test_multiturn_requirement_accumulation`
- `test_execute_action_callback`
- `test_admin_approval_flow`

结果：3/3 通过

#### Iteration 11：修改链路与 skill 增减
测试文件：`tests/e2e/test_iteration11_refinement_e2e.py`

覆盖：
- 修改 App 添加 / 移除 skill
- 修改后持久化恢复
- 运行时状态与持久化状态一致
- 多轮修改状态保留
- 创建 → 修改 → 查询 / 执行回归

关键用例：
- `test_modify_app_add_skill`
- `test_modify_app_remove_skill`
- `test_persistence_recovery_after_modification`
- `test_runtime_state_matches_persistence`
- `test_multi_turn_modification_preserves_state`
- `test_create_modify_query_flow`
- `test_permission_boundary_on_modification`
- `test_execute_action_after_modification`

结果：8/8 通过

#### Iteration 12：复杂创建稳定性与 v2 收尾回归
测试文件：`tests/e2e/test_iteration12_complex_creation_e2e.py`

覆盖：
- 多轮复杂创建需求累积稳定性
- 澄清后话题 refinement 稳定性
- 查询插入后上下文连续性
- create / modify / execute / approval 全链路回归

关键用例：
- `test_multiturn_complex_creation_accumulates_requirements`
- `test_clarification_survives_topic_refinement`
- `test_clarification_then_query_does_not_break_context`
- `test_v2_create_modify_execute_regression`
- `test_v2_permission_and_approval_regression`
- `test_v2_execute_action_regression_after_clarification`

结果：6/6 通过（初版 async test 风格失败，修正为同步包装后通过）

说明：
- 当前 E2E 套件通过 `asyncio.run(...)` 包装 gateway async 接口，避免与现有 pytest 执行模型冲突
- `pytest.mark.e2e` 尚未注册，当前仅产生告警，不影响结果判定

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
- `tests/unit/test_model_client_smoke.py`：客户端级 smoke tests，覆盖 JSON / SSE / 5xx 错误映射，以及 `wire_api=openai-completions` provider 的兼容回退（`delta.content`、`reasoning_content`、`delta.tool_calls`、streaming delta content）

### 4.1 OpenAI-compatible provider compatibility notes
目标：验证在切换到不同 OpenAI-compatible provider 时，模型客户端不会把单一响应 shape 当作唯一真相。

当前已覆盖的兼容回退：
- `/v1/chat/completions` 路径拼接在 `base_url` 带或不带 `/v1` 时都能成立
- 非流式响应可从以下字段回退抽取文本：
  - `choices[0].message.content`
  - `choices[0].message.reasoning_content`
  - `choices[0].delta.content`
- tool-calling 响应可从以下字段回退抽取工具调用：
  - `choices[0].message.tool_calls`
  - `choices[0].delta.tool_calls`
- 流式 `chat/completions` 响应可按 delta content 连续拼装文本

当前 focused 验证：
- `python3 -m pytest tests/unit/test_model_client_smoke.py -q`
- 真实连通性探针：`PYTHONPATH=/root/project/AgentSystem python3 scripts/model_probe.py`
- 当前 probe 结论：切换到 DeepSeek 后已返回 `MODEL_PROBE_OK`

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
- prompt invocation evaluation 应验证 feedback、normalized_response 与 workflow outcome hint 会影响 acceptance 结果，而不只是依赖单一 success proxy
- 结构化 quality signals 应验证 expected_output（如 `slug_text` / `json_object`）与 normalized text 之间的匹配关系会被显式记录并影响 acceptance 推导
- review summary 能力应验证这些 quality signals 继续出现在 prompt invocation acceptance/archive/regression 汇总中，而不是在 evaluation 后再次丢失
- expected_output 契约应覆盖不止一种输出形态，至少包括 `json_object`、`slug_text`、`bullet_list`、`key_value`、`approval_decision`，并验证匹配/不匹配会进入 quality signals
- executable skill adapter 应验证 JSON stdin/stdout 协议、entrypoint 缺失、超时、非零退出码、stderr/stdout 诊断、stdout 非 JSON、结果 payload 非法、skill_id 不匹配等失败映射行为
- script skill generator 应验证生成目录包含 manifest/input.schema/output.schema/error.schema/entrypoint/smoke-test/README，并能被 registry/runtime/app installer 接入后通过 workflow skill step 执行
- generated executable skill 的契约测试应验证 input/output/error schema 可被 schema registry 注册并用于 request/result 校验；manifest validator 也应覆盖 entry 非空、entrypoint 存在、timeout 合法等安装前约束
- 至少应有一条 generated executable skill 的 app-flow 测试：skill 生成并注册后，被 app blueprint 引用，安装后通过正常 skill step 执行成功

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
- `~/.config/agentsystem/config.yaml`

兼容旧私有路径（迁移期）：
- `~/.config/agentsystem/model.local.json`
- `~/.config/agentsystem/model.local.env`

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

## 2026-05-06 - Standard-install-model Phase 2 scenario audit evidence

### Target
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Findings
- scenario count preserved at 50
- scenario-end `/api/history/{session_id}` validation already exists
- operator/install-model gaps still present:
  - explicit install coverage is thin
  - asset discover/list/install operator flows are missing
  - restart/recovery operator chains are missing
  - runtime-layout / migrate-runtime operator flows are missing

### Command evidence
- `python3 - <<'PY' ... Path('tests/e2e/test_50_scenarios_20_turns_user_level.py').read_text(...) ... PY`
- observed summary:
  - `history_check True`
  - `scenario_count 50`
  - `install 2`
  - `discover 0`
  - `assets 0`
  - `restart 0`
  - `restore 0`

## 2026-05-06 - Standard-install-model Phase 2 scenario refresh evidence

### Target
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Changes
- rewrote `S50` from a generic publish/feedback flow into an operator-facing standard-install lifecycle scenario
- preserved total scenario count at 50
- preserved 20 turns for the refreshed scenario
- added natural-language prompts for:
  - status
  - doctor
  - runtime-layout
  - assets list/discover/install
  - restart guidance
  - migrate-runtime framing
  - pre-migration baseline reasoning

### Command evidence
- `python3 - <<'PY' ... ast.parse(source) ... PY`
- observed summary:
  - `syntax_ok`
  - `scenario_count 50`
  - `runtime_layout_mentions 1`
  - `asset_mentions 6`
  - `doctor_mentions 1`
- Rewrote `S41` into an operator-focused system status / doctor / runtime-layout / asset-check conversation.
- Additional observed summary after refresh:
  - `status_mentions 1`
  - `doctor_mentions 3`
  - `runtime_layout_mentions 2`
  - `asset_discover_mentions 1`
  - `restart_mentions 2`
- Rewrote `S12` into a bulk-app lifecycle scenario with install/register/asset-check prompts before and after startup.
- Additional observed summary after refresh:
  - `标准安装链路 1`
  - `安装和注册 1`
  - `list 还是 discover 1`
  - `install 一个之后 1`
  - `统一停止三个App 1`
- Rewrote `S25` into an exception-recovery and restart-continuity scenario with explicit prompts for abnormal exit, session-state checking, doctor usage, runtime-layout/log inspection, and recovery sequencing.
- Additional observed summary after refresh:
  - `异常退出 1`
  - `会话状态 1`
  - `重新启动或恢复 1`
  - `runtime-layout 1`
  - `恢复检查 1`
- Rewrote `S36` into a skill-install failure and repair scenario with explicit prompts for discover retry, doctor clues, installed/log inspection, and post-fix usability verification.
- Additional observed summary after refresh:
  - `安装失败 3`
  - `discover 一次相关资产 1`
  - `doctor 能告诉我哪些线索 1`
  - `installed 目录 2`
  - `排查步骤总结 1`

## 2026-05-06 - Standard-install-model Phase 2 report-output enhancement evidence

### Target
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Changes
- added `_scenario_verdict(...)` helper
- scenario stdout now prints `verdict=` and compact reason text
- JSON report now includes:
  - `verdict`
  - `verdict_reasons`
  - `history_expectation_ok`
  - `history_expectation_failures`
  - `history_expectation_checks`

### Command evidence
- `python3 - <<'PY' ... ast.parse(source) ... PY`
- observed summary:
  - `syntax_ok`
  - `verdict_reasons 1`
  - `history_expectation_failures 1`
  - `all_turns_and_history_checks_passed 1`
  - `verdict= 2`

## 2026-05-06 - Standard-install-model Phase 2 harness validation evidence

### Target
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `python3 -m tests.e2e.test_50_scenarios_20_turns_user_level --help`

### Observed result
- module compiles successfully
- CLI help renders expected flags:
  - `--base-url`
  - `--delay`
  - `--timeout`
  - `--scenarios`
  - `--range`
  - `--output`

### Notes
This is an initial static validation pass for the refreshed harness. Live subset execution remains a later step once the service-up baseline run is intentionally entered.
- Canonical operator-focused live subset for the next run: `S12,S25,S36,S41,S50`.

## 2026-05-06 - Standard-install-model Phase 2 live subset attempt

### Command
- `python3 -m tests.e2e.test_50_scenarios_20_turns_user_level --base-url http://localhost:80 --scenarios S12,S25,S36,S41,S50 --delay 0 --timeout 20 --output /tmp/agentsystem_e2e_operator_subset.json`

### Result
- service connectivity check failed before scenario execution
- observed error: `[Errno 111] Connection refused`

### Interpretation
- the enhanced harness and operator-focused subset are ready, but live subset validation is blocked until the local service is started as part of Phase 3 service-up preparation.

## 2026-05-06 - Phase 3 service-readiness doctor slice evidence

### Target
- `app/cli.py`
- `tests/unit/test_cli.py`

### Changes
- `status` / `doctor` now include:
  - `config_file`
  - `service_reachable`
  - `service_url`
  - `service_error` or `service_status_code`
- `checks` now explicitly include:
  - `config_file`
  - `service_reachable`

### Validation
- `pytest tests/unit/test_cli.py -q`
- result: `6 passed`

## 2026-05-06 - Live doctor output after service-readiness slice

### Command
- `python3 -m app.cli doctor`

### Observed output summary
- `status=needs_attention`
- all repo-local layout checks passed
- `config_file=True`
- `service_reachable=False`
- `service_error=[Errno 111] Connection refused`
- `service_url=http://localhost:80/api/status`

### Interpretation
- the CLI readiness slice is working as intended: configuration is present, but the live local HTTP service is still down, which matches the earlier blocked operator-subset run.

## 2026-05-06 - Explicit not-implemented CLI control contract evidence

### Target
- `app/cli.py`
- `tests/unit/test_cli.py`

### Changes
- `start` / `stop` / `restart` / `install` / `bootstrap` / `migrate-runtime` now return:
  - `status=not_implemented`
  - `exit_code=2`
  - `next_step=use status/doctor to inspect readiness before wiring live runtime control`

### Validation
- `pytest tests/unit/test_cli.py -q`
- `python3 -m app.cli start`
- results:
  - test suite: `7 passed`
  - command output includes `status=not_implemented`
  - process exits with code `2`

## 2026-05-06 - Canonical repo-coupled start-command hint evidence

### Target
- `app/cli.py`
- `tests/unit/test_cli.py`

### Changes
- `doctor` / `status` and unwired runtime-control commands now expose:
  - `suggested_start_command=cd /root/project/AgentSystem && PYTHONPATH=/root/project/AgentSystem uvicorn app.system.http_test_server:app --host 0.0.0.0 --port 80`

### Validation
- `pytest tests/unit/test_cli.py -q`
- `python3 -m app.cli doctor`
- results:
  - test suite: `7 passed`
  - doctor output includes the canonical start-command hint

## 2026-05-06 - Canonical repo-coupled uvicorn startup validation

### Command
- `PYTHONPATH=/root/project/AgentSystem timeout 20s python3 -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port 80`

### Observed output summary
- runtime boot completed successfully
- observed markers:
  - `Application startup complete.`
  - `Uvicorn running on http://0.0.0.0:80`
  - graceful shutdown after timeout wrapper

### Interpretation
- the current repo-coupled start path is runnable and can bring the local service up; the earlier blocked subset run was caused by the service not being started, not by a broken uvicorn startup path.

## 2026-05-06 - First live operator-subset run root cause evidence

### Commands
- `PYTHONPATH=/root/project/AgentSystem nohup python3 -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port 80 > /tmp/agentsystem_phase3_subset.log 2>&1 &`
- `python3 -m tests.e2e.test_50_scenarios_20_turns_user_level --base-url http://localhost:80 --scenarios S12,S25,S36,S41,S50 --delay 0 --timeout 20 --output /tmp/agentsystem_e2e_operator_subset.json`
- `tail -n 80 /tmp/agentsystem_phase3_subset.log`

### Observed result
- harness connectivity gate passed (`HTTP 405` on reachability check)
- all 5 scenarios failed with repeated `HTTP 500` / connection reset patterns
- server log root cause:
  - `AssertionError: The 'python-multipart' library must be installed to use form parsing.`
  - failure occurred in `/root/project/AgentSystem/app/system/http_test_server.py` during `/login` form parsing

### Fix landed
- added `python-multipart>=0.0.9` to `pyproject.toml`

### Interpretation
- the operator subset is now past pure service-up gating and has produced a concrete missing-runtime-dependency defect for the current install path.

## 2026-05-06 - Second live operator-subset run after `.venv` start-path correction

### Commands
- restarted service with `.venv/bin/python3 -m uvicorn ...`
- `python3 -m tests.e2e.test_50_scenarios_20_turns_user_level --base-url http://localhost:80 --scenarios S12,S25,S36,S41,S50 --delay 0 --timeout 20 --output /tmp/agentsystem_e2e_operator_subset.json`
- `grep -n "ERROR:\|Traceback\|POST /api/chat\|200 OK\|504 Gateway Timeout" /tmp/agentsystem_phase3_subset.log`

### Observed result
- login succeeded (`POST /login HTTP/1.1 200 OK`)
- `/api/chat` requests reached real execution (`POST /api/chat HTTP/1.1 200 OK`)
- LLM/tool-calling path intermittently failed with:
  - `ModelClientError: Chat with tools failed: 504 ...`
  - `Rate limit blocked: Concurrent query limit exceeded (5/5)`
- JSON report summary remained:
  - `scenarios_all_ok 0`
  - `scenarios_with_fail 5`

### Interpretation
- the `.venv` start-path correction fixed the earlier multipart/login blocker
- the current next-layer issue is upstream model/tool-calling instability and concurrency pressure during the operator-heavy subset run

## 2026-05-06 - Tool-calling 5xx retry hardening evidence

### Target
- `app/ai/model_client.py`

### Changes
- `chat_with_tools(...)` retry window expanded from 2 attempts to 3 attempts
- transient HTTP 5xx responses are now retried with bounded backoff before surfacing a failure
- transport retries also use slightly longer bounded backoff to reduce immediate repeat pressure

### Validation
- `python3 -m py_compile app/ai/model_client.py`

## 2026-05-06 - Concurrent-slot release hardening evidence

### Target
- `app/system/gateway/light_brain_gateway.py`

### Changes
- wrapped the post-rate-limit command execution path in `try/finally`
- `self._rate_limiter.decrement_concurrent(session_id)` now runs even when command execution returns early or raises

### Validation
- `python3 -m py_compile app/system/gateway/light_brain_gateway.py app/ai/model_client.py`

## 2026-05-06 - Post-hardening rerun timing note

### Commands
- restarted `.venv` uvicorn service
- reran operator subset with `--delay 1`

### Observed result
- harness connectivity gate returned: `服务不可达: timed out`
- existing log still confirms the prior `.venv`-based server process had reached `Application startup complete.`

### Interpretation
- this rerun attempt appears to have hit startup/readiness timing rather than the earlier multipart/login or stranded-concurrency defect classes
- the next live rerun should explicitly wait for ready state before launching the subset

## 2026-05-06 - Harness ready-state wait gate evidence

### Target
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Changes
- added `_wait_for_service(...)` helper based on `/api/status`
- replaced the old one-shot `/api/chat` reachability probe with an explicit ready-state wait
- added CLI flag:
  - `--wait-ready-seconds`

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `python3 -m tests.e2e.test_50_scenarios_20_turns_user_level --help | grep -n 'wait-ready-seconds'`

## 2026-05-06 - Ready-state-gated rerun observation

### Commands
- restarted `.venv` uvicorn service
- reran operator subset with:
  - `--wait-ready-seconds 60`
  - `--delay 1`

### Observed result
- ready-state gate no longer failed first
- report file remained on the prior failing summary shape (`scenarios_all_ok 0`, `scenarios_with_fail 5`)
- live log still shows repeated:
  - `Concurrent query limit exceeded (5/5)`
  - `Invocation dispatch error: method strategy_overview not declared by asset:self_iteration_center:v1`

### Interpretation
- the ready-state wait fix removed one sequencing failure mode
- the remaining dominant blockers are still runtime-level concurrency pressure and invocation-path correctness

## 2026-05-06 - Self-iteration descriptor alias parity evidence

### Target
- `app/bootstrap/runtime.py`

### Changes
- updated the runtime fallback descriptor payload for `asset:self_iteration_center:v1`
- added the missing `strategy_overview` alias so dispatcher-side descriptor reconstruction matches the asset's declared invoke surface

### Validation
- `python3 -m py_compile app/bootstrap/runtime.py`
- string check confirmed one `"name": "strategy_overview"` entry in the fallback descriptor block

## 2026-05-06 - Atomic session-slot acquisition evidence

### Targets
- `app/services/rate_limiter.py`
- `app/system/gateway/light_brain_gateway.py`

### Changes
- added `try_acquire_session_slot(session_id)` to combine rate validation with concurrent-slot reservation atomically
- updated gateway receive path to use the atomic acquire helper instead of separate:
  - `is_session_allowed(...)`
  - `increment_concurrent(...)`
  - `record_query(...)`

### Validation
- `python3 -m py_compile app/services/rate_limiter.py app/system/gateway/light_brain_gateway.py`
- direct smoke check:
  - first acquire returns `(True, None)`
  - concurrent state increments to `1`
  - release brings the counter back to `0`

## 2026-05-06 - Post-atomic-acquire rerun observation

### Commands
- restarted `.venv` uvicorn service
- reran operator subset with:
  - `--wait-ready-seconds 60`
  - `--delay 1`

### Observed result
- live log still shows repeated:
  - `Concurrent query limit exceeded (5/5)`
- the output report did not advance to a new passing summary during the observed run window

### Interpretation
- the atomic acquire fix was necessary, but it was not sufficient to eliminate the operator-subset concurrency failure signature
- the next investigation should move from acquire/release mechanics to identifying why the same logical session (`session_user_skill_01`) accumulates or overlaps requests at runtime

## 2026-05-06 - Rate-limiter concurrency diagnostics instrumentation

### Target
- `app/services/rate_limiter.py`

### Changes
- added structured acquire/release logging for per-session concurrency state
- blocked acquire logs now include:
  - session id
  - current concurrent count
  - current query timestamp count
- successful acquire/release logs now emit the post-operation concurrent count

### Validation
- `python3 -m py_compile app/services/rate_limiter.py`
- direct smoke check still succeeds for one acquire + one release cycle

## 2026-05-06 - Diagnostic rerun scope expansion observation

### Commands
- restarted `.venv` uvicorn service
- reran operator subset with ready-state wait and delay
- inspected `/tmp/agentsystem_phase3_subset.log` for concurrency signatures

### Observed result
- repeated `Concurrent query limit exceeded (5/5)` still present
- the saturation is not limited to one logical session anymore in the observed log slice; it appears on at least:
  - `session_user_context_10`
  - `session_user_skill_01`
- the newly added info-level acquire/release diagnostics did not surface in the current log slice, which implies current logging configuration is not exposing that level for this module during the subset run

### Interpretation
- the remaining failure mode is broader than one isolated scenario session
- before adding more behavioral fixes, the next bounded step should ensure acquire/release diagnostics are emitted at the active log level during rerun, or otherwise capture the same state through warning/error-level observability

## 2026-05-06 - Promote concurrency diagnostics to active log level

### Target
- `app/services/rate_limiter.py`

### Changes
- promoted successful acquire logging from `info` to `warning`
- promoted release logging from `info` to `warning`
- blocked acquire logging remains at `warning`
- this ensures the next subset rerun emits acquire/release/blocked state in the current service log configuration

### Validation
- `python3 -m py_compile app/services/rate_limiter.py`
- direct smoke check now visibly emits:
  - `RateLimiter acquire: ...`
  - `RateLimiter release: ...`

## 2026-05-06 - Warning-level diagnostic rerun observation

### Commands
- restarted `.venv` uvicorn service
- reran operator subset with ready-state wait and delay
- inspected the latest `/tmp/agentsystem_phase3_subset.log`

### Observed result
- log still prominently shows the old gateway-level block signature:
  - `Rate limit blocked: session=... Concurrent query limit exceeded (5/5)`
- the promoted warning-level `RateLimiter acquire/release/...` diagnostics still did not appear in the captured log slice
- the same slice also still includes:
  - `Invocation dispatch error: method strategy_overview not declared by asset:self_iteration_center:v1`

### Interpretation
- the rerun log suggests the effective service process/log capture path is still not reflecting the newest rate-limiter diagnostics consistently
- before making more product-path fixes, the next bounded step should verify that the intended restarted server process is actually the one serving the subset run and that the captured log file belongs to that exact process generation

## 2026-05-06 - Dedicated Phase 3 subset server launcher for process/log generation control

### Target
- `scripts/start_phase3_subset_server.sh`

### Changes
- added a dedicated launcher for the Phase 3 subset validation path
- the launcher now:
  - truncates the target log file before startup
  - writes an explicit startup marker with timestamp
  - writes the launched server PID into the same log
  - starts the `.venv` uvicorn test server with the expected `PYTHONPATH`

### Validation
- `bash -n scripts/start_phase3_subset_server.sh`
- script header and marker-writing logic verified

## 2026-05-06 - Clean-generation rerun proved new diagnostics are live

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected only the fresh log generation after the launcher marker

### Observed result
- fresh marker and PID were present in the log:
  - `phase3-subset-start ...`
  - `phase3-subset-server-pid 678962`
- warning-level rate-limiter diagnostics are now confirmed live in the fresh generation:
  - `RateLimiter acquire: session=session_user_lifecycle_07 concurrent=1 query_timestamps=1`
  - `RateLimiter release: session=session_user_lifecycle_07 concurrent=0 query_timestamps=1`
  - next turn reacquired normally at `concurrent=1`, `query_timestamps=2`
- the same fresh generation then exposed a different blocking layer on the second turn:
  - upstream `504 Gateway Timeout`
  - `ModelClient.chat_with_tools transient server failure ... attempt=1 status=504`

### Interpretation
- process/log generation ambiguity is now resolved for this rerun
- acquire/release behavior is at least visible and appears healthy in the observed fresh slice
- the next dominant blocker in this clean generation is upstream tool-calling model instability rather than an immediate stale-log ambiguity

## 2026-05-06 - Bounded 504 retry hardening for tool-calling model path

### Target
- `app/ai/model_client.py`

### Changes
- increased `chat_with_tools(...)` retry budget from 3 attempts to 4 attempts
- split transient upstream handling so `502/503/504` receive a stronger backoff schedule than generic 5xx
- retry logs now include `retry_in` so rerun evidence can show the actual pause window

### Validation
- `python3 -m py_compile app/ai/model_client.py`
- source check confirmed:
  - `max_attempts = 4`
  - `transient_statuses = {502, 503, 504}`

## 2026-05-06 - Post-504-hardening clean-generation rerun observation

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `685765`

### Observed result
- the fresh generation again showed healthy early acquire/release behavior for `session_user_lifecycle_07`
- unlike the previous clean-generation slice, the observed tool-calling path advanced through multiple successful model/tool turns instead of immediately surfacing a 504
- observed successful progression included:
  - `call_asset_method`
  - `exec_shell`
  - `list_files`
  - `exec_shell`
  - `write_file`
- no immediate upstream `504 Gateway Timeout` appeared in the inspected fresh slice

### Interpretation
- the strengthened bounded retry/window hardening materially improved the previously dominant clean-generation blocker
- the operator subset is now getting deeper into real tool-execution turns before the run needs further diagnosis

## 2026-05-06 - Deeper clean-generation blocker: tool-turn ceiling

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `689183`

### Observed result
- early acquire/release behavior remained healthy
- the previously dominant early 504 did not appear in the observed slice
- the first clearly exposed deeper blocker was now:
  - `ToolCallingEngine result: final_text=[Reached max turns (6)]`
- the recorded tool-call chain before the ceiling was hit included repeated asset/tool exploration:
  - `call_asset_method`
  - `call_asset_method`
  - `call_asset_method`
  - `list_files`
  - `exec_shell`
  - `exec_shell`

### Interpretation
- after the 504 hardening, the operator subset is now reaching a deeper failure layer
- the next bounded improvement target should focus on reducing unproductive tool-call wandering or raising/reshaping the tool-turn budget for this path

## 2026-05-06 - Operator-heavy turn-budget widening

### Target
- `app/system/gateway/tool_calling_interpreter.py`

### Changes
- widened `choose_turn_budget(...)` for operator-heavy messages related to:
  - `app`
  - `标准安装`
  - `安装链路`
  - `交付`
  - `创建`
  - `状态`
  - `运行`
- such requests now receive a turn budget of `8` instead of the generic `6`

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py`
- direct checks confirmed:
  - standard-install / app-delivery phrasing now returns `8`
  - generic greeting still returns `6`

## 2026-05-06 - Post-budget-widening clean-generation observation

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `695845`

### Observed result
- early acquire/release behavior remained healthy
- the first user turn in the observed slice completed directly without falling into a max-turn loop
- subsequent operator-heavy turns went deeper, but a new issue surfaced:
  - one turn returned a malformed direct response containing raw tool-call markup fragments such as `<tool_call>` / `<function=call_asset_method>`
- the same slice also shows continued exploratory asset/tool selection on follow-up turns

### Interpretation
- widening the operator-heavy turn budget helped avoid the earlier immediate `Reached max turns (6)` ceiling in the observed slice
- the next exposed blocker is now response-shape / tool-call rendering correctness, not the old early turn-budget ceiling

## 2026-05-06 - Tool-call markup leak guard

### Target
- `app/system/gateway/tool_calling_interpreter.py`

### Changes
- hardened `_apply_execution_fact_provenance(...)` so raw internal tool-call markup is never passed through directly to user-visible text
- when `final_text` contains internal markers such as `<tool_call>` / `<function=...>`, the interpreter now replaces them with a bounded human-readable summary derived from recorded tool call names

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py`
- direct check confirmed a raw markup payload is transformed into:
  - `已完成内部工具分析，涉及: call_asset_method, exec_shell。正在基于这些结果整理最终结论。`

## 2026-05-06 - Post-markup-guard clean-generation observation

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `702452`

### Observed result
- no raw `<tool_call>` / `<function=...>` leakage is visible in the observed slice
- the operator-heavy path now uses the widened 8-turn budget and reaches at least turn 8
- the dominant remaining pattern is still exploratory wandering across asset + shell + filesystem style tools, for example:
  - repeated `call_asset_method`
  - `exec_shell`
  - `list_files`
  - `read_file`
  - `read_file`

### Interpretation
- the markup-leak guard appears to have contained the user-visible response-shape defect in the observed slice
- the next dominant blocker is now clearly inefficient tool-path selection / exploration breadth, not raw output leakage

## 2026-05-06 - Operator-heavy convergence guidance hardening

### Target
- `app/system/gateway/tool_calling_interpreter.py`

### Changes
- extended `build_turn_state_board(...)` to detect operator-heavy messages (app/标准安装/安装链路/交付/创建/状态/运行/安装/注册/部署)
- operator-heavy paths now receive:
  - "下一步建议: 优先通过 call_asset_method 查询 App 状态或资产信息；只在资产接口无法直接回答时才走文件系统探索"
  - "停止条件: 一旦能够基于资产查询结果或已有证据直接回答用户问题，立即停止工具调用"
- added convergence escalation for operator-heavy messages with non-convergent history markers
  - "收敛提醒: 近期已出现未收敛信号，本轮应优先给出基于已获取证据的明确结论，不要继续多轮工具探索"

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py`
- direct checks confirmed:
  - standard-install phrasing returns operator-heavy guidance
  - generic greeting returns default guidance
  - non-convergent history triggers convergence escalation


### 2026-05-09 1seey + GLM-5.1 tool-required route validation
- verified direct provider path with `https://ai.1seey.com/v1/chat/completions` and model `GLM-5.1`
- verified `PYTHONPATH=/root/project/AgentSystem python3 -m scripts.model_probe` returns `MODEL_PROBE_OK` after routing `request()/probe()` via `chat/completions` for `wire_api=openai-completions`
- verified `tool-required probe` no longer fails with `[Reached max turns (6)]` and now preserves `tool_required` structured-answer semantics through clarification exits
- latest live service-up run advanced past `tool-required probe`, `draft continuation path`, `restart-bounded continuation recovery`, and `draft apply action` before a later governance self-iteration cycle hit an upstream `504` on turn 4

### 2026-05-09 route-aware tool-chat budgeting
- verified `_tool_route_budget()` returns tighter `(max_attempts, timeout_cap)` pairs as tool-route message history deepens
- verified targeted tool-calling engine tests still pass after introducing bounded retry/timeout policy for deeper GLM tool routes
- next live target remains the later governance self-iteration cycle that previously hit `1seey` `504` on turn 4

## 2026-05-10 - Post-convergence-guidance clean-generation observation

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `1922482`

### Observed result
- early acquire/release behavior remained healthy
- the operator-heavy path still wandered, but the pattern shifted:
  - repeated `find_tool`
  - repeated `call_asset_method`
- the earlier filesystem-heavy drift (`list_files` / `read_file`) was reduced in the observed slice
- the remaining budget was still consumed without converging to a direct answer in the inspected turns

### Interpretation
- the added convergence guidance helped suppress some filesystem wandering, but it was not sufficient to stop higher-level tool-selection drift
- the next bounded improvement should narrow the tool surface for operator-heavy routes, especially to reduce repeated `find_tool` exploration when the problem is already within known asset/app surfaces

## 2026-05-10 - Operator-heavy tool-surface narrowing

### Target
- `app/system/gateway/tool_calling_interpreter.py`

### Changes
- added `narrow_tools_for_operator_route(...)`
- operator-heavy routes now expose a narrowed tool surface:
  - `call_asset_method`
  - `exec_shell`
  - `read_file`
  - `ask_clarification`
  - `unclear`
- specifically removed broad discovery / filesystem drift tools from this path, including:
  - `find_tool`
  - `list_files`
  - `search_files`
  - `write_file`
  - `edit_file`

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py`
- direct check confirmed operator-route narrowing keeps only:
  - `['call_asset_method', 'exec_shell', 'read_file', 'ask_clarification', 'unclear']`

## 2026-05-10 - Post-operator-tool-narrowing clean-generation observation

### Commands
- started the server via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `1929048`

### Observed result
- operator-heavy tool exposure was successfully narrowed in the live path:
  - `prompt_tools=['exec_shell', 'read_file', 'call_asset_method', 'ask_clarification', 'unclear']`
  - `exec_tools=['exec_shell', 'read_file', 'call_asset_method', 'ask_clarification', 'unclear']`
- the earlier `find_tool` wandering disappeared from the observed slice
- the path still failed to converge quickly enough because the model repeatedly selected `call_asset_method` across turns 1-6 without transitioning to a direct answer
- this confirms the primary remaining wandering pattern is now repeated asset-method exploration rather than broad tool discovery or filesystem drift

### Interpretation
- narrowing the tool surface worked as intended and removed `find_tool` from the live operator-heavy path
- the remaining blocker is now a deeper `call_asset_method` loop inside the narrowed route
- the next bounded improvement should target stop conditions or repeated-tool-loop suppression for consecutive identical asset-method exploration

## 2026-05-10 - Repeated call_asset_method loop guard

### Target
- `app/ai/tool_calling_engine.py`

### Changes
- added a consecutive tool-call tracker inside the multi-turn tool loop
- when `call_asset_method` is selected 3 consecutive turns, the engine now injects a loop-guard tool result instead of executing another identical asset-method step
- the injected guard explicitly tells the model to stop calling tools and answer directly unless one final missing fact is truly required

### Validation
- `python3 -m py_compile app/ai/tool_calling_engine.py`

## 2026-05-10 - Phase3 subset launcher stale-port cleanup hardening

### Target
- `scripts/start_phase3_subset_server.sh`

### Trigger
- a fresh rerun attempt failed with `ERROR: [Errno 98] ... address already in use`
- live inspection showed port 80 was still held by prior subset server PID `1929048`
- the existing cleanup only killed the bare `uvicorn app.system.http_test_server:app` pattern and missed the actual `python3 -m uvicorn ...` launch form

### Changes
- extended the launcher cleanup patterns to also kill:
  - `python3 -m uvicorn app.system.http_test_server:app`
  - `.venv/bin/python3 -m uvicorn app.system.http_test_server:app`

### Validation
- `bash -n scripts/start_phase3_subset_server.sh`
- direct source check confirmed all three cleanup patterns are present

## 2026-05-10 - Post-loop-guard clean-generation observation

### Commands
- killed stale PID `1929048` that had been contaminating port 80
- restarted via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `1940980`

### Observed result
- the repeated asset-method loop guard fired as intended:
  - `ToolCallingEngine loop guard triggered session=session_user_lifecycle_07 turn=3 tool=call_asset_method consecutive=3`
- after the guard fired, the next model turn stopped tool calling:
  - `returned_tool_calls=[] finish_reason=stop`
- the route transitioned from unbounded repeated tool use into a direct response instead of continuing to max turns
- however, the resulting answer quality was still weak: it stopped with a cautious summary (`目前我无法直接确认...`) rather than producing the stronger operator-facing closure expected by the scenario

### Interpretation
- engine-level repeated-tool suppression is effective at breaking the pathological `call_asset_method` loop
- the dominant remaining issue is no longer looping itself, but weak answer synthesis after the guard-induced stop
- the next bounded improvement should strengthen post-guard answer promotion so the model converts gathered evidence into a tighter operator-facing conclusion instead of retreating into generic uncertainty

## 2026-05-10 - Post-loop-guard answer shaping hardening

### Target
- `app/system/gateway/tool_calling_interpreter.py`

### Changes
- extended `_apply_execution_fact_provenance(...)` to detect the synthetic loop-guard tool call marker
- when the tool-call trail includes `call_asset_method` with `{"loop_guard": true}` the interpreter now rewrites weak post-stop output into a tighter operator-facing convergence summary
- the rewritten summary explicitly states:
  - current evidence is insufficient for full confirmation
  - the route should stop broad exploration
  - the smallest next step is one targeted verification before returning a final conclusion

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py`

## 2026-05-10 - Post-answer-shaping rerun surfaced upstream model transport instability

### Commands
- restarted via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `1947449`

### Observed result
- the rerun entered the expected operator-heavy path with the narrowed tool surface intact
- before the first tool-selection cycle could complete, the upstream model layer stalled and logged:
  - `ModelClient.chat_with_tools transient transport failure model=GLM-5.1 attempt=1 error=The read operation timed out retry_in=0.75s`
- this prevented the new answer-shaping path from being cleanly evaluated in the observed slice

### Interpretation
- current blocker for this specific rerun attempt was external model transport instability, not a newly observed local logic regression
- the post-loop-guard answer-shaping fix still needs a clean live validation pass once the upstream timeout noise subsides

## 2026-05-10 - Early tool-route patience hardening for upstream timeout noise

### Target
- `app/ai/model_client.py`

### Trigger
- clean rerun attempts for the operator-heavy subset were still being interrupted by early upstream read timeouts before the new post-loop-guard answer shaping could be evaluated

### Changes
- widened `_tool_route_budget(...)` for earlier / shallower tool-chat turns:
  - `message_count < 4` now uses `(4 attempts, 75.0s cap)`
  - `message_count >= 4` now uses `(3 attempts, 60.0s cap)`
- deeper routes remain bounded:
  - `message_count >= 6` -> `(2, 50.0)`
  - `message_count >= 8` -> `(1, 45.0)`

### Validation
- `python3 -m py_compile app/ai/model_client.py`
- direct check confirmed:
  - `2 -> (4, 75.0)`
  - `4 -> (3, 60.0)`
  - `6 -> (2, 50.0)`
  - `8 -> (1, 45.0)`

## 2026-05-10 - Patience-hardened rerun still hit upstream 504 on the very first tool turn

### Commands
- restarted via `scripts/start_phase3_subset_server.sh /tmp/agentsystem_phase3_subset.log`
- reran the operator subset with ready-state wait and delay
- inspected the fresh generation tied to server PID `1954599`

### Observed result
- the widened early tool-route budget was active in live execution:
  - `message_count=2 max_attempts=4 timeout_cap=75.0`
- despite the higher patience budget, the first upstream tool-chat call still returned:
  - `HTTP/1.1 504 Gateway Timeout`
  - `transient server failure ... attempt=1 status=504 retry_in=1.5s`
- this means the latest retry/timeout hardening is live, but the current validation attempt was still dominated by upstream provider instability before local answer-shaping could be assessed

### Interpretation
- the patience hardening was wired correctly and reached the live path
- the remaining blocker for this rerun attempt was still upstream 504 behavior, not a fresh local regression in the operator-heavy convergence fixes

## 2026-05-10 - Task-list closure note for remaining tool-required route validation

### Summary
- local convergence hardening for the operator-heavy subset is now layered and live:
  - guidance hardening
  - tool-surface narrowing
  - repeated `call_asset_method` loop guard
  - post-loop-guard answer shaping
  - stale subset-server cleanup hardening
  - early tool-route patience hardening
- the current remaining blocker for the unresolved tool-required validation item is upstream provider instability (`504` / read timeout), not newly observed local HTTP drift or unconstrained local wandering

### Task-list impact
- refreshed `docs/standard-install-model-detailed-task-list.md` so the unresolved-item summary reflects the current state of Phase 0 closure work

## 2026-05-10 - CLI runtime-layout repo-root dependency tightening

### Target
- `app/cli.py`
- `tests/unit/test_cli.py`

### Trigger
- while continuing Phase 0 unresolved-item closure in task-list order, repo-root dependency inspection surfaced that the CLI tests were still effectively anchored to `/root/project/AgentSystem` in their expected layout assertions

### Changes
- replaced the stale hardcoded layout constant pattern with a relative `DEFAULT_LAYOUT_DIRS` map assembled from the detected repo root
- updated CLI unit tests to assert against `REPO_ROOT` dynamically instead of the literal `/root/project/AgentSystem` path

### Validation
- `python3 -m py_compile app/cli.py tests/unit/test_cli.py`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `7 passed`

## 2026-05-10 - Runtime subprocess default cwd repo-root dependency tightening

### Targets
- `app/system/runtime/app_process_manager.py`
- `app/system/workers/app_mgmt.py`

### Trigger
- continuing the Phase 0 repo-root dependency closure work surfaced that subprocess launch paths still defaulted `cwd` to `os.getcwd()`, which silently ties runtime behavior to the current repo checkout location

### Changes
- `AppProcessManager.start_app_process(...)`
  - default subprocess `cwd` now resolves to `self._data_dir` when no explicit `cwd` is provided
- `AppManagementWorker._launch_subprocess(...)`
  - default subprocess `cwd` now resolves to `AGENTSYSTEM_DATA_DIR` (falling back to `data`) when no explicit `cwd` is provided
  - added `Path` import for normalized path resolution

### Validation
- `python3 -m py_compile app/system/runtime/app_process_manager.py app/system/workers/app_mgmt.py`
- direct check confirmed default resolved cwd now points at the runtime data root rather than the current shell cwd

## 2026-05-10 - Pipeline executor default workspace repo-root dependency tightening

### Target
- `app/orchestration/pipeline_executor.py`

### Trigger
- continuing the Phase 0 repo-root dependency closure scan surfaced that both `BaseExecutor` and `PipelineExecutor` still defaulted their workspace to `os.getcwd()`, which would silently couple pipeline execution to the launch directory of the runtime

### Changes
- added `_default_workspace()`
  - prefers `AGENTSYSTEM_DATA_DIR` when present
  - otherwise falls back to resolved `data`
- updated `BaseExecutor` and `PipelineExecutor` to use `_default_workspace()` instead of `os.getcwd()` when no explicit workspace is provided

### Validation
- `python3 -m py_compile app/orchestration/pipeline_executor.py`
- direct check confirmed:
  - without env override, default workspace resolves to the runtime data root
  - with `AGENTSYSTEM_DATA_DIR=/tmp/agentsystem-runtime-data`, both executors adopt that runtime path

## 2026-05-10 - Validation script startup guidance repo-root assumption tightening

### Targets
- `tests/scripts/e2e_detailed_tests.py`
- `tests/scripts/e2e_interactive_tests.sh`
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Trigger
- continuing the Phase 0 repo-root dependency cleanup surfaced that several validation scripts still told operators to run commands via `cd <repo-root> ...`, which preserved an unnecessary repo-root assumption in the human-facing validation path

### Changes
- rewrote startup guidance strings to say "在项目目录执行 ..." instead of embedding `cd <repo-root>` examples
- preserved the same startup commands while removing the hardcoded repo-root phrasing from validation instructions

### Validation
- `python3 -m py_compile tests/scripts/e2e_detailed_tests.py tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `bash -n tests/scripts/e2e_interactive_tests.sh`

## 2026-05-10 - Service-up probe scripts stop requiring repo-root cwd for uvicorn launch

### Targets
- `tests/scripts/e2e_self_iteration_service_up.py`
- `tests/scripts/e2e_draft_creation_probe.py`

### Trigger
- continuing the Phase 0 repo-root dependency closure work surfaced that these service-up probe scripts still launched uvicorn with `cwd=str(ROOT_DIR)`, which preserved a runnable-path dependency on the repo checkout directory

### Changes
- replaced `ROOT_DIR`-anchored runtime assumptions with:
  - `PROJECT_DIR` for import resolution
  - `RUNTIME_DATA_DIR` for runtime working directory and log location
- uvicorn subprocesses now launch with:
  - `cwd=str(RUNTIME_DATA_DIR)`
  - `PYTHONPATH=<project_dir>`
  - `AGENTSYSTEM_DATA_DIR=<runtime_data_dir>`
- removed the unnecessary `cwd=str(ROOT_DIR)` from the `fuser` port-kill helper in the draft probe script

### Validation
- `python3 -m py_compile tests/scripts/e2e_self_iteration_service_up.py tests/scripts/e2e_draft_creation_probe.py`

## 2026-05-10 - Cheap query/read fast path for list/query/status requests

### Targets
- `app/system/gateway/tool_calling_interpreter.py`
- `tests/unit/test_tool_calling_interpreter.py`

### Trigger
- the Phase 0 merged unresolved items still explicitly listed `query/read fast-path for cheap count/status/list requests`

### Changes
- added `_try_cheap_query_fast_path(...)` before the file-introspection and full tool-calling LLM tiers
- cheap requests matching rule-based `list_apps` / `query_app` / `query_status` now bypass the tool-calling LLM route and return immediately from the light-brain rule interpreter
- tagged these commands with source `cheap_query_fast_path`
- refreshed unit expectations around current structured-answer self-model defaults while adding coverage for the new fast path

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py tests/unit/test_tool_calling_interpreter.py`
- `python3 -m pytest tests/unit/test_tool_calling_interpreter.py -q`
  - `23 passed`

## 2026-05-10 - Run isolation metadata for long E2E analysis (`run_id`, `scenario_id`)

### Targets
- `app/system/http_test_server.py`
- `app/system/chat_observation.py`
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_http_test_server.py`

### Trigger
- the remaining active task-list closure item explicitly called for `run isolation metadata for long E2E analysis (run_id, scenario_id)`
- older closure-upgrade notes also required test-generated session logs to carry `run_id` and scenario-to-log correlation metadata

### Changes
- added `_extract_run_metadata(...)` to the HTTP test server and plumbed optional `payload.run_id` / `payload.scenario_id` through `/api/chat`
- when present, `run_id` / `scenario_id` are now attached to:
  - in-memory `conversation_history` records
  - persisted session chat logs via `_append_chat_log(...)`
  - live chat observation probes via `build_chat_observation_probe(...)`
- `persist_chat_observation(...)` now reuses the E2E-provided `run_id` instead of always generating a detached observation run id
- updated the 50-scenario user-level E2E runner to:
  - accept `--run-id`
  - generate a default run id when not provided
  - send `{run_id, scenario_id}` in each `/api/chat` request payload
  - print the selected run id at startup for operator correlation
- added server-level unit coverage asserting that `run_id` / `scenario_id` reach chat logs, conversation history, and live chat observation persistence
- while validating this slice, fixed a missing HTTP test server import for `build_governance_rollout_operator_summary`, which was breaking unrelated nightly-governance endpoint tests

### Validation
- `python3 -m py_compile app/system/http_test_server.py app/system/chat_observation.py tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_http_test_server.py`
- `python3 -m pytest tests/unit/test_http_test_server.py -q`
  - `37 passed`

## 2026-05-10 - Closure scoring split beyond raw response success in user-level E2E reports

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Trigger
- the active detailed task list still explicitly called for `closure scoring split beyond raw response success`
- current user-level E2E reporting mostly collapsed turn quality into raw `ok/fail`, which hid useful distinctions like empty responses, short low-information replies, fallback-like answers, and workflow-success hints

### Changes
- added per-turn `closure_signals` to the user-level E2E runner
- closure signals now separate:
  - `raw_ok`
  - `empty_response`
  - `very_short_response`
  - `informative_length_ok`
  - `fallback_like`
  - `workflow_success_hint`
  - derived `closure_score`
- added per-scenario `closure_summary` aggregation with:
  - average closure score
  - empty-response turn count
  - very-short-response turn count
  - fallback-like turn count
  - workflow-success-hint turn count
  - raw-ok turn count
- failure-detail console output now prints closure-summary hints for failed scenarios
- persisted JSON report now includes both per-turn `closure_signals` and per-scenario `closure_summary`

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py`

## 2026-05-10 - CLI suggested start command no longer teaches repo-root runtime cwd coupling

### Targets
- `app/cli.py`
- `tests/unit/test_cli.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- even after tightening runtime subprocesses, pipeline workspaces, and service-up probes, the CLI control-plane suggestion still taught a repo-root-coupled launch shape: `cd <repo-root> && PYTHONPATH=<repo-root> ...`
- this was still directly relevant to the active Phase 0 closure item around runnable-path repo-root dependency

### Changes
- changed `_start_command(...)` so the suggested launch path now uses:
  - `--app-dir <repo_root>` for import resolution
  - `AGENTSYSTEM_DATA_DIR=<repo_root/data>` for runtime data placement
  - no `cd <repo-root>` requirement
  - no inline `PYTHONPATH=<repo_root>` requirement
- updated CLI tests to assert the new contract
- refreshed the detailed task list notes to record the new closure slice under the repo-root dependency item and to mark the three older closure-upgrade bullets as landed

### Validation
- `python3 -m py_compile app/cli.py tests/unit/test_cli.py`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `7 passed`

## 2026-05-10 - Focused closure rerun for remaining Phase R Wave 5 acceptance-binding slice

### Targets
- `tests/unit/test_light_brain_gateway_acceptance_binding.py`
- `tests/unit/test_http_test_server.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- the detailed install-model task list still carried the old Phase R Wave 5 open-slice bullets as unresolved even though the implementation and earlier notes now indicated they had landed
- before marking those bullets closed, a focused rerun was needed on the acceptance-binding and real HTTP coverage that prove the slice end to end

### Validation
- `python3 -m pytest tests/unit/test_light_brain_gateway_acceptance_binding.py tests/unit/test_http_test_server.py -q`
  - `43 passed`

### Closure confirmed
- changed-file intent is derived and surfaced from richer repo/task-list sourcing
- multi-command acceptance evidence binds distinct `matched_work_item_ids` without defaulting immediately to a single-work-item fallback
- compact operator-facing `change_execution_summary` remains surfaced on both acceptance evidence and top-level `acceptance_plan`
- task-list status was updated to mark the remaining Wave 5 open-slice bullets as closed and to move old-work validation/docs phases into active in-progress state

## 2026-05-10 - Focused local rerun for current HTTP/action compatibility surfaces

### Targets
- `tests/unit/test_http_test_server.py`
- `tests/unit/test_light_brain_gateway_acceptance_binding.py`
- `tests/unit/test_tool_calling_interpreter.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after closing several Phase 0 sub-slices, the remaining HTTP-compatibility bullet still needed an up-to-date local regression snapshot that isolates local contract health from the still-open upstream provider instability window

### Validation
- `python3 -m pytest tests/unit/test_http_test_server.py tests/unit/test_light_brain_gateway_acceptance_binding.py tests/unit/test_tool_calling_interpreter.py -q`
  - `66 passed`

### Coverage reconfirmed
- `/api/chat` response contract and structured-answer surfacing
- `/api/action` continuation / acceptance / workflow payload propagation
- acceptance-plan evidence binding and compact change-execution summary surfacing
- cheap query fast-path behavior and tool-route fallback boundaries

### Note
- this strengthens the evidence that the current remaining blocker on the unresolved service-up closure item is external provider instability during live operator-heavy runs, not a newly observed local HTTP/action compatibility regression

## 2026-05-10 - Bounded grep sweep for remaining repo-root runnable-path coupling

### Targets
- `app/`
- `tests/`
- `scripts/`
- top-level startup shell surfaces
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after landing the runtime cwd, pipeline workspace, service-up probe, and CLI start-contract decoupling fixes, the remaining Phase 0 repo-root dependency item still needed a fresh bounded scan for obvious leftover runnable-path patterns

### Validation
- bounded grep sweep for the main legacy signatures:
  - `cd {repo_root}`
  - `PYTHONPATH=.*repo_root`
  - `ROOT_DIR = Path(__file__)`
  - `cwd=str(ROOT_DIR)`
  - `os.getcwd()`
- result:
  - `NO_MATCHES`

### Note
- this is intentionally a bounded static confirmation pass, not a proof that every future runtime shape is install-model clean
- it does strengthen the current Phase 0 status by showing that the previously identified obvious repo-root runnable-path signatures are no longer present in the main app/test/script/startup surfaces

## 2026-05-10 - Focused old-work closure regression bundle

### Targets
- `tests/unit/test_cli.py`
- `tests/unit/test_http_test_server.py`
- `tests/unit/test_light_brain_gateway_acceptance_binding.py`
- `tests/unit/test_tool_calling_interpreter.py`
- `tests/unit/test_pending_task_orchestrator.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after multiple Phase 0 closure slices were landed and individually documented, section `1.3 Close validation and docs for old work` still needed one explicit focused regression bundle showing that the old-work closure evidence was now consolidated rather than scattered only across separate commits

### Validation
- `python3 -m pytest tests/unit/test_cli.py tests/unit/test_http_test_server.py tests/unit/test_light_brain_gateway_acceptance_binding.py tests/unit/test_tool_calling_interpreter.py tests/unit/test_pending_task_orchestrator.py -q`
  - `85 passed`

### Coverage bundle
- CLI control-plane contract and repo-root decoupled startup guidance
- `/api/chat` and `/api/action` workflow/acceptance payload compatibility
- acceptance-plan evidence binding and compact change-execution-summary surfacing
- cheap-query fast-path and interpreter boundary behavior
- pending-task orchestrator acceptance-plan/result persistence

### Outcome
- this focused regression bundle is sufficient to mark the validation/docs sub-phase as landed for old-work closure, even though broader install-model implementation phases remain ahead

## 2026-05-10 - Phase 3 subset startup script no longer relies on repo-root cwd/PYTHONPATH

### Targets
- `scripts/start_phase3_subset_server.sh`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- even after the broader repo-root decoupling work, the Phase 3 subset startup helper still encoded the old startup pattern with `cd "$PROJECT_DIR"` and `PYTHONPATH="$PROJECT_DIR:..."`
- this kept one of the active startup/service-up helpers tied to repo-root runtime assumptions

### Changes
- removed `cd "$PROJECT_DIR"`
- removed explicit `PYTHONPATH` export
- added `RUNTIME_DATA_DIR="${AGENTSYSTEM_DATA_DIR:-$PROJECT_DIR/data}"`
- launch now uses:
  - `env AGENTSYSTEM_DATA_DIR="$RUNTIME_DATA_DIR"`
  - `--app-dir "$PROJECT_DIR"`
- keeps the earlier restart-hardening behavior (`pkill` + port-free wait) intact

### Validation
- `bash -n scripts/start_phase3_subset_server.sh`
- grep confirmation shows:
  - `AGENTSYSTEM_DATA_DIR`
  - `--app-dir`
  - no remaining startup-path `PYTHONPATH` export or repo-root `cd`

## 2026-05-10 - Compatibility shell wrappers no longer export repo-root PYTHONPATH

### Targets
- `start_server.sh`
- `start_web_server.sh`
- `stop_server.sh`
- `tests/unit/test_cli.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- the previous repo-root coupling sweep still found the top-level compatibility wrappers exporting `PYTHONPATH="$PROJECT_DIR:..."`
- even though they were only delegating into the Python CLI, they still preserved the old repo-root import pattern at the wrapper layer

### Changes
- removed `PYTHONPATH` export from all three wrappers
- wrappers now invoke `app/cli.py` directly via:
  - `"$PROJECT_DIR/.venv/bin/python3" "$PROJECT_DIR/app/cli.py" ...`
  - or `python3 "$PROJECT_DIR/app/cli.py" ...`
- updated CLI wrapper tests accordingly

### Validation
- `bash -n start_server.sh start_web_server.sh stop_server.sh`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `7 passed`

## 2026-05-10 - Full E2E helper scripts no longer rely on repo-root cwd/PYTHONPATH module launches

### Targets
- `run_full_e2e_bg.sh`
- `run_full_e2e_detached.sh`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after cleaning the subset-start and CLI-wrapper surfaces, the repo-coupling sweep still found the two full-E2E helper scripts using:
  - `cd "$ROOT"`
  - `export PYTHONPATH="$ROOT"`
  - `python -m tests.e2e...`
- this preserved the old repo-root execution shape for long-run baseline helpers

### Changes
- removed repo-root `cd`
- removed repo-root `PYTHONPATH` export
- replaced `-m tests.e2e.test_50_scenarios_20_turns_user_level` with direct execution of:
  - `"$ROOT/tests/e2e/test_50_scenarios_20_turns_user_level.py"`
- kept existing logging/timeout arguments unchanged

### Validation
- `bash -n run_full_e2e_bg.sh run_full_e2e_detached.sh`
- grep confirmation found no remaining:
  - `PYTHONPATH`
  - `cd "$ROOT"`
  - `-m tests.e2e`

## 2026-05-10 - Grouped pytest runner helper no longer depends on repo-root `cd`

### Targets
- `scripts/run_test_groups.sh`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after cleaning several startup and E2E helper surfaces, the sweep still found `scripts/run_test_groups.sh` using `cd "$ROOT"` and a shell-string pytest command shape
- this preserved another helper-level dependency on repo-root execution context

### Changes
- removed `cd "$ROOT"`
- changed the pytest launcher from a shell string to a direct interpreter path:
  - `PYTEST="$ROOT/.venv/bin/python"`
  - `"$PYTEST" -m pytest -q "$@"`
- kept the grouped test selection unchanged

### Validation
- `bash -n scripts/run_test_groups.sh`
- grep confirmation found no remaining:
  - `cd "$ROOT"`
  - `PYTHONPATH`

## 2026-05-10 - Startup/helper repo-coupling sweep reached zero remaining simple shell-pattern hits

### Targets
- `start_*.sh`
- `stop_*.sh`
- `scripts/`
- `run_*.sh`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after the wrapper, subset-helper, full-E2E-helper, and grouped-test-runner cleanups, one final bounded shell-surface sweep was needed before reclassifying the startup-path and runnable-path task-list items

### Validation
- bounded grep for:
  - `export PYTHONPATH=`
  - `cd "$ROOT"`
  - `cd "$PROJECT_DIR"`
  - `PYTHONPATH=$ROOT`
  - `PYTHONPATH=$PROJECT_DIR`
- result:
  - no matches

### Outcome
- marked the startup-path cleanup item as closed
- marked the runnable-path repo-root dependency item as closed
- narrowed section `1.2` to the remaining live HTTP/provider closure window rather than broad path-cleanup uncertainty

## 2026-05-10 - Phase 0 remainder reclassification after closure-upgrade and helper-path cleanup

### Targets
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after the closure-upgrade items, startup/helper cleanup, runnable-path sweeps, and focused local HTTP regressions had all landed, the detailed task list still described some resolved buckets as generically open

### Changes
- marked the older closure-upgrade bucket as closed because all three tracked sub-items are now landed
- expanded section `1.2` so the remaining code-level loose-end state is described explicitly:
  - local HTTP/action contract evidence is green
  - startup/helper/path-cleanup sweeps are green
  - the remaining unresolved window is live upstream tool-calling/provider stability during operator-heavy service-up validation

### Note
- this is a task-list truthfulness update, not a claim that the live provider-window blocker itself is solved

## 2026-05-10 - Initial CLI/script surface inventory for Phase 1

### Targets
- `docs/standard-install-model-detailed-task-list.md`

### Inventory snapshot
- top-level shell surfaces:
  - `start_server.sh`
  - `start_web_server.sh`
  - `stop_server.sh`
  - `run_full_e2e_bg.sh`
  - `run_full_e2e_detached.sh`
  - `task_push.sh`
- helper scripts:
  - `scripts/start_phase3_subset_server.sh`
  - `scripts/run_test_groups.sh`
  - `scripts/model_probe.py`
- python entrypoints relevant to install-model control-plane planning:
  - `app/cli.py`
  - `app/system/http_test_server.py`
  - `app/runtime/app_bootstrap.py`
  - `tests/e2e/test_50_scenarios_20_turns_user_level.py`

### Outcome
- recorded Phase `2.1` as landed in the detailed task list
- confirmed the main operator control plane is now consolidated into `app/cli.py`
- confirmed the remaining gap is not missing surface discovery, but wiring the planned runtime/install commands to real service/install behavior

## 2026-05-10 - Phase 1 CLI target-surface and contract sections normalized

### Targets
- `docs/standard-install-model-detailed-task-list.md`

### Changes
- marked section `2.2` as landed now that the command surface is explicitly defined and the parser surface already exists
- collapsed the duplicate `2.3 Define CLI behavior contracts` headings into one concrete status section
- clarified the split between:
  - commands whose names/parser surface already exist
  - commands that already expose live contract behavior (`status`, `doctor`, `runtime-layout`)
  - commands still awaiting deeper service/install wiring (`start`, `stop`, `restart`, `install`, `bootstrap`, `migrate-runtime`)

### Outcome
- the Phase 1 task-list sections now better match the actual current CLI maturity instead of mixing planning bullets with already-landed contract work

## 2026-05-10 - CLI contracts now expose explicit operation-scope metadata

### Targets
- `app/cli.py`
- `tests/unit/test_cli.py`

### Trigger
- after normalizing the Phase 1 task sections, the next useful contract improvement was to make the CLI responses state more explicitly whether a command is showing source-repo transition state or targeting a future installed-runtime control action

### Changes
- added explicit `operation_scope` metadata to CLI result contracts:
  - `source_repo_health_view` for `status` / `doctor`
  - `source_repo_layout_view` for `runtime-layout`
  - `installed_runtime_target_not_yet_wired` for not-yet-implemented runtime/install commands
- added `layout_mode=transition_repo_anchored` to the runtime-layout response
- refreshed focused CLI tests accordingly

### Validation
- `python3 -m py_compile app/cli.py tests/unit/test_cli.py`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `7 passed`

## 2026-05-10 - CLI health commands now expose explicit failure semantics

### Targets
- `app/cli.py`
- `tests/unit/test_cli.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after adding operation-scope metadata, the next useful contract improvement for `status` / `doctor` was to expose why the command is unhealthy and what the operator should do next, rather than only returning `needs_attention`

### Changes
- `status` / `doctor` now expose:
  - `status_reason`
  - `missing_checks`
  - `next_actions`
- health checks now explicitly skip non-check metadata keys from the runtime-layout contract
- task list contract notes updated to reflect the landed failure-semantics slice

### Validation
- `python3 -m py_compile app/cli.py tests/unit/test_cli.py`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `7 passed`

## 2026-05-10 - First live asset inventory slice landed in the CLI

### Targets
- `app/cli.py`
- `tests/unit/test_cli.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after strengthening the health/status contracts, the next safe move from the Phase 1 command surface was to convert one of the `assets` subcommands from pure placeholder status into a small real behavior slice

### Changes
- `assets list` and `assets discover` now return a live builtin-asset inventory derived from `SYSTEM_SKILL_SPECS`
- both commands expose:
  - `status = ok`
  - `operation_scope = source_repo_asset_inventory_view`
  - `asset_count`
  - `assets`
- `assets install` remains planned for now
- task list updated to reflect that `assets list` / `assets discover` are no longer skeleton-only surfaces

### Validation
- `python3 -m py_compile app/cli.py tests/unit/test_cli.py`
- `python3 -m pytest tests/unit/test_cli.py -q`
  - `9 passed`

## 2026-05-10 - E2E harness localhost preflight now ignores ambient proxy settings

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_harness.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- Phase 3 live subset attempts showed a confusing mismatch: shell `curl http://localhost:80/api/status` succeeded, but the Python/httpx readiness gate in the E2E harness reported `服务不可达: timed out`
- this pointed to the harness inheriting ambient proxy settings during localhost readiness and chat calls, which is exactly the wrong behavior for repo-local baseline validation

### Changes
- changed the harness readiness probe to construct `httpx.Client(..., trust_env=False)`
- changed `E2EClient` to construct its long-lived `httpx.Client(..., trust_env=False)`
- added focused unit tests covering both constructor sites
- updated the task list notes for Phase 3 service-up preparation

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_harness.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_harness.py -q`
  - `2 passed`

### Notes
- this does not remove upstream model-call timeout risk inside `/api/chat`
- it does remove a false-negative local-readiness failure mode, so the next live subset rerun can more cleanly distinguish local harness transport problems from real model/runtime instability

## 2026-05-10 - E2E harness can now fail fast on pathological timeout streaks

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_fail_fast.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after the localhost transport fix, a bounded live rerun against `S41` reached `/api/chat` successfully on the first turn, then fell into repeated per-turn timeouts
- without an early-abort control, this kind of pathological streak wastes large chunks of Phase 3 runtime while adding very little new diagnostic value

### Changes
- added `--max-consecutive-failures` to the user-level E2E harness
- `run_scenario(...)` now tracks consecutive failed turns and can abort a scenario early when the configured threshold is reached
- scenario results and JSON report output now persist:
  - `aborted_early`
  - `abort_reason`
- updated the Phase 3 task list notes for baseline execution and failure analysis

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_harness.py tests/unit/test_user_level_e2e_fail_fast.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_harness.py tests/unit/test_user_level_e2e_fail_fast.py -q`
  - `3 passed`

### Live evidence
- bounded rerun command:
  - `PYTHONUNBUFFERED=1 timeout 180 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41 --delay 1 --timeout 45 --wait-ready-seconds 5 --output /tmp/e2e_single_s41.json`
- observed behavior:
  - readiness gate passed (`HTTP 200`)
  - turn `01/20` succeeded quickly
  - subsequent turns hit repeated `Timeout after 45.0s`

### Notes
- this change does not fix the underlying `/api/chat` timeout issue
- it does make Phase 3 reruns cheaper and more honest by stopping once the run is clearly in a pathological failure mode

## 2026-05-10 - Added per-scenario turn caps for bounded Phase 3 diagnostics

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_fail_fast.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- Phase 3 analysis now strongly suggests that the live timeout pattern may depend on turn progression or context buildup, because bounded evidence showed turn `01/20` can succeed while later turns time out
- we needed a cleaner way to probe `turn 1 only`, `turn 1-2`, `turn 1-3`, etc. without editing scenario data or launching a full 20-turn replay every time

### Changes
- added `--max-turns-per-scenario` to the user-level E2E harness
- `run_scenario(...)` now accepts `max_turns` and slices the scenario turn list for bounded diagnostics
- report metadata now records:
  - `max_turns_per_scenario`
  - `max_consecutive_failures`
- extended fail-fast tests to cover bounded-turn execution
- updated Phase 3 failure-analysis notes in the task list

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_fail_fast.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `4 passed`

### Notes
- this does not reduce the eventual need for full 20-turn and full 50-scenario baselines
- it does make the current Phase 3 diagnostic loop much tighter, especially for isolating whether timeout onset tracks with conversation depth

## 2026-05-10 - Bounded S41 probe confirmed timeout onset at turn 02 and report semantics were tightened

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after adding bounded-turn and fail-fast controls, the next useful action was to actually use them against `S41` to narrow the timeout onset window
- the first bounded probe showed that the harness report still described the run in terms of full 20-turn totals even when only a subset of turns had been executed, which made Phase 3 evidence harder to read cleanly

### Bounded live probe
- command:
  - `PYTHONUNBUFFERED=1 timeout 150 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 2 --max-consecutive-failures 1 --output /tmp/e2e_s41_turn2_probe.json`
- observed behavior:
  - readiness gate passed (`HTTP 200`)
  - `01/20` succeeded quickly
  - `02/20` timed out after `45.0s`
  - scenario aborted immediately after the first consecutive failure threshold was hit

### Changes
- tightened report/banner semantics for bounded runs:
  - startup banner now distinguishes `计划轮次` vs `执行轮次`
  - summary now distinguishes `计划轮次`, `执行预算轮次`, and `实际执行轮次`
  - JSON report now stores:
    - `planned_total_turns`
    - `executed_turn_budget`
- task list updated to record that the current live timeout onset window is localized to turn `02` on `S41`

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_fail_fast.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `4 passed`

## 2026-05-10 - Tightened tool-route retry budgets after Phase 3 log evidence showed upstream 504 amplification

### Targets
- `app/ai/model_client.py`
- `tests/unit/test_tool_calling_engine.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- bounded `S41` live probes plus `/tmp/agentsystem_phase3.log` showed the second-turn stall was not a local readiness failure
- the dominant pattern was repeated upstream `504 Gateway Timeout` responses on the tool-calling route (`/v1/chat/completions`), with the server retrying enough times to stretch one degraded turn across several minutes

### Changes
- tightened `_tool_route_budget(...)` in `app/ai/model_client.py`
  - `message_count < 4` now uses `(3 attempts, 60s cap)`
  - `message_count >= 4` now uses `(2 attempts, 55s cap)`
  - `message_count >= 6` remains `(2 attempts, 50s cap)`
  - `message_count >= 8` remains `(1 attempt, 45s cap)`
- this aligns the implementation with the existing unit-test expectations and reduces how long early degraded tool routes can monopolize a live user turn
- updated the Phase 3 failure-analysis notes to reflect the upstream-504 finding

### Validation
- `python3 -m py_compile app/ai/model_client.py tests/unit/test_tool_calling_engine.py`
- `python3 -m pytest tests/unit/test_tool_calling_engine.py -q`
  - `14 passed`

### Notes
- this is not a full provider-stability fix
- it is a runtime-facing mitigation that should make degraded tool-call turns collapse faster and surface fallback behavior sooner instead of spending multiple minutes inside retry amplification

## 2026-05-10 - Gateway prompt history window tightened for short operator/status turns

### Targets
- `app/system/gateway/tool_calling_interpreter.py`
- `tests/unit/test_tool_calling_interpreter_context.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- the captured `/tmp/agentsystem_chat_with_tools_payload.json` showed the tool-calling system prompt was carrying repeated fallback-heavy recent dialogue into later short status queries
- for the current `S41` failure class, that kind of history bloat is low-value context and may increase the chance that a simple second-turn operator question gets routed through an unnecessarily heavy prompt

### Changes
- tightened `build_session_context(...)` history inclusion for gateway tool-call prompts:
  - recent-history window reduced to the last 4 messages
  - total recent-history character budget reduced from `2000` to `800`
- added a focused unit test proving that older dialogue is dropped and the prompt stays bounded
- updated Phase 3/4 task-list notes to record this as the first prompt-shape mitigation in the repair loop

### Validation
- `python3 -m py_compile app/system/gateway/tool_calling_interpreter.py tests/unit/test_tool_calling_interpreter_context.py`
- `python3 -m pytest tests/unit/test_tool_calling_interpreter_context.py -q`
  - `1 passed`

### Notes
- this does not change the fundamental session history stored by the product
- it only narrows how much recent conversation is re-exposed inside the gateway tool-calling prompt for short live operator/status turns

## 2026-05-11 - Live budget-aware S41 rerun cleared the turn-02 timeout, then bounded-history expectations were corrected

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_history_expectations.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after confirming `/api/status` exposed the new `tool_route_budget`, the next necessary step was a fresh bounded live rerun against `S41` on the actually restarted runtime
- the rerun materially improved: both bounded turns succeeded, but the harness still failed the run because scenario-end history expectations were comparing a 2-turn diagnostic run against the full 20-turn scenario design

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 150 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 2 --max-consecutive-failures 1 --output /tmp/e2e_s41_turn2_probe_livebudget.json`
- observed behavior:
  - readiness gate passed (`HTTP 200`)
  - `01/20` succeeded
  - `02/20` also succeeded in roughly `1.0s`
  - remaining failure was only bounded-history expectation mismatch

### Changes
- `_evaluate_scenario_history(...)` now compares history counts against `len(result.turns)` for bounded diagnostic runs rather than always against the full scenario design length
- added a focused unit test covering bounded history expectations
- updated the Phase 4 repair notes to reflect that the turn-02 timeout cleared on the restarted live runtime

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_history_expectations.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `5 passed`

## 2026-05-11 - Deepened S41 bounded probe to 5 turns and isolated scenario users by run id

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_history_expectations.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after the 2-turn bounded rerun cleared the original turn-02 timeout, the next useful move was to extend the same live probe to a deeper 5-turn window
- the 5-turn probe showed all five turns succeeding, but the scenario-end history count still mismatched because repeated probes were reusing the same scenario user/session identity across runs

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 210 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_s41_turn5_probe_livebudget.json`
- observed behavior:
  - readiness gate passed (`HTTP 200`)
  - turns `01-05/20` all succeeded
  - no transport/service errors occurred in the 5-turn window
  - remaining failure was only stale-history contamination from prior probes using the same scenario user id

### Changes
- added `_effective_user_id(...)` so each run uses a run-id-isolated scenario user identity when `run_id` is present
- this keeps bounded diagnostics from inheriting old `/api/history` records from earlier probes of the same scenario
- added a focused unit test for run-id user isolation
- updated Phase 4 repair notes to record the 5-turn live success window

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_history_expectations.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `6 passed`

## 2026-05-11 - Bounded 5-turn rerun exposed silent empty responses, harness now counts them as failures

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_response_visibility.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after run-id isolation removed stale session contamination, the bounded 5-turn `S41` rerun still did not produce a clean pass
- inspection of `/tmp/e2e_s41_turn5_probe_isolated.json` showed the deeper issue: several turns were being counted as `ok=True` even though both `response` and `content` were empty, which is not an acceptable user-visible success condition for the user-level baseline

### Changes
- tightened turn success classification in `run_scenario(...)`
  - a turn now counts as `ok` only when:
    - `ok` is truthy
    - `type != error`
    - there is non-empty visible response text in `response` or `content`
- added a focused unit test proving that empty visible responses are marked as failures
- updated Phase 4 repair notes to record that silent empty replies are now treated as a real remaining issue instead of a hidden green result

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_response_visibility.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_response_visibility.py tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `7 passed`

## 2026-05-11 - API chat error path now emits visible assistant text instead of silent empty replies

### Targets
- `app/system/http_test_server.py`
- `tests/unit/test_http_test_server.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- log inspection of the isolated bounded `S41` rerun showed repeated upstream `429 Too Many Requests` failures inside `gateway.receive_message(...)`
- the HTTP server was already catching those exceptions, but its error response did not populate `response`/`content` and did not append an assistant error message into conversation history, which is why user-level E2E was seeing silent empty replies

### Changes
- updated `/api/chat` exception handling so failures now:
  - create a visible assistant error text: `LLM request failed: ...`
  - append that assistant error message into `conversation_history`
  - persist the visible error text into chat logs and observations
  - return `response` and `content` fields in the HTTP JSON body even when `success=false`
- added focused unit coverage for this error-path contract

### Validation
- `python3 -m py_compile app/system/http_test_server.py tests/unit/test_http_test_server.py`
- `python3 -m pytest tests/unit/test_http_test_server.py::test_api_chat_error_returns_visible_response_and_history_entry tests/unit/test_user_level_e2e_response_visibility.py tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `8 passed`
- restarted the local service and re-ran bounded `S41` with `--max-turns-per-scenario 5`
  - turns that previously appeared as silent empties now surface explicit `LLM request failed: ... 429 ...`
  - scenario-end history now fails for the honest reason: visible error markers remain in the conversation

## 2026-05-11 - Tool-route 429 now degrades to conservative fallback, bounded S41 5-turn probe passes cleanly

### Targets
- `app/ai/model_client.py`
- `tests/unit/test_model_client_tool_route_budget.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after surfacing visible `/api/chat` errors, the remaining bounded `S41` defect was honest but still undesirable: provider `429` pressure was visible to users and failed the user-level baseline
- the existing `ToolCallingEngine` already had a turn-0 degradation path for retryable tool-route failures; the missing piece was that `429` responses were not marked retryable

### Changes
- updated `app/ai/model_client.py`
  - `chat_with_tools(...)` now marks `429` failures as `retryable=True`
- this lets `ToolCallingEngine.execute_turns(...)` degrade first-turn tool-route `429` pressure into the existing conservative non-convergence text instead of surfacing raw provider failure text
- added focused unit coverage proving `429` is now classified as retryable for tool routes

### Validation
- `python3 -m py_compile app/ai/model_client.py tests/unit/test_model_client_tool_route_budget.py`
- `python3 -m pytest tests/unit/test_model_client_tool_route_budget.py tests/unit/test_http_test_server.py::test_api_chat_error_returns_visible_response_and_history_entry tests/unit/test_user_level_e2e_response_visibility.py tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `9 passed`
- restarted the local service
- reran bounded `S41` with `--max-turns-per-scenario 5`
  - turns `01-05/20` all succeeded
  - no transport/service errors occurred
  - scenario-end history checks passed
  - status/operator turns under provider pressure degraded to the conservative visible fallback text
- report: `/tmp/e2e_s41_turn5_probe_429degrade.json`

## 2026-05-11 - Widened bounded live rerun from S41 to system/operator subset S41-S45, all 5 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after `S41` alone cleared the repaired 5-turn bounded probe, the next task-list-aligned move was to test whether the same repair stack generalizes to the adjacent system/operator scenarios instead of staying at a single-scenario anecdote

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 420 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41,S42,S43,S44,S45 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_system_subset_turn5_probe.json`
- observed behavior:
  - `5/5` scenarios passed
  - `25/25` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
  - provider pressure still degraded into the conservative visible fallback text where needed, without breaking the bounded user-level baseline

### Outcome
- this is the first bounded multi-scenario confirmation that the repaired operator/system path is not just a single `S41` outlier
- current evidence supports treating `S41-S45` as a repaired bounded subset and moving outward to the next adjacent slice before a full 50-scenario retry

## 2026-05-11 - Widened bounded live rerun again to cross-interaction subset S46-S49, all 4 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after the repaired bounded system/operator subset `S41-S45` passed, the next adjacent slice in the task list was the cross-interaction cluster `S46-S49`
- this checks whether the repair stack still holds when scenario patterns mix multiple users, rapid requests, mixed intent styles, and longer conversational carry-over

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 420 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S46,S47,S48,S49 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_cross_subset_turn5_probe.json`
- observed behavior:
  - `4/4` scenarios passed
  - `20/20` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- bounded repaired behavior now extends beyond the system/operator slice into the adjacent cross-interaction slice
- current repaired bounded evidence covers `S41-S49` with clean pass results across both subsets
- next useful move is to merge repaired slices into a broader bounded baseline window before retrying the full 50-scenario run

## 2026-05-11 - Merged repaired bounded slices into one combined S41-S49 rerun, all 9 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after both repaired bounded subsets (`S41-S45` and `S46-S49`) passed independently, the next evidence step was to merge them into one larger bounded baseline window
- this checks whether the repaired behavior remains stable when both slices run back-to-back in one live execution instead of as isolated batches

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 600 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S41,S42,S43,S44,S45,S46,S47,S48,S49 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_s41_s49_combined_turn5_probe.json`
- observed behavior:
  - `9/9` scenarios passed
  - `45/45` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- repaired bounded evidence now covers the combined contiguous slice `S41-S49` in a single live run
- this is a stronger signal than separate subset passes because it confirms the repaired path remains stable across a larger chained baseline window
- next useful decision is whether to widen once more into the next adjacent slice or to take a larger bounded jump toward the full 50-scenario suite

## 2026-05-11 - Broadened bounded slice to S30-S49, uncovered and fixed one harness-only S31 history mismatch

### Targets
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- `tests/unit/test_user_level_e2e_history_expectations.py`
- `docs/standard-install-model-detailed-task-list.md`

### Trigger
- after `S41-S49` passed as one contiguous repaired bounded slice, the next useful move was a larger bounded jump to `S30-S49`
- that broader run passed `19/20` scenarios; the only failure was `S31`, and inspection showed it was not a product/runtime regression but a harness accounting bug

### Root cause
- `S31` intentionally includes empty and whitespace-only turns
- the harness already skips those synthetic inputs instead of issuing HTTP calls
- scenario-end history expectations were still counting them as if they should appear in persisted `/api/history`, which caused `expected 5 user turns, got 3`

### Changes
- added `_history_counted_turns(...)` to filter out synthetic empty-input placeholder turns from persisted-history expectations
- added focused unit coverage proving `S31` synthetic empty turns no longer inflate expected user-turn counts
- reran bounded `S31` after the fix and confirmed scenario-end history checks pass cleanly

### Validation
- `python3 -m py_compile tests/e2e/test_50_scenarios_20_turns_user_level.py tests/unit/test_user_level_e2e_history_expectations.py`
- `python3 -m pytest tests/unit/test_user_level_e2e_history_expectations.py tests/unit/test_user_level_e2e_fail_fast.py tests/unit/test_user_level_e2e_harness.py -q`
  - `7 passed`
- bounded rerun:
  - `tests/e2e/test_50_scenarios_20_turns_user_level.py --scenarios S31 --max-turns-per-scenario 5 --max-consecutive-failures 1`
  - scenario passed with history checks passing
- reports:
  - broad slice: `/tmp/e2e_s30_s49_bounded_turn5_probe.json`
  - focused post-fix S31: `/tmp/e2e_s31_bounded_turn5_postfix.json`

## 2026-05-11 - Re-ran corrected broader bounded slice S30-S49, all 20 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after fixing the synthetic-empty-input history accounting bug surfaced by `S31`, the next required step was to repeat the broader bounded slice instead of treating the focused `S31` rerun as sufficient evidence

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 900 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S30,S31,S32,S33,S34,S35,S36,S37,S38,S39,S40,S41,S42,S43,S44,S45,S46,S47,S48,S49 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_s30_s49_bounded_turn5_postfix.json`
- observed behavior:
  - `20/20` scenarios passed
  - `100/100` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- repaired bounded evidence now cleanly covers the broader contiguous slice `S30-S49`
- this is the strongest bounded baseline window achieved so far and materially increases confidence before the next expansion toward the full suite

## 2026-05-11 - Broadened bounded live slice again to S20-S49, all 30 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after the corrected broader bounded slice `S30-S49` passed cleanly, the next task-list-aligned move was another contiguous expansion toward the front of the suite
- this checks whether the repaired bounded baseline still holds when adding the context and security scenarios `S20-S29`

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 1200 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S20,S21,S22,S23,S24,S25,S26,S27,S28,S29,S30,S31,S32,S33,S34,S35,S36,S37,S38,S39,S40,S41,S42,S43,S44,S45,S46,S47,S48,S49 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_s20_s49_bounded_turn5_probe.json`
- observed behavior:
  - `30/30` scenarios passed
  - `150/150` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- repaired bounded evidence now cleanly covers the contiguous slice `S20-S49`
- this is the broadest bounded live baseline window achieved so far and materially de-risks the next step toward the full suite

## 2026-05-11 - Broadened bounded live slice again to S10-S49, all 40 scenarios passed

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after `S20-S49` passed cleanly, the next contiguous expansion toward the full suite was to include `S10-S19`
- the first attempt revealed a practical ops issue rather than a product issue: the local service was down, so the suite could not start (`connection refused`)
- after restoring the local service, the broadened bounded rerun was repeated immediately

### Live rerun
- command:
  - `PYTHONUNBUFFERED=1 timeout 1500 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --scenarios S10,S11,S12,S13,S14,S15,S16,S17,S18,S19,S20,S21,S22,S23,S24,S25,S26,S27,S28,S29,S30,S31,S32,S33,S34,S35,S36,S37,S38,S39,S40,S41,S42,S43,S44,S45,S46,S47,S48,S49 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_s10_s49_bounded_turn5_probe.json`
- observed behavior:
  - `40/40` scenarios passed
  - `200/200` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- repaired bounded evidence now cleanly covers the contiguous slice `S10-S49`
- this is the broadest bounded live baseline window achieved so far and leaves only the final jump to the full 50-scenario suite

## 2026-05-11 - Final bounded full-suite rerun passed cleanly, 50/50 scenarios green

### Targets
- `docs/standard-install-model-detailed-task-list.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

### Trigger
- after `S10-S49` passed cleanly, the remaining task-list goal was the final bounded rerun across the full 50-scenario suite
- before launching, service reachability was checked explicitly to avoid the earlier connection-refused startup hiccup

### Live rerun
- precheck:
  - `curl -sf http://localhost:80/api/status`
- command:
  - `PYTHONUNBUFFERED=1 timeout 1800 .venv/bin/python3 tests/e2e/test_50_scenarios_20_turns_user_level.py --base-url http://localhost:80 --delay 0.5 --timeout 45 --wait-ready-seconds 5 --max-turns-per-scenario 5 --max-consecutive-failures 1 --output /tmp/e2e_full_50_bounded_turn5_probe.json`
- observed behavior:
  - `50/50` scenarios passed
  - `250/250` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### Outcome
- the repaired bounded live baseline now clears the entire 50-scenario suite
- this closes the bounded Phase 4 repair loop with full-suite evidence rather than partial-slice confidence only

## 2026-05-11 - Baseline evidence frozen after bounded full-suite green run

### Frozen truth set
- final full bounded suite report:
  - `/tmp/e2e_full_50_bounded_turn5_probe.json`
- key bounded progression reports:
  - `/tmp/e2e_s41_turn5_probe_429degrade.json`
  - `/tmp/e2e_system_subset_turn5_probe.json`
  - `/tmp/e2e_cross_subset_turn5_probe.json`
  - `/tmp/e2e_s41_s49_combined_turn5_probe.json`
  - `/tmp/e2e_s30_s49_bounded_turn5_postfix.json`
  - `/tmp/e2e_s20_s49_bounded_turn5_probe.json`
  - `/tmp/e2e_s10_s49_bounded_turn5_probe.json`
  - `/tmp/e2e_full_50_bounded_turn5_probe.json`

### Frozen bounded baseline summary
- `50/50` scenarios passed
- `250/250` executed turns succeeded
- `0` transport/service errors
- all scenario-end history checks passed
- this bounded full-suite result is the pre-install-model truth set for subsequent before/after comparison unless the acceptance contract is explicitly changed

## 2026-05-12 - Shared runtime path resolver slice

### Scope
Implemented the first install-model migration slice by introducing a shared runtime path resolver and wiring the initial control-plane/config surfaces to it.

### Code touched
- `app/runtime_paths.py`
- `app/cli.py`
- `app/ai/model_config_loader.py`
- `tests/unit/test_runtime_paths.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_model_config.py`

### Validation
- `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_cli.py tests/unit/test_model_config.py`
- result: `15 passed`

### Notes
This slice does not yet migrate all runtime writers off repo-local `data/...` defaults. It establishes the shared path contract first so later slices can replace those defaults incrementally instead of scattering path logic across subsystems.

## 2026-05-12 - Runtime/persistence default-path adoption wave

### Scope
Implemented the first adoption wave for Slice B by moving several runtime and persistence services off repo-local default paths and onto the shared runtime path resolver.

### Code touched
- `app/persistence/runtime_state_store.py`
- `app/system/runtime/app_data_store.py`
- `app/persistence/upgrade_log_service.py`
- `app/system/catalog/runtime_center.py`
- `app/system/catalog/resource_center.py`
- `app/system/runtime/config_center.py`
- `tests/unit/test_runtime_path_adoption.py`
- `tests/unit/api_test_helper.py`

### Validation
- `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py`
- result: `55 passed`

### Notes
This wave intentionally focused on constructor defaults. Explicit injected temp paths still take priority so existing tests and isolated runtime assembly continue to work. Remaining migration work can continue service-by-service until repo-local mutable state defaults are fully removed from production codepaths.

## 2026-05-12 - Runtime/persistence default-path adoption wave 2

### Scope
Expanded Slice B into more remaining mutable-state defaults while deliberately not crossing into asset-root migration too early.

### Code touched
- `app/persistence/persistence_service.py`
- `app/orchestration/pipeline_executor.py`
- `app/system/runtime/lifecycle.py`
- `app/bootstrap/runtime.py`
- `tests/unit/test_runtime_path_adoption_wave2.py`
- `tests/unit/api_test_helper.py`

### Validation
- `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py`
- result: `62 passed`

### Notes
This wave moved more mutable runtime defaults under the shared resolver, but explicitly stopped short of migrating `AssetCenter` installed/build roots and bootstrap `RuntimeCenter` persistence semantics. Those paths participate in asset-lifecycle and startup-asset assumptions that should be handled in a later, dedicated slice rather than folded into general persistence cleanup.

## 2026-05-12 - Runtime/persistence default-path adoption wave 3

### Scope
Closed another safe portion of Slice B by moving several remaining helper defaults from repo-local `data/...` assumptions to the shared runtime resolver, without changing the repo-curated path-definition bootstrap seam.

### Code touched
- `app/skills/generated_callable_materializer.py`
- `app/skills/skill_config_center.py`
- `app/persistence/path_store.py`
- `tests/unit/test_runtime_path_adoption_wave3.py`

### Validation
- `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py tests/unit/test_execution_chain_integration.py`
- result: `76 passed`

### Notes
`PathStore` now has an install-model-aware default, but bootstrap still explicitly points it at the repo-owned path asset directory. That is intentional for now because path definitions are still treated as authored control-plane assets rather than migrated runtime-installed assets.

## 2026-05-12 - Slice B tail rescan and closure signal

### Scope
Performed another grep-guided tail rescan and migrated the remaining straightforward mutable-state default found in `CoreOrchestrator`, then classified what is left as intentional migration-boundary behavior rather than generic default-path debt.

### Code touched
- `app/orchestration/core_orchestrator.py`
- `tests/unit/test_runtime_path_adoption_wave4.py`

### Validation
- `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py tests/unit/test_execution_chain_integration.py`
- result: `77 passed`

### Notes
At this point, the remaining repo-anchored path occurrences are predominantly deliberate:
- repo-authored path assets still pinned during bootstrap
- compatibility logic that still recognizes legacy `data/...` references during transition
This is a good stopping point for generic mutable-default cleanup.

## 2026-05-12 - Phase 6 planning handoff after Slice B closure

### Scope
After confirming Slice B generic mutable-default cleanup is effectively closed, I converted the remaining repo-anchored behavior into an explicit Phase 6 planning document instead of forcing premature path rewrites.

### Artifacts added
- `docs/phase-6-asset-control-plane-separation-plan.md`

### Planning outcome
- classified the remaining repo-anchored seams into:
  - repo-authored path-definition assets
  - `AssetCenter` installed/build roots
  - bootstrap `RuntimeCenter` persistence seam
  - legacy compatibility in `skill_asset_service.py`
- proposed the next Phase 6 work packages and recommended execution order
- recommended the next implementation slice as:
  - **Phase 6 Slice C1**: decide control-plane asset treatment and publish the concrete root map before moving live asset roots

### Validation
- planning/documentation only in this round; no new runtime codepaths changed

## 2026-05-12 - Phase 6 Slice C1 decision artifact

### Scope
Converted the Phase 6 planning seam into a concrete Slice C1 decision artifact so later asset-separation code changes can follow an explicit root map instead of re-deriving policy case by case.

### Artifacts added
- `docs/phase-6-slice-c1-root-map.md`

### Decision outcome
- repo-authored path definitions are treated as packaged built-in control-plane assets under the install model
- source/build/installed/runtime-registry roots are explicitly separated in the root map
- `RuntimeCenter` persistence migration is intentionally deferred until built-in asset bootstrap semantics are rewritten explicitly
- recommended next implementation order:
  - Slice C2 externalize installed asset root
  - Slice C3 package built-in control-plane assets
  - Slice C4 externalize runtime registry persistence

### Validation
- documentation-only round; no new runtime behavior changed

## 2026-05-12 - Phase 6 Slice C2 first live-code seam

### Scope
Started the first live-code move for installed asset externalization by teaching `AssetCenter` to default to install-model roots while preserving the current bootstrap compatibility wiring.

### Code touched
- `app/system/catalog/asset_center.py`
- `tests/unit/test_asset_center_install_model_roots.py`

### Validation
- `pytest -q tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
- result: `33 passed`

### Notes
This is intentionally a narrow first seam. `AssetCenter` is now install-model-aware by default, but bootstrap still passes repo-local installed/build roots so startup and built-in asset behavior remain unchanged until the next Phase 6 slice deliberately flips those callers.

### Additional Slice C2 adoption in non-bootstrap caller paths
- `SkillRegistryService` default installed root now resolves through the shared install-model path contract
- `CoreOrchestrator` now uses `AssetCenter`'s installed-root choice when wiring `SkillRegistryService`, instead of hardcoding `installed/`
- validation extension:
  - `pytest -q tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `35 passed`

### Slice C2 operator-facing inspection enhancement
- `app/cli.py` `runtime-layout` now exposes `asset_root_transition` with:
  - `installed_runtime_assets`
  - `build_artifacts`
  - `legacy_repo_installed`
  - `legacy_repo_build`
  - `bootstrap_status`
- this does not flip bootstrap behavior; it makes the transition state explicitly inspectable for operators and tests
- validation extension:
  - `pytest -q tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `44 passed`

### Slice C2 bootstrap-boundary inspection hardening
- added `describe_phase6_asset_bootstrap_binding(...)` in `app/bootstrap/runtime.py`
- runtime bootstrap now consumes that helper instead of inlining asset/data root wiring
- CLI `runtime-layout` now exposes `bootstrap_asset_binding` so operators can inspect the current bootstrap contract directly
- validation extension:
  - `pytest -q tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `45 passed`

### Slice C2 bootstrap flip preview contract
- `describe_phase6_asset_bootstrap_binding(...)` now supports:
  - `installed_assets_mode="current"`
  - `installed_assets_mode="install-model-preview"`
- CLI `runtime-layout` now exposes both:
  - `bootstrap_asset_binding`
  - `bootstrap_asset_binding_preview`
- this gives a concrete, testable preview of the first bootstrap installed/build root flip candidate while keeping runtime bootstrap on the current binding
- validation extension:
  - `pytest -q tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `46 passed`

### Slice C2 isolated bootstrap test seam before live flip
- added `tests/unit/bootstrap_test_helper.py` to build `build_runtime()` under injected config/home without relying on host-level `/root/.local/share/agentsystem/config/config.yaml`
- added `tests/unit/test_bootstrap_runtime_isolation.py`
  - verifies isolated bootstrap startup still reaches ready state
  - verifies current bootstrap binding differs from preview binding only on the intended installed/build asset seam while runtime-registry binding remains unchanged
- validation extension:
  - `pytest -q tests/unit/test_bootstrap_runtime_isolation.py tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `47 passed`

### Slice C2 first live bootstrap flip
- `app/bootstrap/runtime.py` now boots Phase 6 asset wiring from the install-model installed/build roots
- retained unchanged:
  - repo `source/`
  - repo `data/runtime_center.json`
- `app/cli.py` now reports:
  - live `bootstrap_asset_binding` -> install-model installed/build roots
  - `bootstrap_asset_binding_preview` -> prior repo-pinned asset binding as rollback/reference view
- validation extension:
  - `pytest -q tests/unit/test_bootstrap_runtime_isolation.py tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `47 passed`

### Slice C3 first built-in control-plane asset packaging seam
- added `materialize_builtin_path_definitions(...)` in `app/bootstrap/runtime.py`
- bootstrap now projects repo-authored `data/paths/*.yaml` into `installed_assets_dir/builtin_paths/`
- `PathStore` now loads built-in path definitions from that projected install-model location during bootstrap instead of reading repo `data/paths/` directly at runtime
- validation extension:
  - `pytest -q tests/unit/test_builtin_path_projection.py tests/unit/test_bootstrap_runtime_isolation.py tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `48 passed`

### Slice C3 built-in path projection metadata hardening
- `materialize_builtin_path_definitions(...)` now writes `builtin_paths_manifest.json`
- projected built-in path assets now carry an explicit packaged identity record:
  - `asset_id = builtin.control_plane.paths`
  - `asset_type = path`
  - `origin = repo_authored_projection`
  - projected file inventory
- validation extension remains:
  - `pytest -q tests/unit/test_builtin_path_projection.py tests/unit/test_bootstrap_runtime_isolation.py tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py`
  - result: `48 passed`
