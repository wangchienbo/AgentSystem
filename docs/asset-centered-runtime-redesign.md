# Asset-Centered Operating Runtime Redesign

## 1. 背景与目标

AgentSystem 当前围绕 gateway + tool-calling 主链逐步收敛，但这条链路仍保留了旧框架的核心问题：

- 资产元信息真相源分散
- 交互层仍承担过多资产知识
- 模型资源仍主要停留在 config/client 级别，尚未进入统一治理面
- 启动顺序更多体现为实现细节，而不是正式运行时约束
- 模型仍可能面对过宽的探索型工具面

本次重构不再以旧版本兼容为目标，而直接建立一套新的运行时骨架：

1. 资产中心成为唯一元信息入口
2. 资产自描述、自注册、自声明模型需求
3. 模型资源层独立读取外部配置并注册到资产中心
4. 交互层采用受控三分支协议，而非自由工具探索
5. 启动顺序成为正式框架定义的一部分

本次重构的目标不是只重写一个 gateway 模块，而是重构以下五个系统约束：

- 元信息真相源
- 模型资源治理
- 资产注册机制
- 交互决策协议
- 启动顺序与运行时编排

---

## 2. 核心设计原则

### 2.1 资产中心是唯一元信息真相源
所有资产相关元信息，包括：

- 资产列表
- 资产概要
- 资产详细信息
- 方法说明
- 输入输出 schema
- 资产健康状态
- 模型需求

都只能通过资产中心读取。交互层、执行层、模型层、治理层都不再各自维护一套独立资产真相。

### 2.2 资产必须自描述、自注册
每个资产必须自己提供并注册：

- `asset_id`
- `summary`
- `detail`
- `methods`
- `schema`
- `model_requirement`
- `health`

资产中心只负责索引和查询，不替资产手工维护业务真相。

### 2.3 全局开放配置极小化
全局固定配置中只保留：

- 资产中心 bootstrap 信息
- 模型资源层配置文件位置
- 启动顺序与 required assets

明确不在全局开放配置中存放：

- 各资产 detail
- 各资产 methods
- 各资产 schema 集合
- 各资产完整配置
- 各资产执行说明

这些全部交由资产自注册。

### 2.4 模型资源纳入统一治理
模型不再只是 config + client，而是运行时受治理资源，必须具备：

- 配置来源
- 连通性/健康状态
- 可用 client
- fallback 关系
- 可被资产需求解析器选择

### 2.5 交互层只做受控决策
交互层不再暴露旧式自由探索工具面。模型每轮只允许输出：

- `text`
- `need_asset_detail_id`
- `invoke(asset_id, method, params)`

detail 获取、模型解析、执行调用全部下沉为系统受控流程。

### 2.6 启动顺序是正式运行时约束
启动顺序不是部署附属品，而是框架语义：

1. 基础环境
2. 资产中心
3. 模型资源层
4. 其他系统资产
5. 交互层
6. 外部入口

资产中心必须先 ready，否则模型层与其他资产都没有统一注册目标。

---

## 3. 总体架构

### 3.1 Global Bootstrap Layer
建议配置：

- `config/system_bootstrap.yaml`
- 外部 `model_pool.yaml`

职责：
- 提供系统最小锚点
- 不承载业务资产内容

### 3.2 Asset Center Layer
建议目录：

- `app/system/asset_center/`

建议模块：
- `models.py`
- `registry.py`
- `service.py`
- `bootstrap.py`

职责：
- 注册资产
- 列出资产
- 返回 detail
- 返回 model requirement
- 返回模型列表视图

边界：
- 不负责业务执行
- 不负责 prompt 生成
- 不负责业务编排

### 3.3 Model Resource Layer
建议目录：

- `app/system/model_runtime/`

建议模块：
- `model_pool_loader.py`
- `model_client_registry.py`
- `model_probe.py`
- `model_selector.py`

职责：
- 读取外部模型配置
- 探测连通性
- 初始化 clients
- 注册模型资源到资产中心
- 做 preferred/minimum/fallback 解析

### 3.4 Asset Runtime Layer
建议目录：

- `app/system/assets/`

建议模块：
- `base_asset.py`
- `descriptor_builder.py`
- `registration_protocol.py`

职责：
- 统一资产协议
- 统一 descriptor 生成
- 统一注册载荷结构

### 3.5 Interaction Runtime Layer
建议目录：

- `app/system/interaction_runtime/`

