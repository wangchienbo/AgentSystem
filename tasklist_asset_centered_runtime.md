# AgentSystem Task List - Asset-Centered Operating Runtime Rewrite

> 本文件不是补丁式 backlog，而是 **Asset-Centered Operating Runtime 大改框架** 的执行任务单。
> 目标不是继续修旧 gateway/tool-call 链，而是直接把运行时骨架切到：
> - 资产中心唯一元信息入口
> - 模型资源统一治理
> - 资产自描述/自注册
> - 受控三分支交互协议
> - 启动顺序成为正式运行时约束
>
> 执行规则：
> - 所有阶段任务都收在这一份总清单里，不再拆分独立 phase 文件
> - 先立新主链，再删旧兼容
> - 先补新验证，再删旧测试
> - 每个阶段都要明确：文件落点、关键约束、验收点、清理项

---

## 0. 总目标

- [ ] 建立资产中心最小骨架
- [ ] 建立模型资源层最小骨架
- [ ] 建立启动编排器与硬启动顺序
- [ ] 定义标准资产 descriptor / 注册协议
- [ ] 让 self-iteration 成为第一批标准资产
- [ ] 重写交互层为 summary/detail/invoke 三分支协议
- [ ] 删除旧模型可见资产查询工具面
- [ ] 建立新主链测试并删除旧兼容回归

---

## 1. 总体护栏与完成标准

### 1.1 架构硬约束
- [ ] 资产中心只做索引/查询/解析，不承担业务执行
- [ ] descriptor 必须 versioned
- [ ] summary/detail/methods/model_requirement 必须同源生成
- [ ] fallback 不得跨越最低语义能力门槛
- [ ] 必须保留开发者调试/观测视图
- [ ] 必须设计运行中重注册与局部恢复
- [ ] 至少保留一个简单低歧义试点资产，避免只用 self-iteration 误判架构问题

### 1.2 新主链完成定义
- [ ] 资产中心可先启动并 ready
- [ ] 模型资源层可读取外部配置并注册模型资源
- [ ] self-iteration 可作为标准资产注册 descriptor
- [ ] 交互层可通过资产中心读取 summary/detail
- [ ] 模型可输出 `text / need_asset_detail_id / invoke`
- [ ] 调用前可按资产 model requirement 解析模型
- [ ] 首选模型失败时可 fallback
- [ ] 最终回答可闭环返回

### 1.3 旧链清理总原则
- [ ] 不再保留模型可见 `list_assets/query_asset_info/query_asset_detail`
- [ ] 不再继续扩写旧 gateway bounded-route patch 逻辑
- [ ] 不再新增旧语义下的兼容测试
- [ ] 所有旧路径清理必须在新主链测试可跑后进行

---

## 2. Phase 1 - 定义系统底座

### 2.1 配置与 schema
- [x] 定义 `config/system_bootstrap.yaml` 最小 schema
- [x] 定义 `model_pool.yaml` 最小 schema（以 `config/model_pool.local.example.yaml` 示例形式落库）
- [x] 定义 asset descriptor v1 schema
- [x] 定义 model requirement v1 schema
- [x] 定义 interaction decision envelope v1 schema

### 2.2 文件与文档落点
- [x] 在 `docs/asset-centered-runtime-redesign.md` 中固定 schema 字段清单
- [x] 在总任务单中固定 required fields 与 optional fields
- [x] 为 descriptor version / additive extension 规则留出章节

### 2.3 验收点
- [x] bootstrap config 足以定位 asset center 与 model config path
- [x] descriptor 字段最小集明确，不依赖 chat 记忆补解释
- [x] decision envelope 三分支语义无歧义

---

## 3. Phase 2 - 建立资产中心

### 3.1 新增模块
- [x] 新增 `app/system/asset_center/models.py`
- [x] 新增 `app/system/asset_center/registry.py`
- [x] 新增 `app/system/asset_center/service.py`
- [x] 新增 `app/system/asset_center/bootstrap.py`

