# Phase H / Iteration E2E Test Results

## Record Template
- 场景:
- 输入:
- 主链路:
- 预期:
- 实际结果:
- 失配分类:
- 修复动作:
- 当前结论:
- 遗留问题:

---

## Iteration 10 ~ 12 v2 Regression Summary (2026-04-22)

### Iteration 10 - 北星目标 v2 场景实施
- 场景:
  - 复杂创建场景的澄清与需求累积
  - execute_action 回流执行
  - 权限和审批链路一致性
- 主链路:
  - `LightBrainGateway` → `LightBrainInterpreter` → clarification / pending context
  - `LightBrainGateway.execute_action` → command rebuild → `AppManagementWorker`
  - `LightBrainGateway` → `PolicyAuthorityService` → `AppManagementWorker`
- 对应测试:
  - `tests/e2e/test_iteration10_v2_scenarios_e2e.py`
- 实际结果:
  - 3/3 通过
- 当前结论:
  - v2 第一批用户主链路已具备可重复回归记录
- 遗留问题:
  - 仍需继续强化复杂创建场景在更长对话中的稳定性

### Iteration 11 - 修改链路 / skill 增减 / 状态一致性
- 场景:
  - refinement 与 skill add/remove
  - 修改后持久化 / 运行时状态一致性
  - 创建 → 修改 → 查询 / 执行回归
- 主链路:
  - `LightBrainGateway` → `RefinementWorker` → `RefinementOrchestrator`
  - `LightBrainGateway` → `AppManagementWorker` → `PersistenceService`
  - `LightBrainGateway` → `AppManagementWorker` → `RuntimeCenter`
- 对应测试:
  - `tests/e2e/test_iteration11_refinement_e2e.py`
- 实际结果:
  - 8/8 通过
- 当前结论:
  - v2 修改链路、skill 管理与状态一致性已进入稳定回归范围
- 遗留问题:
  - 需要后续把相关场景映射回更高层 testing docs 与 mismatch list

### Iteration 12 - 复杂创建稳定性与 v2 收尾回归
- 场景:
  - 多轮复杂创建需求累积稳定性
  - 澄清后的话题 refinement 连续性
  - create / modify / execute / approval 全量回归
- 主链路:
  - `LightBrainGateway` → `LightBrainInterpreter` → clarification / pending context 累积
  - create / modify / execute / query 主链路复验
- 对应测试:
  - `tests/e2e/test_iteration12_complex_creation_e2e.py`
- 实际结果:
  - 初版 async test 风格失败
  - 修正为同步测试包装后，6/6 通过
- 修复动作:
  - 使用 `asyncio.run(...)` 包装 gateway async 接口，保持与现有 pytest 模型一致
- 当前结论:
  - v2 场景已完成闭环收尾，并形成第二批可复验回归记录
- 遗留问题:
  - `pytest.mark.e2e` 未注册，仍有告警噪声

---

## H4 Validation Checkpoint (2026-04-22)

### H4-00 交互层直接答复路径
- 场景:
  - 用户触发内建直答类 intent 时，交互层直接本地回复，不进入 orchestrator / bridge child session 路径
- 输入:
  - `你好`
  - `帮助`
  - `系统状态`
- 主链路:
  - `LightBrainGateway.process_message()`
  - `LightBrainInterpreter.interpret()`
  - builtin intent 命中本地 handler
  - `_handle_greet / _handle_query_help / _handle_query_status`
  - `_after_reply(...)` 执行 reply 回写
- 预期:
  - 这类内建直答请求直接走本地 handler
  - 不调用 bridge/orchestrator
  - 最终仍完成统一 reply 回写
- 实际结果:
  - `greet / query_help / query_status` 在 bridge 可用时仍保持本地直答
  - `MockOrchestratorBridge.calls == []`
  - reply 正常返回，且仍进入统一 reply after-hook
- 失配分类:
  - 控制流失配
- 修复动作:
  - 用 gateway integration test 明确锁定 builtin direct-reply path 的旁路行为