建议模块：
- `context_assembly.py`
- `decision_protocol.py`
- `interaction_orchestrator.py`

职责：
- 从资产中心拉 summary/detail
- 组装上下文
- 驱动受控三分支决策
- 调统一调用层

### 3.6 Invocation Layer
建议目录：

- `app/system/invocation/`

建议模块：
- `invocation_dispatcher.py`
- `model_resolved_call.py`

职责：
- 校验 asset_id/method/params
- 解析模型需求
- 选择模型
- 执行真实调用

### 3.7 Startup Orchestration Layer
建议目录：

- `app/system/startup/`

建议模块：
- `startup_orchestrator.py`

职责：
- 分阶段启动
- readiness barrier
- required asset 检查
- fail-fast
- 局部重注册与恢复

---

## 4. 配置设计

### 4.1 `system_bootstrap.yaml`

```yaml
version: 1

asset_center:
  asset_id: "asset:asset_center:v1"
  bootstrap_module: "app.system.asset_center.bootstrap"

model_runtime:
  config_path: "/root/.config/agentsystem/model_pool.yaml"

startup:
  order:
    - asset_center
    - model_runtime
    - system_assets
    - interaction_runtime
    - external_entrypoints

  required_assets:
    - asset:asset_center:v1
    - asset:self_iteration_center:v1
```

### 4.2 `model_pool.yaml`

```yaml
version: 1

default_model: "gpt-5.4"
fallback_model: "gpt-4o-mini"

models:
  - model_id: "gpt-5.4"
    provider: "openai"
    base_url: "https://..."
    api_key_env: "OPENAI_API_KEY"
    enabled: true

  - model_id: "gpt-4o-mini"
    provider: "openai"
    base_url: "https://..."
    api_key_env: "OPENAI_API_KEY"
    enabled: true
```

设计原则：
- bootstrap config 极小化
- model pool 独立给模型层读取
- 不在全局配置中承载资产细节

---

## 5. 资产 descriptor 与注册协议

### 5.1 descriptor v1 最小结构

```json
{
  "descriptor_version": 1,
  "asset_id": "asset:self_iteration_center:v1",
  "kind": "system_asset",
  "summary": "Self-iteration governance and observation surface",
  "detail": "Provides regression, governance, observation, and backlog reasoning surfaces.",
  "methods": [
    {
      "name": "strategy_overview",
      "description": "Return observe/summarize/act overview",
      "input_schema": {"type": "object"},
      "output_schema": {"type": "object"}
    }
  ],
  "model_requirement": {
    "preferred_model": "gpt-5.4",
    "fallback_model": "gpt-4o-mini",
    "minimum_requirements": {
      "structured_output": true
    }
  }
}
```

### 5.2 关键约束
- `descriptor_version` 必须存在
- `summary/detail/methods/model_requirement` 必须同源生成
- descriptor 是资产注册与交互决策的唯一描述面
- 第一版先使用静态注册快照，不做复杂动态 provider

---

## 6. 模型资源治理与降级

### 6.1 模型资源注册
模型层初始化后，将可用模型注册为受治理资源，至少包含：

- `model_id`
- `provider`
- `healthy`
- `default/fallback role`
- 最小能力标签

### 6.2 资产模型需求
每个资产 descriptor 声明：

- `preferred_model`
- `fallback_model`
- `minimum_requirements`

### 6.3 模型解析流程
调用前固定执行：
1. 读取 asset descriptor
2. 取出 model requirement
3. 在模型资源池中尝试 preferred model
4. preferred 不健康时尝试 fallback model
5. fallback 不满足最低语义能力时明确失败
6. resolved model 注入调用上下文

### 6.4 第一版复杂度约束
第一版只做：
- preferred model
- minimum requirements
- fallback model

暂不做：
- 复杂多维评分
- 复杂 latency/cost 优化
- 深度 capability ontology

---

## 7. 交互协议重写

### 7.1 新决策协议
模型每轮只允许返回三类之一：

#### 直接回答
```json
{"text": "..."}
```

#### 请求更多 detail
```json
{"need_asset_detail_id": "asset:self_iteration_center:v1"}
```

#### 执行资产方法
```json
{
  "invoke": {
    "asset_id": "asset:self_iteration_center:v1",
    "method": "strategy_overview",
    "params": {}
  }
}
```

### 7.2 明确删除旧探索面
模型不再直接看到：
- `list_assets`
- `query_asset_info`
- `query_asset_detail`