### 3.2 数据结构
- [x] 定义 `AssetDescriptorRecord`
- [x] 定义 `AssetMethodSpec`
- [x] 定义 `AssetModelRequirement`
- [x] 定义 registry 存储结构
- [x] 定义 descriptor version 字段与最低必填校验

### 3.3 最小能力
- [x] 实现 `register_asset()`
- [x] 实现 `list_assets()`
- [x] 实现 `get_asset_detail(asset_id)`
- [x] 实现 `get_asset_model_requirement(asset_id)`
- [x] 为后续模型资源注册预留 `list_models()` 接口或视图

### 3.4 边界控制
- [x] 明确禁止 asset center 直接执行业务方法
- [x] 明确禁止把模型 client 初始化逻辑塞进 asset center
- [x] 明确禁止把交互 prompt 组装逻辑塞进 asset center

### 3.5 局部恢复与注册一致性
- [ ] 设计 descriptor 替换规则
- [ ] 设计同 asset_id 重注册行为
- [ ] 设计 stale descriptor 的最小处理策略
- [ ] 设计 startup epoch / instance 标识是否需要进入 v1

### 3.6 验收点
- [x] 可启动独立 asset center
- [x] descriptor 可注册和查询
- [ ] 重复注册行为可预测
- [x] asset center 仍保持轻中心边界

---

## 4. Phase 3 - 建立模型资源层

### 4.1 新增模块
- [x] 新增 `app/system/model_runtime/model_pool_loader.py`
- [x] 新增 `app/system/model_runtime/model_client_registry.py`
- [x] 新增 `app/system/model_runtime/model_probe.py`
- [x] 新增 `app/system/model_runtime/model_selector.py`

### 4.2 配置读取与初始化
- [x] 读取外部 `model_pool.yaml`
- [x] 校验 default/fallback model 是否存在
- [x] 初始化 provider/client 基础对象
- [x] 对每个模型执行最小连通性探测（以独立 probe 组件和单测先落地）
- [x] 生成 healthy/unhealthy 运行时视图

### 4.3 资产中心注册
- [x] 将可用模型注册为模型资源记录
- [x] 模型资源记录包含 model_id/provider/healthy/fallback role
- [x] 为 asset center 提供模型列表视图

### 4.4 模型解析逻辑
- [x] 实现 preferred model 命中逻辑
- [x] 实现 minimum requirements 检查
- [x] 实现 fallback model 选择逻辑
- [x] fallback 不满足最低要求时显式失败

### 4.5 边界控制
- [x] 第一版不做复杂 capability ontology
- [x] 第一版不做多维 latency/cost 评分
- [x] 第一版不做跨多个备选模型的深度排序系统

### 4.6 验收点
- [x] 外部模型配置可独立读取
- [ ] 至少两种模型资源可完成 probe 与注册
- [x] preferred/fallback 策略行为清晰可测

---

## 5. Phase 4 - 建立资产协议与首批资产

### 5.1 新增模块
- [x] 新增 `app/system/assets/base_asset.py`
- [x] 新增 `app/system/assets/descriptor_builder.py`
- [x] 新增 `app/system/assets/registration_protocol.py`

### 5.2 统一资产协议
- [x] 定义标准 asset boot 接口
- [x] 定义标准 descriptor build 接口
- [x] 定义标准 register 接口
- [ ] 定义标准 invoke 接口

### 5.3 descriptor 同源生成
- [x] summary/detail/methods/model_requirement 从同一 builder 输出
- [x] 禁止四处分散定义 summary/detail/methods/model_requirement
- [x] 约束 method naming、summary/detail 最小语义格式

### 5.4 首批资产迁移
- [x] 迁移 self-iteration 为标准注册资产
- [x] 为 self-iteration 提供 descriptor v1
- [ ] 视需要迁移 runtime_center 为第二试点资产
- [x] 选定一个简单低歧义试点资产进入首批集合（config_center）
- [x] 修正 self-iteration 在 gateway 中的稳定路由与专用渲染

### 5.5 运行中重注册
- [ ] 设计资产重启后的重新注册流程
- [ ] 设计 descriptor 更新后旧缓存如何失效
- [ ] 设计 interaction 侧 detail cache 失效策略的输入信号