- 当前结论:
  - H4 中“交互层直接答复路径”已有明确验证记录，不再空缺
- 遗留问题:
  - 后续若继续固化“单次 LLM 决策主路径”，仍需再检查 builtin intent 与模型路由边界是否需要进一步统一表述

### H4-01 交互层查上下文再答复路径
- 场景:
  - 交互层在已有 linked / child session context 的情况下解释用户消息，并把上下文沉淀为可消费的 command context
- 输入:
  - 用户在已有 app / refinement / child session 相关上下文后继续发起 `modify_app` / `query_app` 一类请求
- 主链路:
  - `LightBrainGateway.process_message()`
  - `LightBrainInterpreter._finalize_command(...)`
  - 从 `recent_session_context / linked_session_context / child_session_contexts` 生成 `context_hints`
  - 必要时从 child context 补 `target_app`
  - gateway 归一化回填 `target_app / context_hints / related_session_ids`
- 预期:
  - command 不只是保留原始意图，还能稳定携带与当前 App / 子会话相关的上下文线索
- 实际结果:
  - interpreter 已开始真实消费 linked / child context，而非只做被动透传
  - `context_hints` 已可稳定生成
  - `target_app` 已可从 child context 补全
  - gateway 已统一把这些字段回填到 command parameters
- 失配分类:
  - 状态模型失配
  - 接口契约失配
- 修复动作:
  - 在 interpreter finalize 阶段统一汇总 linked / child context
  - 在 gateway 层统一归一化回填 parameters
- 当前结论:
  - “查上下文再答复”已经从设计意图进入真实可消费主路径
- 遗留问题:
  - 仍需继续朝“当前消息 + 当前 session + 最近 100 条”的单次 LLM 决策模型进一步收口

### H4-02 交互层调主控并自动创建 child session 路径
- 场景:
  - 交互层收到 app 相关复杂请求后，自动 fork orchestration child session，并把 child session 纳入后续上下文链路
- 输入:
  - `create_app` / `modify_app` / `master_execute` / `list_apps` 等会进入 orchestration path 的请求
- 主链路:
  - `LightBrainGateway` / bridge / local child session wrapper
  - `RuntimeCenter` 建立 child session entity
  - `ContextCenter` 建立 child session context link
  - related session id 回流父链路
- 预期:
  - child session 创建、关联、回流行为一致，且后续交互能继续利用这些 child session context
- 实际结果:
  - bridge 侧 app 指令已可自动 fork orchestration child session
  - `master_execute` / `list_apps` / package / `modify_interactive_app` / `self_modify` 本地路径已切到统一 local child session 包装
  - `SessionLink` / child session 状态机已开始被真实主链消费
- 失配分类:
  - 控制流失配
  - 状态模型失配
- 修复动作:
  - 建立统一 child session 包装与 related link 回流
  - 在 command context 中补入 linked / child session context
- 当前结论:
  - “交互层调主控并自动创建 child session”主路径已基本成形，并已成为 Phase H context 的真实来源之一
- 遗留问题:
  - 仍需继续压缩旧 bridge / 本地兼容路径的残留分叉

### H4-03 主控 -> app -> skill 统一 session 契约路径
- 场景:
  - 主控、app、skill 在继续执行时统一遵循 `session_id` 非空续约、空值新建的规则，并能透传 related session context
- 输入:
  - app management / refinement / runtime asset method mapping / orchestrator closure 等调用链
- 主链路:
  - `Gateway -> AppManagementWorker / RefinementWorker / SystemAppRefinementWorker -> runtime asset refine_app -> AppRefinementOrchestratorService / AppRefinementService`
- 预期:
  - session 续约 / 新建规则一致，且跨 worker / orchestrator / runtime mapping 的上下文透传保持统一
- 实际结果:
  - `AppManagementWorker.query_app/modify_app` 已开始消费 `target_app/context_hints/related_session_ids`
  - `RefinementWorker.refine_app` 已兼容 `refine` / `refine_closure`
  - `SystemAppRefinementWorker` 与 runtime asset `refine_app` 已把这些字段透进 closure request 与 output
  - orchestrator / service 已把这些字段写入 compare summary、workflow inputs、release note、diagnostics