这些以后属于系统内部元信息装配能力。

### 7.3 上下文装配顺序
每轮固定为：
1. 决策协议说明
2. 当前可见资产 summary 列表
3. 已加载 asset details
4. 最近历史
5. 当前问题

---

## 8. 启动顺序与运行时编排

### Stage 0, 基础环境
- config loader
- logging
- minimal persistence

### Stage 1, 资产中心
- registry ready
- register/query ready

### Stage 2, 模型资源层
- 读取模型配置
- 探测连通性
- 初始化 clients
- 注册模型资源

### Stage 3, 系统资产层
- self_iteration_center
- runtime_center（可选第二试点）
- 其他系统资产
- 完成注册

### Stage 4, 交互层
- context assembly ready
- decision protocol ready
- invocation ready

### Stage 5, 外部入口
- api/chat/http ready

### 8.1 局部恢复要求
重构不能只设计 cold start，还必须设计：
- 资产重注册
- descriptor 替换生效
- 局部资产崩溃后的恢复
- interaction 侧 detail cache 失效策略

---

## 9. 风险与硬护栏

### 9.1 一级护栏
1. 资产中心不得承担业务执行
2. descriptor 必须 versioned
3. summary/detail/methods/model_requirement 必须同源生成
4. fallback 不得跨越最低语义能力门槛
5. 必须保留开发者调试/观测视图
6. 必须设计运行中重注册与局部恢复

### 9.2 额外系统风险
- 资产中心膨胀成上帝模块
- 自注册后描述与实际运行状态漂移
- 资产注册统一但语义不统一
- fallback 改变资产实际语义
- 严格三分支协议放大异常路径处理难度
- 资产中心成为高频热路径性能瓶颈
- 只用 self-iteration 单试点会误判架构问题

### 9.3 风险收敛策略
- Asset Center 保持轻中心
- descriptor 统一构造器
- 模型治理第一版保持克制
- 保留一个简单低歧义试点资产
- 新主链测试先建立，再删除旧兼容回归

---

## 10. 第一版范围与试点策略

### 10.1 第一版必须完成
- asset_center
- model_runtime
- startup_orchestrator
- self_iteration_center 资产化
- 新 interaction runtime 三分支协议
- 新主链测试

### 10.2 第一版建议额外加入
- 一个简单低歧义试点资产
- 可选 runtime_center 作为第二批资产

### 10.3 第一版明确不做
- 全系统资产一次性迁移
- 复杂 capability ontology
- 复杂健康聚合
- 资产中心业务执行化
- 复杂 provider 模式

---

## 11. 测试与验收

### 11.1 必须新增的测试
- 资产中心 registry 单测
- descriptor/schema 单测
- 模型选择/fallback 单测
- 启动顺序/required assets 单测
- self-iteration 新主链集成测试
- 简单试点资产测试

### 11.2 可删除的旧测试
- 旧模型可见资产查询工具回归
- 旧 bounded-route/compat 修补测试

### 11.3 第一版验收主链
1. 资产中心可启动并 ready
2. 模型资源层可注册
3. self-iteration 可注册 summary/detail/methods/model_requirement
4. 交互层可通过资产中心读取这些信息
5. 模型可请求 detail 或直接 invoke
6. 执行层可按 model requirement 选模型
7. 首选失败时可 fallback
8. 最终回答可闭环返回

---

## 12. 实施顺序

### Phase 1, 立底座
- Asset Center
- Model Runtime
- Startup Orchestrator

### Phase 2, 立资产协议
- BaseAsset
- Descriptor
- Registration Protocol

### Phase 3, 迁 self-iteration
- 作为首批标准资产

### Phase 4, 重写 interaction runtime
- context assembly
- decision protocol
- invocation chain

### Phase 5, 删除旧工具面与旧测试
- 移除旧模型可见资产查询工具
- 清理旧兼容回归

### Phase 6, 扩更多资产
- runtime_center
- governance
- app management

---

## 13. 最终一句话

直接将 AgentSystem 重构为一套 **Asset-Centered Operating Runtime**：以资产中心为唯一元信息真相源，以模型资源层为统一模型治理面，以资产自描述自注册为标准协议，以受控三分支决策为交互协议，以“资产中心 → 模型资源层 → 系统资产 → 交互层 → 外部入口”为硬启动顺序，并删除旧的模型可见资产查询工具面与相关兼容性回归。
