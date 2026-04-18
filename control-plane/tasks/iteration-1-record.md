
## Iteration 1 deep dive — modify_app main path

### Current modify_app control flow (v1)
1. 用户消息进入 `light_brain_gateway.process_message`
2. interpreter 产出 `InterpretedCommand(intent="modify_app", ...)`
3. `_execute_command()` 分发到 `_handle_modify_app()`
4. `_handle_modify_app()` 分三段：
   - `requires_clarification=True`：返回澄清问题
   - `confirmed=False`：先返回确认框
   - `confirmed=True`：进入 `_execute_modify_app()`
5. `_execute_modify_app()` 先做 `_check_app_modify_permission()`
6. 若 refinement orchestrator 未注入，直接返回“功能尚未完全启用”提示
7. 若有 MessageBus，则优先 RPC 到 `system.app_refinement`
8. refinement RPC 分两步：
   - `dry_run`：分析是否需要新 skill
   - `refine`：真正执行修改
9. gateway 根据 dry_run 结果决定是否因权限不足而拦截，并在 refine 成功后返回成功摘要

### modify_app deep mismatches
#### 1. 控制流失配
- [ ] modify_app 与 create_app 一样，真实主路径已经强绑定到 `MessageBus -> system.app_refinement`，但 gateway 里仍残留一整段不可达 legacy orchestrator 直调逻辑。
- [ ] 当前 modify_app 表面上像 gateway 的本地 handler，实际已经是“gateway 做确认 + 权限 + dry-run，再交给 refinement worker”的厚路径。
- [ ] 这说明 modify_app 的真实主路径与历史 fallback 也没有完全清干净。

#### 2. 契约失配
- [ ] gateway 发给 refinement worker 的输入结构是：`app_id / description / new_features / user_id`。
- [ ] 但 `SystemAppRefinementWorker` 内部用的是 `AppRefinementRequest`，而 orchestrator/service 真实签名接的是 `SuggestedSkillRefinementClosureRequest` / `SuggestedSkillRefinementClosureResult` 体系。
- [ ] worker 里直接 `from app.models.app_refinement import AppRefinementRequest`，但当前模型文件里可见的是 `SuggestedSkillRefinementClosureRequest`，这暴露出请求模型命名/版本很可能已经漂移。

#### 3. 权限失配
- [ ] modify_app 的权限门控比 create_app 更完整，至少主路径里已经有 `_check_app_modify_permission()` 和 dry-run 后的 `can_create_skills` 二次门控。
- [ ] 但这也意味着 create_app 和 modify_app 两条主链路的权限模型并不对称，同样涉及“会不会创建新 skill”，一条在主路径里做，一条还漂在旧分支里。
- [ ] `_check_app_modify_permission()` 依赖 user service 和 app owner role，但是否与 delete_app / create_app / execute_action 共享统一门控规则，还未统一。

#### 4. 降级失配
- [ ] 若 `_app_refinement_orchestrator` 未注入，modify_app 会返回“功能未完全启用”，属于弱降级。
- [ ] 但一旦 MessageBus 存在且 RPC 报错，当前直接返回错误文本，而不是回落到本地 orchestrator 或确认后挂起状态。
- [ ] 这和文档中的“refinement orchestrator 不可用时应友好降级”相比，还不够系统化。

#### 5. 状态与确认协议失配
- [ ] modify_app 的确认框 payload 用的是 `target_app / modification / confirmed=True`，而 create_app 的确认 payload 则是 `app_name / app_type / parameters / confirmed=True`，确认协议风格并不统一。
- [ ] execute_action 对 create/start/stop/delete 有专门 confirmed 分支，但 modify_app 当前主要走 `process_message` 和 `_handle_modify_app` 内部确认协议，按钮回流协议需要统一核对。

#### 6. 实现边界失配
- [ ] gateway 同时承担了修改确认 UI、权限判断、dry-run skill 需求分析结果解释、refine 成功摘要展示等职责。
- [ ] worker/orchestrator/service 则负责 suggested-skill 分析、blueprint/register/install/run 等实现闭环。
- [ ] 这导致修改链路的“用户语义层”和“实现闭环层”边界也偏厚，失败后难以区分是权限失败、分析失败、refine 失败，还是安装/执行失败。