- 失配分类:
  - 模块边界失配
  - 接口契约失配
- 修复动作:
  - 统一 worker / runtime mapping / orchestrator 的字段透传契约
  - 让 refinement 内部开始真实消费这些字段，而非只做 passthrough
- 当前结论:
  - 主控 -> app -> skill 的 session/context 契约已经跨主要执行面连通
- 遗留问题:
  - 后续仍可继续清理未完全切走的旧执行分支，进一步固化单一主路径

### H4-04 context upload 回写正确性
- 场景:
  - 最终用户可见响应能够体现已注入并被消费的 Phase H context，而不是只在内部链路透传
- 输入:
  - `modify_app` 与 `query_app` 两条高频用户路径
- 主链路:
  - `AppCommandService.summarize_phase_h_context()`
  - `AppPresenter._append_context_summary()`
  - `AppCreateModifyExecutor`
  - `AppLifecycleQueryExecutor`
- 预期:
  - 最终 confirmation / success / degraded / detail 响应可带出 `target_app/context_hints/related_session_ids` 摘要
- 实际结果:
  - `AppCommandService` 已统一保留并汇总这批字段
  - `AppPresenter` 已在 confirmation / success / degraded / query detail 响应中追加“上下文摘要”
  - `modify_app` 高层路径已覆盖 confirm / degraded / success
  - `query_app` 高层路径已覆盖 detail / degraded
- 失配分类:
  - 接口契约失配
  - 可观测性失配
- 修复动作:
  - 建立统一 summary helper
  - 将 summary 真正接入最终 presenter 文案层
  - 增加 executor 级高层测试锁定最终响应
- 当前结论:
  - 当前 Phase H context 已经从“内部透传字段”变成“最终响应可见信息”，具备主链路可解释性
- 遗留问题:
  - 目前是调试型摘要展示，后续可继续产品化为更自然的最终交互文案

### H4 验证覆盖与结论
- 相关验证覆盖:
  - `tests/unit/test_light_brain.py`
  - `tests/unit/services/test_context_center.py`
  - `tests/test_runtime_center.py`
  - `tests/unit/test_runtime_asset_management_worker.py`
  - `tests/unit/test_runtime_asset_deeper_mappings.py`
  - `tests/unit/test_refinement_worker.py`
  - `tests/unit/test_system_app_refinement_worker.py`
  - `tests/unit/test_app_refinement_orchestrator.py`
  - `tests/unit/test_app_refinement_service.py`
  - `tests/unit/test_app_command_service.py`
  - `tests/unit/test_app_presenter.py`
  - `tests/unit/test_app_create_modify_executor.py`
  - `tests/unit/test_app_lifecycle_query_executor.py`
- 最终验证命令:
  - `pytest -q tests/unit/test_app_lifecycle_query_executor.py tests/unit/test_app_create_modify_executor.py tests/unit/test_app_presenter.py tests/unit/test_app_command_service.py tests/unit/test_app_refinement_orchestrator.py tests/unit/test_app_refinement_service.py tests/unit/test_runtime_asset_deeper_mappings.py tests/unit/test_refinement_worker.py tests/unit/test_system_app_refinement_worker.py tests/unit/test_runtime_asset_management_worker.py tests/unit/test_light_brain.py tests/unit/services/test_context_center.py tests/test_runtime_center.py`
- 结果:
  - `96 passed`
- 当前结论:
  - H4 中“查上下文再答复”“调主控自动创建 child session”“主控 -> app -> skill 统一 session 契约”“context 回写可解释”这几条主验证面已具备可复验记录
- 遗留问题:
  - 尚未形成真实外部用户脚本驱动的 full E2E 运行窗口验证
  - 交互层“直接答复路径”仍需补更明确的验证记录
  - 统一 context upload after-hook 仍待进一步固化

---

