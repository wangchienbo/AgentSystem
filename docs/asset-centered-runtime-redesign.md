# Asset-Centered Runtime Redesign — Phase 9 完整设计文档

> **状态**: 已落地实施，代码已提交
> **版本**: v1.0
> **创建时间**: 2026-05-01
> **相关 Tasklist**: `tasklist_asset_centered_runtime.md`（221 项全部完成）

---

## 1. 设计目标

将 AgentSystem 的运行时从**以 LLM 工具面为中心的隐式路由**切换到**以资产中心为唯一元信息入口的显式三分支协议**。

### 1.1 解决的问题

| 旧链路问题 | 新方案 |
|---|---|
| 模型直接暴露 `list_assets`/`query_asset_detail` 等底层工具面 | 资产中心作为唯一入口，模型只输出 `text/need_asset_detail_id/invoke` |
| gateway/tool_calling_interpreter 直接路由到 self-iteration | 通过 DecisionProtocol 三分支协议 + ContextAssembly 缓存 |
| 启动顺序隐式依赖 | 显式 StartupOrchestrator + 硬依赖链 |
| 模型配置散落在各处 | 模型资源层统一注册到资产中心 |
| 无标准化的资产描述协议 | AssetDescriptorRecord v1 协议 |

### 1.2 核心原则

- **资产中心只做索引/查询/解析**，不承担业务执行
- **资产中心必须先启动**，其他组件依赖它
- 交互协议严格限定为 **text / need_asset_detail_id / invoke** 三分支
- 模型资源由资产描述声明 `model_requirement`，调用时解析并支持降级

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    启动编排器                              │
│              StartupOrchestrator                         │
│  基础环境 → 资产中心 → 模型注册 → 资产注册 → 交互层        │
└────────────────────┬────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐   ┌──────────────┐  ┌──────────────┐
│资产中心  │   │ 模型资源层     │  │ 交互运行时      │
│        │   │              │  │              │
│Registry│   │ModelSelector │  │Orchestrator  │
│Service │   │ModelProbe    │  │DecisionProto │
│Models  │   │ClientRegistry│  │ContextAssemb │
└────────┘   └──────────────┘  └──────────────┘
                    │                   │
                    └───────┬───────────┘
                            ▼
                     资产 descriptor 注册
                     (self-iteration, config, ...)
```

---

## 3. 启动顺序

### 3.1 硬性启动阶段

| 阶段 | 名称 | 依赖 | 职责 |
|---|---|---|---|
| 1 | `env_ready` | 无 | 基础环境检查 |
| 2 | `asset_center_bootstrap` | `env_ready` | 启动资产中心并自注册 |
| 3 | `model_registry` | `asset_center_bootstrap` | 读取模型配置、初始化客户端、注册到资产中心 |
| 4 | `asset_registration` | `model_registry` | 其他系统资产（self-iteration、config_center）注册 descriptor |
| 5 | `interaction_layer` | `asset_registration` | 交互层初始化，加载资产上下文 |

### 3.2 StartupOrchestrator 实现

**文件**: `app/system/startup/startup_orchestrator.py`

- 每个阶段定义为 `StartupStage(name, action, required, depends_on, ready_check)`
- 依赖检查：阶段执行前验证 `depends_on` 中的依赖已就绪
- 就绪检查：可选 `ready_check` 函数，返回 `(ok: bool, detail: dict)`
- 失败处理：必需阶段失败抛出 `StartupOrchestratorError`
- 恢复机制：`rerun_stage()` 支持单阶段重新执行并标记 `recovered`

### 3.3 资产中心自引导

**文件**: `app/system/asset_center/bootstrap.py`

```python
ASSET_CENTER_DESCRIPTOR = AssetDescriptorRecord(
    descriptor_version=1,
    asset_id="asset:asset_center:v1",
    kind="system_asset",
    summary="Central metadata registry for runtime asset descriptors",
    detail="Provides the authoritative runtime metadata entry for asset summaries, "
           "details, method specs, and model requirements. "
           "Does not execute business logic.",
    methods=(),  # 资产中心自身不暴露业务方法
)

def bootstrap_asset_center() -> AssetCenterService:
    service = AssetCenterService()
    service.register_asset(ASSET_CENTER_DESCRIPTOR)
    return service
