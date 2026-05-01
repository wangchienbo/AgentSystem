# AgentSystem Task List - Asset-Centered Operating Runtime Rewrite

> 本文件不是补丁式 backlog，而是 **Asset-Centered Operating Runtime 大改框架** 的执行任务单。
> 目标不是继续修旧 gateway/tool-call 链，而是直接把运行时骨架切到：
> - 资产中心唯一元信息入口
> - 模型资源统一治理
> - 资产自描述/自注册
> - 受控三分支交互协议
> - 启动顺序成为正式运行时约束

---

## 0. 本轮目标

- [ ] 建立资产中心最小骨架
- [ ] 建立模型资源层最小骨架
- [ ] 建立启动编排器与硬启动顺序
- [ ] 定义标准资产 descriptor / 注册协议
- [ ] 让 self-iteration 成为第一批标准资产
- [ ] 重写交互层为 summary/detail/invoke 三分支协议
- [ ] 删除旧模型可见资产查询工具面
- [ ] 建立新主链测试并删除旧兼容回归

---

## Phase 1, 定义系统底座
- [ ] 定义 `system_bootstrap.yaml` 最小 schema
- [ ] 定义 `model_pool.yaml` 最小 schema
- [ ] 定义 asset descriptor v1 schema
- [ ] 定义 model requirement v1 schema
- [ ] 定义 interaction decision envelope v1 schema

## Phase 2, 建立资产中心
- [ ] 新增 `app/system/asset_center/models.py`
- [ ] 新增 `app/system/asset_center/registry.py`
- [ ] 新增 `app/system/asset_center/service.py`
- [ ] 新增 `app/system/asset_center/bootstrap.py`
- [ ] 实现 register/list/detail/model-requirement 最小能力
- [ ] 为 descriptor 加入 version 字段与最低必填约束

## Phase 3, 建立模型资源层
- [ ] 新增 `app/system/model_runtime/model_pool_loader.py`
- [ ] 新增 `app/system/model_runtime/model_client_registry.py`
- [ ] 新增 `app/system/model_runtime/model_probe.py`
- [ ] 新增 `app/system/model_runtime/model_selector.py`
- [ ] 实现 preferred/minimum/fallback 三段模型选择
- [ ] 实现模型资源注册到资产中心

## Phase 4, 建立资产协议与首批资产
- [ ] 新增 `app/system/assets/base_asset.py`
- [ ] 新增 `app/system/assets/descriptor_builder.py`
- [ ] 新增 `app/system/assets/registration_protocol.py`
- [ ] 迁移 self-iteration 为标准注册资产
- [ ] 视需要迁移 runtime_center 为第二试点资产
- [ ] 统一 summary/detail/methods/model_requirement 同源生成

## Phase 5, 建立启动编排器
- [ ] 新增 `app/system/startup/startup_orchestrator.py`
- [ ] 固化启动顺序: env -> asset_center -> model_runtime -> system_assets -> interaction_runtime -> entrypoints
- [ ] 实现 required asset 检查
- [ ] 实现 fail-fast 启动失败路径
- [ ] 设计局部重注册/局部恢复最小机制

## Phase 6, 重写交互运行时
- [ ] 新增 `app/system/interaction_runtime/context_assembly.py`
- [ ] 新增 `app/system/interaction_runtime/decision_protocol.py`
- [ ] 新增 `app/system/interaction_runtime/interaction_orchestrator.py`
- [ ] 重写 `tool_calling_interpreter.py` 为兼容壳或直接退役
- [ ] 移除模型可见 `list_assets/query_asset_info/query_asset_detail`
- [ ] 固定三分支输出: text / need_asset_detail_id / invoke

## Phase 7, 建立统一调用层
- [ ] 新增 `app/system/invocation/invocation_dispatcher.py`
- [ ] 新增 `app/system/invocation/model_resolved_call.py`
- [ ] 执行前统一解析 asset model requirement
- [ ] 首选失败时按 fallback 策略降级
- [ ] 最低语义能力不满足时明确失败

## Phase 8, 新测试与旧测试清理
- [ ] 新增资产中心 registry 单测
- [ ] 新增 descriptor/schema 单测
- [ ] 新增模型选择/fallback 单测
- [ ] 新增启动顺序/required assets 单测
- [ ] 新增 self-iteration 新主链集成测试
- [ ] 新增简单低歧义试点资产测试
- [ ] 删除旧模型可见资产查询工具回归
- [ ] 删除旧 bounded-route 兼容测试

## Phase 9, 文档与收口
- [ ] 新增 `docs/asset-centered-runtime-redesign.md`
- [ ] 更新 `docs/design.md`
- [ ] 更新 `docs/system-relationship-map.md`
- [ ] 更新 `docs/testing.md`
- [ ] 更新 `docs/development-log.md`
- [ ] 提交首个设计模块边界 commit

---

## 风险护栏
- [ ] 资产中心不得承担业务执行
- [ ] descriptor 必须 versioned
- [ ] summary/detail/methods/model_requirement 必须同源生成
- [ ] fallback 不得跨越最低语义能力门槛
- [ ] 必须保留开发者调试/观测视图
- [ ] 必须设计运行中重注册与局部恢复
- [ ] 至少保留一个简单试点资产，避免只用 self-iteration 误判架构问题