## H2 Discovery Slice Checkpoint
- 场景: 运行态核心资产注册与发现工具接线
- 输入: Runtime bootstrap loads core services, Gateway exposes runtime asset tools
- 主链路: `build_runtime -> RuntimeCenter register core assets -> ToolRegistry expose list/query/call asset tools -> LightBrainGateway handle runtime asset tool intents`
- 预期:
  - 核心服务注册为运行态资产
  - Gateway 能承接 `list_assets / query_asset_info / call_asset_method`
  - AssetToolExecutor 基于 RuntimeCenter 返回运行态信息
- 实际结果:
  - 已注册 `master_control / config_center / runtime_center / model_router / tool_calling_engine / light_brain_gateway`
  - Gateway 已挂接运行态资产工具处理器
  - AssetToolExecutor 已从 system catalog 切换为 RuntimeCenter
  - `call_asset_method` 已可真实映射到 `model_router.resolve_model / config_center.get_config / gateway.list_assets`
  - `light_brain_gateway` 已在 bootstrap 主链中完成正式运行态注册
  - runtime asset intent 已从粗 regex 升级为基于 tool registry 的轻量 tool-aware 解析
  - runtime worker 资产已扩展注册到 `app_management_worker / user_manager / refinement_worker / package_manager`
  - `call_asset_method` 已扩展覆盖 worker 与 package/refinement 面的 `list_apps / query_app / start_app / stop_app / delete_app / uninstall_app / list_users / show_permissions / refine_app / package_list_installed / package_search / package_build / package_install / package_uninstall / package_rollback`
  - runtime asset call 返回契约已统一收敛到 `ok / result / error / error_type / state_change / audit_ref / raw_result`
  - `query_asset_info` 与 `query_asset_detail` 已开始收敛出 descriptor vs expanded detail 的语义边界 (`detail_level`)
  - expanded detail 已补 `capability_methods / parameter_hints / capability_notes / usage_notes / invoke_examples`，且 invoke examples 已开始 capability-aware
  - incomplete runtime asset method intent 已收敛为 clarification，而不是直接掉入错误 handler
  - 已补 gateway/interpreter/runtime-asset focused E2E，覆盖 success path / failure path / detail path / clarification path / missing-method path
  - 补充了 21 个 focused tests，并通过 `21 passed`
  - 兼容加载旧 runtime data，旧 `running` 状态与缺失字段可转为新契约
- 失配分类:
  - 部分旧资产查询仍保留 static catalog 回退语义
  - interpreter 对 runtime asset intent 仍是基础 regex 级别
- 修复动作:
  - 增加正式 runtime asset tools
  - 在 Gateway 默认工具表中暴露 runtime asset intents
  - RuntimeCenter 增加 method mapping 与 legacy runtime entry 迁移加载
  - 统一 `query_asset_detail` 优先走 runtime contract
- 当前结论:
  - H2.2/H2.3 已从设计态进入可调用骨架态，并完成首批真实方法映射
  - 运行态资产发现, 查询, 调用三段链路已打通
  - gateway 资产注册已进入 bootstrap 正式主链，并有 focused test 锁定
  - interpreter 对 runtime asset intent 已不再只靠硬编码 regex，开始受 tool registry 驱动
  - runtime-facing worker, lifecycle write path, package/refinement 层已进入资产映射覆盖面，调用面显著扩展
  - runtime asset call 的返回契约已开始统一，整链联动测试已覆盖到 gateway -> interpreter -> runtime asset call，并补到了关键 failure path
  - `query_asset_info` / `query_asset_detail` 已开始摆脱双轨混用，转向 descriptor vs expanded detail 分层
  - expanded detail 已从空壳说明走向可实际消费的调用提示层
  - incomplete runtime asset call 已开始从硬错误改为 clarification，交互边界更接近最终形态
- 遗留问题:
  - 当前 invoke examples 已开始 capability-aware，但仍主要依赖方法名启发式，后续可继续接 schema 级样例生成
  - 当前 focused E2E 已明显扩开，但仍不等于完整系统运行窗口下的端到端验证
  - 后续还可以把更多 worker / orchestration surface 纳入统一 runtime asset method contract