### 5.6 验收点
- [x] self-iteration 可通过标准协议注册
- [x] descriptor 构造无分散真相源
- [x] self-iteration 详情/列表请求可稳定命中 runtime asset 渲染链路
- [x] 至少一个简单资产可作为辅助试点运行

---

## 6. Phase 5 - 建立启动编排器

### 6.1 新增模块
- [x] 新增 `app/system/startup/startup_orchestrator.py`

### 6.2 固化顺序
- [x] 固化启动顺序: env -> asset_center -> model_runtime -> system_assets -> interaction_runtime -> entrypoints
- [x] 明确 asset center ready 之后才允许 model runtime 注册
- [x] 明确模型资源 ready 之后才允许系统资产宣告 fully ready
- [x] 明确 interaction runtime 只能在 required assets ready 后启动

### 6.3 启动控制
- [x] 实现 required asset 检查
- [x] 实现 fail-fast 启动失败路径
- [x] 实现阶段日志输出
- [x] 实现最小 readiness barrier

### 6.4 局部恢复
- [x] 设计 model runtime 局部重启后的再注册
- [x] 设计单资产崩溃后的重注册与状态替换
- [ ] 设计 interaction runtime 是否需要感知 descriptor 更新

### 6.5 验收点
- [x] 冷启动顺序可重复复现
- [x] required asset 缺失时系统能明确失败
- [x] 局部重启至少有最小恢复路径定义

---

## 7. Phase 6 - 重写交互运行时

### 7.1 新增模块
- [x] 新增 `app/system/interaction_runtime/context_assembly.py`
- [x] 新增 `app/system/interaction_runtime/decision_protocol.py`
- [x] 新增 `app/system/interaction_runtime/interaction_orchestrator.py`

### 7.2 上下文装配
- [x] 从 asset center 拉可见 asset summaries
- [x] 拉取已缓存的 asset details
- [x] 定义 initial detail 载入策略
- [ ] 固定 context block 顺序
- [ ] 区分实时查询与会话级缓存

### 7.3 决策协议
- [x] 固定三分支输出: text / need_asset_detail_id / invoke
- [x] 非法 envelope 输出有明确错误处理
- [x] 重复请求已存在 detail 时有明确处理策略
- [x] 请求不存在 asset detail 时有明确处理策略

### 7.6 调试与观测
- [x] 设计开发者调试视图，能看每轮 loaded summaries/details
- [x] 设计开发者调试视图，能看模型为何请求 detail 或 invoke
- [ ] 设计开发者调试视图，能看最终 resolved model

### 7.7 验收点
- [x] self-iteration 问题可走新三分支链闭环
- [x] 简单试点资产可走低歧义闭环
- [x] 开发者仍可观测 decision/detail/invoke 过程

### 7.4 主入口重构
- [ ] 重写 `tool_calling_interpreter.py` 为兼容壳或直接退役
- [ ] 将旧 gateway 资产知识迁出
- [ ] 不再继续扩写旧 bounded-route prompt patch

### 7.5 旧工具面移除
- [ ] 移除模型可见 `list_assets/query_asset_info/query_asset_detail`
- [ ] 清理旧 asset-first prompt 暴露与 route patch 逻辑
- [ ] 清理旧 hot-tool bounded route 的兼容残留

---

## 8. Phase 7 - 建立统一调用层

### 8.1 新增模块
- [x] 新增 `app/system/invocation/invocation_dispatcher.py`
- [x] 新增 `app/system/invocation/model_resolved_call.py`

### 8.2 执行前解析
- [x] 校验 asset_id/method/params
- [x] 执行前统一读取 asset model requirement
- [x] 交给 model selector 解析 preferred/fallback
- [x] resolved model 注入实际执行上下文

### 8.3 失败策略
- [x] 首选失败时按 fallback 降级
- [x] fallback 不满足最低语义能力时明确失败
- [x] method 不存在时明确失败
- [x] params schema mismatch 时明确失败

