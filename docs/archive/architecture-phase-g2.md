# Phase G.2: Skill 元信息 + 身份追踪 + 日志中心

> 2026-04-13 架构讨论确定

## 一、核心问题

1. **App 创作者需要知道每个 Skill 的输入输出格式**，才能合理组装
2. **多个 App 共用同一个 Skill 实例**，需要身份识别排查 bug
3. **每个 Skill 需要运行日志**，统一日志中心存储
4. **请求链路需要全追踪**：谁 → 调了什么 → 返回了什么 → 花了多久

## 二、设计原则

| 原则 | 说明 |
|------|------|
| **Skill 元信息声明** | 每个 Skill 必须声明 input_schema、output_schema、actions |
| **App 实例绑定** | 一个 App 实例 = 1 个 Orchestrator 实例 + N 个 Skill Worker 绑定 |
| **Skill 共享** | Skill Worker 实例可被多个 App 共用，但每次请求携带身份 |
| **身份追踪** | request → caller_id + trace_id + user_id + app_instance_id |
| **日志分级** | 沿用现有 CollectionLevel 体系：off / light / medium / heavy |
| **日志中心** | 统一 LogCenter 存储所有 Skill 的运行日志，支持按 trace_id 查询 |

## 三、数据模型

### 3.1 SkillMetaInfo（Skill 元信息）

```python
class SkillMetaInfo(BaseModel):
    """Skill 的完整元信息，供 App 创作者查看和组装使用。"""
    skill_id: str
    name: str
    description: str
    version: str

    # 输入输出格式（创作者组装时的关键信息）
    input_schema: dict  # JSON Schema，描述 inputs 字段
    output_schema: dict  # JSON Schema，描述 outputs 字段

    # 多接口定义
    actions: dict[str, ActionMeta]  # {action_name: ActionMeta}

    # 运行时声明
    capability_profile: SkillCapabilityProfile  # 已有的能力档案
    dependencies: list[str]  # 依赖的其他 skill

    # 调试信息
    author: str = ""
    source: str = ""  # "builtin" | "remote" | "created"
    created_at: datetime
    updated_at: datetime
```

### 3.2 ActionMeta（单个动作的元信息）

```python
class ActionMeta(BaseModel):
    """一个 action 的完整描述。"""
    name: str
    description: str
    input_schema: dict  # 该 action 特定的输入格式
    output_schema: dict  # 该 action 特定的输出格式
    timeout_default: float = 30.0
    retry_default: int = 1
```

### 3.3 RequestContext（请求上下文 — 身份识别）

```python
class RequestContext(BaseModel):
    """每次请求的身份识别信息。"""
    trace_id: str  # 全链路追踪 ID（UUID）
    request_id: str  # 当前请求 ID（UUID）
    user_id: str  # 发起请求的用户
    app_instance_id: str  # 所属 App 实例
    caller_id: str  # 直接调用者（Orchestrator 或某个 Skill）
    parent_trace_id: str | None = None  # 父级 trace（skill 互调时）
    timestamp: datetime
```

### 3.4 SkillLogEntry（Skill 运行日志）

```python
# 日志等级（沿用系统体系）
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

class SkillLogEntry(BaseModel):
    """单条 Skill 运行日志。"""
    trace_id: str  # 全链路追踪
    skill_id: str
    action: str
    app_instance_id: str
    user_id: str
    level: LogLevel
    message: str
    timestamp: datetime

    # 可选详情
    inputs: dict | None = None  # 仅在 heavy 级别记录
    outputs: dict | None = None  # 仅在 heavy 级别记录
    error: str | None = None
    duration_ms: float | None = None
    metadata: dict = {}  # 额外信息

class LogCollectionConfig(BaseModel):
    """日志收集配置。"""
    level: LogLevel = "INFO"  # 默认级别
    record_inputs: bool = False  # 是否记录输入
    record_outputs: bool = False  # 是否记录输出
    max_entries: int = 10000  # 最大保留条目
    retention_hours: int = 24  # 保留时长
```

### 3.5 AppInstanceBinding（App 实例绑定配置）

```python
class AppInstanceBinding(BaseModel):
    """一个 App 实例绑定的 Orchestrator + Skill Worker 配置。"""
    app_instance_id: str
    orchestrator_id: str  # Orchestrator Worker ID
    skill_bindings: dict[str, SkillBindingConfig]  # skill_id → 配置
    log_config: LogCollectionConfig

class SkillBindingConfig(BaseModel):
    """单个 Skill 在 App 中的绑定配置。"""
    skill_id: str
    enabled: bool = True
    custom_config: dict = {}  # 覆盖 Skill 的默认配置
    log_level: LogLevel | None = None  # 覆盖全局日志级别
```

