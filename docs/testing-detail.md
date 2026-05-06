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
- HTTP acceptance 对 recent working memory 与 continuation recovery payload 的验证
- service-up E2E 脚本已扩展 context-view / restart-style recovery 探针，完整跑绿仍受外部模型可用性影响

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