```

---

## 4. 核心模块设计

### 4.1 资产中心（Asset Center）

**目录**: `app/system/asset_center/`

#### 4.1.1 数据模型

**文件**: `app/system/asset_center/models.py`

**AssetDescriptorRecord v1**:

```python
@dataclass(frozen=True)
class AssetDescriptorRecord:
    descriptor_version: int              # 必填，协议版本
    asset_id: str                        # 必填，全局唯一标识
    kind: str                            # 必填，资产类型（如 system_asset）
    summary: str                         # 必填，一句话概要
    detail: str                          # 必填，详细描述
    methods: tuple[AssetMethodSpec, ...] # 可选，方法规格列表
    model_requirement: AssetModelRequirement  # 可选，模型需求声明
    metadata: dict[str, Any]             # 可选，扩展元数据
    registration_epoch: int              # 运行时自动分配，单调递增
```

**AssetMethodSpec**:

```python
@dataclass(frozen=True)
class AssetMethodSpec:
    name: str                         # 必填，方法名
    description: str                  # 必填，方法描述
    input_schema: dict[str, Any]      # 必填，输入参数 JSON Schema
    output_schema: dict[str, Any]     # 可选，输出参数 JSON Schema
```

**AssetModelRequirement**:

```python
@dataclass(frozen=True)
class AssetModelRequirement:
    preferred_model: str | None = None
    fallback_model: str | None = None
    minimum_requirements: dict[str, Any] = field(default_factory=dict)
```

**InteractionDecisionEnvelope**:

```python
@dataclass(frozen=True)
class InteractionDecisionEnvelope:
    decision: str                     # "text" | "need_asset_detail_id" | "invoke"
    text: str | None = None
    need_asset_detail_id: str | None = None
    invoke: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### 4.1.2 注册表

**文件**: `app/system/asset_center/registry.py`

**核心职责**:
- `register_asset(descriptor)` — 注册资产，自动分配 `registration_epoch`
- `register_model(record)` — 注册模型资源
- `list_assets()` — 返回所有资产的摘要列表
- `list_models()` — 返回所有模型资源列表
- `get_asset_detail(asset_id)` — 返回资产完整描述
- `get_asset_model_requirement(asset_id)` — 返回资产的模型需求
- `require_asset(asset_id)` — 获取资产，不存在时抛异常

**验证规则**:
- `descriptor_version >= 1`
- `asset_id` / `kind` / `summary` / `detail` 均非空
- 方法名必须唯一

#### 4.1.3 服务层

**文件**: `app/system/asset_center/service.py`

`AssetCenterService` 是对外暴露的入口，封装 Registry 并提供标准化输出：

```python
def list_assets() -> list[dict]:
    # 返回只包含 asset_id / kind / summary / descriptor_version 的摘要
    pass

def get_asset_detail(asset_id: str) -> dict:
    # 返回完整 descriptor.to_dict()
    pass
```

**关键边界**: 服务层不做任何业务逻辑，只做数据查询和格式转换。

### 4.2 模型资源层

**目录**: `app/system/model_runtime/`

#### 4.2.1 ModelRuntimeRecord

**文件**: `app/system/model_runtime/model_client_registry.py`

```python
@dataclass(frozen=True)
class ModelRuntimeRecord:
    model_id: str        # 唯一标识
    provider: str        # 提供商
    base_url: str        # API 地址
    api_key_env: str     # 环境变量名
    wire_api: str        # 协议类型
    enabled: bool        # 是否启用
    healthy: bool = False  # 健康状态（通过 probe 检测）
    role: str = "secondary"  # 角色：primary/secondary/fallback
    metadata: dict | None = None
```

#### 4.2.2 ModelSelector — 模型选择与降级

**文件**: `app/system/model_runtime/model_selector.py`

**选择逻辑**（严格有序）:

1. 检查 `preferred_model` 是否 `enabled` + `healthy` + 满足 `minimum_requirements`
2. 如果不满足，检查 `fallback_model` 是否满足相同条件
3. 如果 fallback 也不满足 → 抛 `ModelSelectionError`

**最低能力门槛**: 通过 `minimum_requirements` 字典匹配 `ModelRuntimeRecord.metadata` 中的能力标记。fallback 不得跨越最低语义能力门槛。

#### 4.2.3 ModelProbe — 健康检测

**文件**: `app/system/model_runtime/model_probe.py`