## 四、日志分级体系

沿用现有 CollectionLevel，映射关系：

| CollectionLevel | LogLevel 行为 | 记录内容 |
|----------------|--------------|---------|
| `off` | 不记录 | 无 |
| `light` | INFO | 仅记录 skill 调用开始/结束、状态、耗时 |
| `medium` | DEBUG + INFO | 增加输入/输出的摘要（截断到 200 字符） |
| `heavy` | DEBUG + INFO + WARNING + ERROR | 完整输入/输出、错误堆栈 |
| `custom` | 自定义 | 按 LogCollectionConfig 精确控制 |

## 五、请求链路追踪

```
用户 (user_id="alice")
  │
  ▼ trace_id="t-001", caller_id="user"
┌─────────────────────────────────────────┐
│  App Orchestrator (app="my-app")        │
│  trace_id=t-001, caller_id=user         │
│  log: [INFO] path.maoxuan matched       │
│  log: [INFO] step 1/4: intent_parse     │
│  ┌────────────────────────────────────┐ │
│  │ RPC → system.intent.parse          │ │
│  │ trace_id=t-001, caller_id=orch     │ │
│  │ log: [INFO] intent parsed          │ │
│  │ log: [DEBUG] inputs: {msg:"..."}   │ │
│  └────────────────────────────────────┘ │
│  log: [INFO] step 2/4: maoxuan_analyze  │
│  ┌────────────────────────────────────┐ │
│  │ RPC → skill.maoxuan.analyze        │ │
│  │ trace_id=t-001, caller_id=orch     │ │
│  │ log: [INFO] analysis completed     │ │
│  │ log: [INFO] duration=3200ms        │ │
│  └────────────────────────────────────┘ │
│  log: [INFO] path completed             │
└─────────────────────────────────────────┘
  │
  ▼ 用户收到回复

# 排查 bug 时：
GET /api/logs?trace_id=t-001  → 返回该链路所有 Skill 的完整日志
GET /api/logs?skill_id=skill.maoxuan → 返回该 Skill 的所有日志
GET /api/logs?app_instance_id=xxx&level=ERROR → 某 App 的错误日志
```

## 六、App 创作者视角

```
App 创作者界面看到的 Skill 卡片：

┌──────────────────────────────────────┐
│ 📊 Data Analysis Skill              │
│                                      │
│ 描述: 对结构化数据进行统计分析        │
│ 版本: 1.0.0                          │
│                                      │
│ 输入:                                │
│   - data: string (必需)              │
│   - analysis_type: enum (必需)       │
│     可选值: trend, compare, anomaly  │
│                                      │
│ 输出:                                │
│   - summary: string                  │
│   - insights: array of string        │
│   - charts: array of string          │
│                                      │
│ 可用动作:                             │
│   - analyze: 执行分析                 │
│   - validate: 验证数据格式            │
│   - suggest: 建议分析方向             │
│                                      │
│ 依赖: system.context                 │
│ 风险等级: R0_safe_read               │
│ 网络需求: N0_none (可离线)           │
└──────────────────────────────────────┘

创作者拖拽 skill 到 App 时，系统自动检查：
1. 输入输出格式是否匹配
2. 依赖的 skill 是否已安装
3. 离线能力是否满足 App 需求
```

## 七、文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `app/models/skill_meta.py` | **新建** | SkillMetaInfo, ActionMeta |
| `app/models/request_context.py` | **新建** | RequestContext 身份追踪 |
| `app/models/log_center.py` | **新建** | SkillLogEntry, LogCollectionConfig |
| `app/models/app_binding.py` | **新建** | AppInstanceBinding, SkillBindingConfig |
| `app/services/log_center.py` | **新建** | 日志中心服务 |
| `app/core/trace.py` | **新建** | trace_id 生成与透传工具 |
| `app/services/skill_meta_service.py` | **新建** | Skill 元信息查询服务 |

## 八、改动现有模型

| 文件 | 改动 |
|------|------|
| `app/models/skill_runtime.py` | `SkillExecutionRequest` 增加 `trace_id`, `caller_id`, `user_id` |
| `app/models/skill_runtime.py` | `SkillExecutionResult` 增加 `trace_id`, `duration_ms` |
| `app/core/message_bus.py` | RPC 请求自动注入 `RequestContext` |
| `app/services/app_orchestrator.py` | 使用 `RequestContext` + `LogCenter` |