### create_app vs modify_app comparison
#### 已确认的共同问题
- [ ] 都存在“当前主 RPC 路径 + 不可达 legacy 旧路径”并存问题
- [ ] 都有 gateway / worker / orchestrator / service 多层链路叠加问题
- [ ] 都缺少真正统一的降级策略视图
- [ ] 都缺少统一的请求/响应契约定义文档

#### 已确认的差异
- [ ] modify_app 主路径里的权限门控明显强于 create_app
- [ ] create_app 主路径的降级更差，RPC 失败后基本直接 error
- [ ] modify_app 已有 dry-run → decide → refine 结构，而 create_app 没有把“是否需要新 skill”显式拆成主路径阶段

### First adaptation priorities (v1)
#### Priority A — 主路径统一重构
- [ ] 抽统一的 AppCommand / AppCommandResult contract
- [ ] 抽统一的 AppCommandRouter / AppCommandService
- [ ] 先把 create_app / modify_app 纳入统一 command layer
- [ ] 再逐步把 gateway 中分散的 confirmed / permission / degrade 分支迁出

#### Priority B — create/modify 结构收敛
- [x] 先修复 `system.meta_app` worker 对 `AppCreationFromMetaAppRequest` 的字段漂移，避免 RPC 请求模型与 orchestrator 模型直接错位
- [x] 把 create_app 中不可达 legacy create 路径清掉
- [x] 把 create_app 的“需要新 skill”权限门控迁回当前主路径
- [x] 开始统一 create / modify 的 confirmed payload 协议
- [ ] 统一 gateway → worker → orchestrator 的请求模型
- [ ] 统一 create / modify 的降级语义

#### Priority C — 权限与状态模型重构
- [ ] 抽统一 AppOperationPolicy，替代复用 `_check_app_modify_permission()` 控制多类操作
- [ ] 设计 active skill / 多轮状态的持久化表示
- [ ] 对齐 session / command replay / action replay 的恢复边界

#### Priority D — lifecycle / query 对齐
- [ ] 统一 list/query/start/stop/pause/resume 调用入口
- [ ] 对齐 AppCatalog / RuntimeCenter / lifecycle 的状态语义
- [ ] 统一 query/list 返回模型