通过 `client.probe("ping")` 检测模型连通性，成功标记 `healthy=True`，失败标记 `healthy=False`。

### 4.3 交互运行时

**目录**: `app/system/interaction_runtime/`

#### 4.3.1 ContextAssembly — 上下文快照

**文件**: `app/system/interaction_runtime/context_assembly.py`

**InteractionContextSnapshot**（不可变数据类）:

- `summaries` — 资产摘要列表
- `details` — 已加载资产详情的字典（asset_id → detail dict）
- `_summary_index` — 摘要的 O(1) 索引（内部维护）
- `has_summary(asset_id)` — 检查摘要是否存在
- `has_detail(asset_id)` — 检查详情是否已加载
- `is_detail_stale(asset_id)` — 详情是否过期（detail_epoch < summary_epoch）
- `with_summaries(summaries, summary_index)` — 刷新摘要返回新快照
- `with_detail(asset_id, detail)` — 加载详情返回新快照

**ContextAssembly**:
- `refresh(asset_center_service)` — 从资产中心拉取最新摘要和详情

#### 4.3.2 DecisionProtocol — 三分支决策协议

**文件**: `app/system/interaction_runtime/decision_protocol.py`

**核心方法**:

| 方法 | 职责 |
|---|---|
| `normalize(envelope)` | 验证 envelope，返回 `DecisionProtocolResult` |
| `resolve_against_context(envelope, context)` | 根据上下文解析决策（缓存命中/过期/缺失） |
| `propose_for_self_iteration(message, context)` | self-iteration 资产的决策提议 |
| `propose_for_config_center(message, context)` | config_center 资产的决策提议 |
| `build_detail_request(asset_id)` | 构造详情请求 |
| `build_text_response(text)` | 构造纯文本响应 |
| `build_invoke_request(asset_id, method, params)` | 构造方法调用请求 |

**上下文解析语义**:

| 场景 | 行为 |
|---|---|
| 详情已加载且未过期 | → `text`（返回缓存命中） |
| 详情已加载但过期 | → `need_asset_detail_id`（标记 stale） |
| 摘要不存在 | → `text`（返回不可用） |
| 正常情况 | → 返回原始 envelope |

#### 4.3.3 InteractionOrchestrator — 交互编排器

**文件**: `app/system/interaction_runtime/interaction_orchestrator.py`

**核心入口**: `process_message(user_message: str) -> dict`

**路由优先级**（从高到低）:

1. 问候语（你好 / hello / hi）
2. 能力查询（能做什么 / 是做什么的）
3. 治理摘要（治理摘要 / 治理概览）
4. 自我迭代显式提及
5. 模型资源查询
6. 模型配置摘要
7. 配置中心显式提及
8. 配置变更（模糊 / 精确参数）
9. 状态查询
10. 总结 / 结束
11. 资产列表 / 详情查询
12. 默认 fallback

**上下文刷新**: 每条消息进入时，从资产中心 `refresh()` 更新 `_snapshot`。

**代词解析**: 维护 `_last_asset_id` 支持"它的..." / "再看看"等代词回指。

**重复检测**: 记录 `_recent_detail_requests`，对"再说一次...详情"返回文本提示。

---

## 5. 交互协议 v1

### 5.1 三分支决策

```
text → 直接返回用户可读文本
need_asset_detail_id → 请求装载某个资产的完整描述
invoke → 请求对某个资产方法执行调用
```

### 5.2 交互流程

```
用户消息
  → InteractionOrchestrator.process_message()
    → ContextAssembly.refresh() 更新上下文快照
    → 关键词路由 → DecisionProtocol 方法
    → DecisionProtocol.resolve_against_context()
    → InteractionDecisionEnvelope.validate()
    → 返回 dict{decision, text, need_asset_detail_id, invoke, metadata, resolved_action}
```

### 5.3 外部入口集成

**文件**: `app/system/gateway/tool_calling_interpreter.py`

旧 gateway 保留为兼容壳，通过 `LightBrainGateway` 集成新的 `InteractionOrchestrator`。

---

## 6. 测试策略

### 6.1 单元测试覆盖

| 模块 | 测试文件 | 覆盖点 |
|---|---|---|
| 资产中心注册表 | `test_asset_center_manifest_validation.py` | descriptor 验证、注册、查询 |
| 模型选择器 | `test_model_selector.py` | preferred/fallback/minimum 选择逻辑 |
| 决策协议 | `test_decision_protocol.py` | normalize、context 解析 |
| 交互编排器 | `test_interaction_orchestrator.py` | process_message 路由、上下文刷新 |