### 8.4 边界控制
- [ ] invocation layer 不负责资产元信息 discover
- [ ] invocation layer 不负责生成交互回答
- [ ] invocation layer 不将 asset center 变成执行层代理

### 8.5 验收点
- [x] self-iteration invoke 可在新调用层成功执行
- [x] fallback 行为可被独立验证
- [x] method/schema 错误路径有明确输出

---

## 9. Phase 8 - 新测试与旧测试清理

### 9.1 新测试必须先补
- [ ] 新增资产中心 registry 单测
- [ ] 新增 descriptor/schema 单测
- [ ] 新增模型选择/fallback 单测
- [x] 新增启动顺序/required assets 单测
- [x] 新增 self-iteration 新主链集成测试
- [x] 新增简单低歧义试点资产测试
- [ ] 新增局部重注册/descriptor 替换相关测试

### 9.2 旧测试删除清单
- [x] 删除旧模型可见资产查询工具回归（已收缩 `tests/unit/test_runtime_asset_intent_parsing.py`、`tests/unit/test_tool_calling_interpreter.py`、`tests/unit/test_runtime_asset_gateway_registration.py` 中旧 query_asset_* 主路径断言）
- [x] 删除旧 bounded-route 兼容测试（已清理一批仅服务旧资产工具语义的解释器/意图断言）
- [x] 删除只服务旧 prompt tool exposure 修补逻辑的测试（已收缩 `tests/unit/services/test_hot_tool_manager.py` 与相关 hot-tool 断言）
- [ ] 删除旧 hot-tool 资产工具面对齐修补测试（在新链完全接管后）

### 9.3 测试迁移原则
- [ ] 只保留与新主链直接相关的测试
- [ ] 不为已废弃旧结构写兼容性测试
- [ ] 删除旧测试前确认新主链测试已形成覆盖

### 9.4 最终真实用户链路验证
- [ ] 设计至少 50 个真实自然语言场景
- [ ] 每个场景覆盖 1 到 10 轮连续对话
- [ ] 场景集合覆盖简单查询、资产导航、detail 请求、方法调用、fallback、失败恢复、澄清、切换话题、跨轮追问、复杂组合任务
- [ ] 所有场景必须使用模拟真实用户表达，而不是内部 schema 指令式样本
- [ ] 验证以用户侧完整链路为准，不以单模块 mock 成功替代
- [ ] 输出场景总表、通过率、失败归因、链路阻塞点、设计反推结论

### 9.5 验收点
- [ ] 新主链测试可独立支撑重构
- [ ] 删除旧测试后仍有完整验证网
- [ ] 50+ 真实自然语言连续对话场景可作为最终收口验证

---

## 10. Phase 9 - 文档与收口

### 10.1 已完成
- [x] 新增 `docs/asset-centered-runtime-redesign.md`
- [x] 新增 `tasklist_asset_centered_runtime.md`

### 10.2 继续更新
- [ ] 更新 `docs/design.md`
- [ ] 更新 `docs/system-relationship-map.md`
- [ ] 更新 `docs/testing.md`
- [ ] 更新 `docs/development-log.md`

### 10.3 收口动作
- [ ] 将最终模块关系同步进 relationship map
- [ ] 将测试替换策略同步进 testing docs
- [ ] 记录旧路径退役边界
- [ ] 提交每个阶段的 meaningful commit，不做过碎提交

### 10.4 验收点
- [ ] 文档、任务单、代码结构、测试结构四者一致
- [ ] 不出现“文档是新框架，任务单还是旧 patch 逻辑”的漂移

---

## 11. 最终验收清单

- [ ] 资产中心是唯一元信息入口
- [ ] 模型资源层独立读取配置并注册模型资源
- [ ] self-iteration 成为标准资产并可运行
- [ ] 至少一个简单低歧义资产可运行
- [ ] 交互层不再暴露旧模型可见资产查询工具面
- [ ] 模型每轮只走三分支协议
- [ ] 调用前能解析模型需求并 fallback
- [ ] 新测试闭环替换旧兼容回归
- [ ] 启动顺序、局部恢复、开发调试视图都有明确落点