### Progress update
- [x] 已切换策略：由于系统尚未上线，当前工作流从保守修补切换为允许大改的主路径统一方案。
- [x] 已新增结构性方案文档：`control-plane/tasks/app-command-unification-plan.md`
- [x] 已完成第一个最小改造点：修复 `app/system/workers/system_meta_app_worker.py`，把 `app_goal/app_type/features/constraints` 错位映射改为 `goal/app_kind/scope/context/workflow_inputs`，与 `AppCreationFromMetaAppRequest` 当前模型对齐。
- [x] 已完成第二个最小改造点：清理 `app/system/gateway/light_brain_gateway.py::_execute_create_app` 中不可达 legacy create_app 路径，并把“需要新 skill”时的权限门控迁回当前主 RPC 路径。
- [x] 已完成第三个最小改造点：统一 create/modify 的确认协议入口，`execute_action()` 现在同时支持 `create_app` 和 `modify_app` 的 confirmed 回流，`modify_app` 确认按钮 payload 也开始对齐到统一 `target_app + parameters + confirmed` 结构。
- [x] 已完成第四个最小改造点：补 `app/system/gateway/light_brain_interpreter.py` 中 create_app 的确认按钮 payload 生成点，使 create_app 也开始走统一 `target_app + parameters + confirmed` 协议。
- [x] 已完成第五个最小改造点：新增 `app/models/app_command.py` 与 `app/services/app_command_service.py`，开始建立统一 AppCommand / AppCommandResult / AppCommandService 雏形，给 gateway 和后续 command layer 收敛提供明确接缝。
- [x] 已完成第六个最小改造点：`app/system/gateway/light_brain_gateway.py::execute_action()` 中 create_app / modify_app 的 confirmed rebuild 已开始接入 `AppCommandService.build_command(...)`，command layer 从定义层进入真实入口层。
- [x] 已完成第七个最小改造点：`app/services/app_command_service.py` 已新增 `normalize_confirmed_params(...)` 与 `rebuild_interpreted_command(...)`，`light_brain_gateway.py::execute_action()` 现在复用 command layer 做 confirmed payload 标准化与命令重建，进一步减少 gateway 内联协议细节。
- [x] 已完成第八个最小改造点：`app/services/app_command_service.py` 已新增 `build_confirmation_actions(...)`，`_handle_modify_app()` 的确认按钮生成开始迁出 gateway，向 command presenter / policy 边界继续收敛。
- [x] 已完成第九个最小改造点：`app/services/app_command_service.py` 已新增 `build_confirmation_response(...)`，`_execute_create_app()` 现在在未确认时走统一的 create_app 确认响应生成，create/modify 两条主链路都开始复用 command layer 的确认表现层能力。
- [x] 已完成第十个最小改造点：`app/services/app_command_service.py` 已新增 `from_interpreted_command(...)`，`_execute_create_app()` 与 `_handle_modify_app()` 现在开始复用 `requires_confirmation(...)` 做确认判定，requires_confirmation 判断从 gateway 的零散字段判断开始收口到 command layer。
- [x] 已完成第十一个最小改造点：`app/services/app_command_service.py` 已新增 `build_degraded_response(...)`，create_app / modify_app 在 MessageBus 缺失、RPC 调用失败、refinement orchestrator 缺失时开始复用统一降级响应构造，降级语义开始收敛。
- [x] 已完成第十二个最小改造点：`app/services/app_command_service.py` 已新增 `build_permission_denied_response(...)` 与 `build_success_response(...)`，create_app / modify_app 的权限失败与成功响应开始复用统一构造，进一步收敛主链路语义。
- [x] 已完成第十三个最小改造点：`app/services/app_command_service.py` 已新增 `build_confirmation_content(...)`，create_app / modify_app 的确认文案开始经由统一 presenter 风格接口生成，gateway 中的确认文案内联逻辑继续减少。
- [x] 已完成第十四个最小改造点：`app/services/app_command_service.py` 已新增 `build_query_detail_response(...)`，`start_app` / `stop_app` / `query_app` 开始复用统一 success / degraded / detail response 构造，lifecycle/query 的 response contract 开始收口。
- [x] 已完成第十五个最小改造点：`pause_app` / `resume_app` 的已暂停、已运行、状态不匹配、成功执行、RPC 失败、MessageBus 缺失等响应已开始复用 `AppCommandService` 的统一 success / degraded response 构造，lifecycle 主链路进一步收口。
- [x] 已完成第十六个最小改造点：新增 `app/services/app_command_presenter.py`，把 confirmation / degraded / success / query detail / permission denied 等 presenter 相关能力从 `AppCommandService` 中迁出，`AppCommandService` 现在改为组合 `AppCommandPresenter`，开始形成更清晰的 service + presenter 边界。
- [x] 已完成第十七个最小改造点：新增 `app/services/app_command_policy.py`，把 `requires_confirmation(...)` 规则从 `AppCommandService` 中迁到独立 policy 层，`AppCommandService` 开始组合 `AppCommandPolicy + AppCommandPresenter`，主控层内部边界继续清晰化。
- [x] 已完成第十八个最小改造点：新增 `app/services/app_command_router.py`，把 app 域 intent → handler 的映射从 `light_brain_gateway.py` 混合 handler 表中抽出，`LightBrainGateway` 现在优先通过 `AppCommandRouter` 分发 create/start/stop/pause/resume/query/modify/delete 等 app intent，开始形成更明确的 app-domain router 边界。
- [x] 已完成第十九个最小改造点：新增 `app/services/app_list_presenter.py`，把 `list_apps` 的空状态与列表响应构造从 `light_brain_gateway.py` 中迁出，app 列表展示也开始纳入 app-domain presenter 体系。
- [x] 已完成第二十个最小改造点：`query_status` 中的 app 状态卡片、系统总览卡片与状态查询失败降级，已开始分别复用 `AppListPresenter` 与 `AppCommandService` 的统一 presenter / degraded response 能力，app-domain 展示层收口继续推进。
- [x] 已完成第二十一个最小改造点：新增 `app/services/app_presenter.py`，并删除 `app/services/app_command_presenter.py` 与 `app/services/app_list_presenter.py`，将 command/list/status 的展示能力统一合并到单一 `AppPresenter` 中；`AppCommandService` 与 `LightBrainGateway` 已切换为复用统一 presenter，app-domain 展示层开始真正收口。
- [x] 已完成第二十二个最小改造点：`AppCommandPolicy` 已新增 `can_pause_from_status(...)` 与 `can_resume_from_status(...)`，pause/resume 的状态规则开始从 gateway 条件判断迁到 policy 层，app-domain 的状态语义继续从 gateway 向 policy/application layer 收口。
- [x] 已完成第二十三个最小改造点：`AppCommandPolicy` 已新增 `can_create_required_skills(...)`，create_app / modify_app 对“是否允许创建新 skill”的规则判断开始从 gateway 直接字段判断迁到 policy 层，权限语义继续从 gateway 向 policy 收口。
- [x] 已完成第二十四个最小改造点：`AppCommandRouter` 已新增 `handles(...)`，`LightBrainGateway::_execute_command()` 现在显式先判断某个 intent 是否属于 app-domain 再分发给 app router，app-domain 入口边界开始从“查 handler 命中”提升为更明确的 router ownership 判定。
- [x] 已完成第二十五个最小改造点：新增 `app/services/app_application_service.py`，并让 `LightBrainGateway` 把 create/start/stop/pause/resume/query/modify/delete 等 app-domain intent 统一交给 `AppApplicationService` 入口处理；app-domain 已从“router + components”阶段切入真正的 application layer 接管阶段。
- [x] 已完成第二十六个最小改造点：新增 `app/services/app_lifecycle_query_executor.py`，并先把 `start_app` / `stop_app` 的真实执行逻辑从 gateway 迁到 executor；`AppApplicationService` 现已开始注册 executor 而不是纯 gateway handler，执行接管正式开始。
- [x] 已完成第二十七个最小改造点：`pause_app` / `resume_app` / `query_app` / `list_apps` 已迁入 `AppLifecycleQueryExecutor`，lifecycle/query 这一组主执行链已大部分从 gateway 切出；`AppApplicationService` 现在对这批 intent 注册 executor 而非 gateway handler，执行接管继续扩大。
- [x] 已完成第二十八个最小改造点：新增 `app/services/app_create_modify_executor.py`，并把 `create_app` / `modify_app` 的确认与主执行链迁入 executor；`AppApplicationService` 已开始对 create/modify 注册 executor，第三刀重头戏已正式切入。
- [x] 已完成第二十九个最小改造点：已从 `app/system/gateway/light_brain_gateway.py` 删除 `_handle_start_app` / `_handle_stop_app` / `_handle_pause_app` / `_handle_resume_app` / `_handle_query_app` / `_handle_modify_app` / `_execute_modify_app` 等已被 executor 接管的残留厚 handler；gateway 中 app-domain 历史双份执行逻辑已明显收缩。
- [x] 已完成最小验证：`python3 -m py_compile app/system/workers/system_meta_app_worker.py app/system/gateway/light_brain_gateway.py app/system/gateway/light_brain_interpreter.py app/models/app_command.py app/services/app_command_service.py app/services/app_command_policy.py app/services/app_command_router.py app/services/app_presenter.py app/services/app_application_service.py app/services/app_lifecycle_query_executor.py app/services/app_create_modify_executor.py`
- [ ] 下一步：继续清理 create_app legacy 残留、收口 delete/list ownership，并进一步减少 gateway 直接构造 app-domain response