### 6.2 50 场景对话验收测试

**文件**: 
- `tests/unit/conversational_scenarios.py` — 场景定义
- `tests/unit/test_conversational_scenarios.py` — 测试 harness

**9 大类别、50+ 场景**:

| 类别 | 场景 ID | 数量 | 典型场景 |
|---|---|---|---|
| 简单查询 | SQ001-SQ010 | 10 | 状态查看、能力查询、问候 |
| 详情请求 | DR001-DR008 | 8 | 查看详情、对比资产、重复请求 |
| 方法调用 | IV001-IV009 | 9 | 策略概览、配置查询、参数修改 |
| 模型降级 | FB001-FB003 | 3 | preferred 不健康、fallback 也不满足 |
| 失败恢复 | FR001-FR003 | 3 | 调用重试、资产替代、全模型不可用 |
| 意图澄清 | CL001-CL003 | 3 | 模糊需求、多资产意图、参数缺失 |
| 话题切换 | TS001-TS004 | 4 | 状态→配置、技术→闲聊、连续跳跃 |
| 追问 | FU001-FU004 | 4 | 策略追问、配置结果追问、连续三轮 |
| 复杂混合 | CM001-CM006 | 6 | 完整诊断、发现→执行、10轮极限对话 |

**验证点**:
- `decision` 分支正确
- `asset_id` 匹配预期
- `method` 匹配预期
- `text` fallback 可接受（allow_text_fallback 标记）

**运行命令**:
```bash
pytest -q tests/unit/test_conversational_scenarios.py
# 54 passed in 0.29s
```

---

## 7. 资产注册协议

### 7.1 Descriptor v1 Schema

```python
{
    "descriptor_version": 1,           # int, 必填
    "asset_id": "asset:xxx:v1",        # str, 必填
    "kind": "system_asset",            # str, 必填
    "summary": "一句话概要",            # str, 必填
    "detail": "详细描述",               # str, 必填
    "methods": [...],                  # list[AssetMethodSpec], 可选
    "model_requirement": {...},        # AssetModelRequirement, 可选
    "metadata": {},                    # dict, 可选
    "registration_epoch": 42           # int, 运行时自动分配
}
```

### 7.2 版本扩展规则

- v1 作为最小稳定协议
- 后续扩展必须 **additive**（仅新增可选字段）
- 不允许重写必填字段的语义
- 版本升级前必须保留调试/观测视图兼容说明

### 7.3 资产自注册流程

1. 资产模块定义自己的 `AssetDescriptorRecord`
2. 启动阶段调用 `asset_center_service.register_asset(descriptor)`
3. 注册表验证、分配 `registration_epoch`、存储
4. 交互层通过 `refresh()` 自动获取最新摘要和详情

---

## 8. 模型资源治理

### 8.1 配置外置

模型配置不放在全局业务配置中，由 LLM 层自己读取外部配置文件。

### 8.2 注册流程

1. **读取配置** — 从外部配置文件加载 `ModelConfig`
2. **初始化客户端** — 创建 `OpenAIResponsesClient`
3. **健康检测** — `ModelProbe.probe()` 检测连通性
4. **注册到资产中心** — `asset_center_service.register_model(record)`

### 8.3 调用时模型选择

1. 解析资产的 `model_requirement`
2. 调用 `ModelSelector.resolve(...)` 选择模型
3. 首选模型不健康 → 降级到 fallback
4. Fallback 也不满足最低要求 → 显式失败
5. 记录选择原因（`"preferred"` / `"fallback"`）

---

## 9. 边界与约束

### 9.1 资产中心不做的事

- ❌ 不执行任何业务逻辑
- ❌ 不初始化模型客户端
- ❌ 不直接调用资产方法
- ❌ 不维护业务状态
- ❌ 不暴露自由探索式 API（只允许 summary/detail/invoke）

### 9.2 交互层不做的事

- ❌ 不直接查询资产注册表（必须通过资产中心）
- ❌ 不跳过上下文刷新直接决策
- ❌ 不返回三分支以外的决策

### 9.3 模型资源层不做的事

- ❌ 不管理资产描述符
- ❌ 不参与路由决策
- ❌ 不处理用户消息

---

## 10. 调试与观测

### 10.1 get_debug_view()

`InteractionOrchestrator.get_debug_view()` 返回:

```python
{
    "loaded_summaries": ["asset:self_iteration_center:v1", ...],
    "loaded_details": ["asset:config_center:v1", ...],
    "summary_epochs": {"asset:self_iteration_center:v1": 2, ...},
    "detail_epochs": {"asset:config_center:v1": 3, ...},
}
```

### 10.2 Epoch 机制

- 每次资产注册 `registration_epoch` 单调递增
- `InteractionContextSnapshot` 通过 `summary_epoch` 和 `detail_epoch` 比较判断详情是否过期
- `is_detail_stale()` → `detail_epoch < summary_epoch` 时标记过期

---

## 11. 文件清单

| 文件 | 行数 | 职责 |
|---|---|---|
| `app/system/asset_center/__init__.py` | 11 | 模块导出 |
| `app/system/asset_center/bootstrap.py` | 18 | 资产中心自引导 |
| `app/system/asset_center/models.py` | 90 | 数据模型 |
| `app/system/asset_center/registry.py` | 58 | 注册表核心 |
| `app/system/asset_center/service.py` | 38 | 服务层 |
| `app/system/model_runtime/__init__.py` | 7 | 模块导出 |
| `app/system/model_runtime/model_client_registry.py` | 38 | 模型客户端注册 |
| `app/system/model_runtime/model_probe.py` | 20 | 健康检测 |
| `app/system/model_runtime/model_selector.py` | 35 | 模型选择与降级 |
| `app/system/startup/startup_orchestrator.py` | 85 | 启动编排器 |
| `app/system/interaction_runtime/__init__.py` | 7 | 模块导出 |
| `app/system/interaction_runtime/context_assembly.py` | 99 | 上下文快照 |
| `app/system/interaction_runtime/decision_protocol.py` | 163 | 三分支决策协议 |
| `app/system/interaction_runtime/interaction_orchestrator.py` | 275 | 交互编排器 |
| `app/system/gateway/tool_calling_interpreter.py` | ~40 | 兼容壳 |
| `tests/unit/test_conversational_scenarios.py` | ~110 | 场景测试 harness |
| `tests/unit/conversational_scenarios.py` | ~350 | 50+ 场景定义 |

---

## 12. 已知限制与后续工作

### 12.1 V1 不做的事

- ❌ 动态心跳/租约机制（启动时静态注册）
- ❌ 多维模型评分（仅 preferred/fallback/minimum）
- ❌ 自由探索式 API
- ❌ LLM 驱动的意图路由（当前使用关键词路由）

### 12.2 后续 Phase

| 优先级 | 事项 | 说明 |
|---|---|---|
| P1 | LLM 意图路由替换关键词路由 | 当前是临时桥接 |
| P2 | 陈旧描述符策略（Phase 3.5） | 自动清理过期资产 |
| P3 | 启动 epoch / instance ID | 更细粒度的启动追踪 |
| P4 | 动态注册与心跳 | 运行时资产上下线 |
| P5 | 完整端到端 E2E 测试 | 真实模型调用链路 |

---

## 13. Git 提交记录

最近 15 个相关提交（最新在前）：

```
2b67947 docs: mark tasklist complete - all 218 items done
b46e068 docs: mark Phase 6 §7.4 as completed in tasklist
f3e7e69 refactor: shrink tool_calling_interpreter.py to compatibility shell
8faaae9 fix: resolve last 2 conversational scenario failures
9715b5d Phase I: Integrate InteractionOrchestrator + InvocationDispatcher
469891d feat: expand InteractionOrchestrator with process_message
e5f017a docs: record Phase 9.1 descriptor/schema and model selector tests
be71531 test: add descriptor/schema and model selector unit tests
15a1552 docs: record hot-tool registry asset tool retirement
6df687a refactor: retire legacy asset tool discovery
96b830f refactor: remove remaining legacy gateway slow e2e
c25d3ca test: add lightweight runtime asset acceptance coverage
b985ecf docs: document runtime asset route convergence
aec95e1 refactor: remove legacy asset detail gateway route
7e2a39c refactor: retire light brain detail intent emission
```

---

> **本文档与代码同步于 2026-05-01，反映当前已落地的完整实现。**
