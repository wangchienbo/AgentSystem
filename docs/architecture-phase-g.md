# Phase G: 持久化 Skill Worker + 路径执行图 + 离线运行

> 2026-04-13 架构讨论确定，中心式 Orchestrator 架构。

## 一、架构总览

```
┌────────────────────────────────────────────────────────────┐
│                        App Instance                        │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              App Orchestrator (中心调度器)            │  │
│  │                                                      │  │
│  │  职责：                                               │  │
│  │  1. 加载路径执行图（从 YAML）                          │  │
│  │  2. 接收用户请求，匹配路径                             │  │
│  │  3. 输入格式验证/模板变量解析                          │  │
│  │  4. 按步骤调度 Skill Workers（RPC）                    │  │
│  │  5. Checkpoint 记录 + 断点重试                        │  │
│  │  6. 模型离线时自动切换离线路径                         │  │
│  │  7. 失败感知 + 降级处理                                │  │
│  │  8. 汇总结果，格式化返回用户                           │  │
│  │  9. 万能 Skill 兜底（未匹配路径时）                     │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │ RPC via MessageBus                   │
│       ┌─────────────┼─────────────┬──────────────┐        │
│       ▼             ▼             ▼              ▼        │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐   │
│  │Intent   │  │Maoxuan   │  │Data     │  │Analysis  │   │
│  │Worker   │  │Worker    │  │Fetch    │  │Worker    │   │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘   │
│       ▲             ▲             ▲              ▲        │
│       └─────────────┴─────────────┴──────────────┘        │
│                    WorkerManager                          │
│              (启动 │ 健康检查 │ 崩溃重启)                   │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ModelHealthMonitor (后台 ping 模型)                  │  │
│  │  → online / degraded / offline                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SkillInstaller (自动搜索/下载/安装远程 Skill)        │  │
│  │  MD 文档 → SkillPackager → MultiActionLlmWorker     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SkillConfigCenter (Skill 运行时配置中心)             │  │
│  │  model / prompt / actions / input_schema             │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

## 二、核心设计决策

### 2.1 中心式 vs 链式

**选择中心式 App Orchestrator：**
- 统一负责输入输出格式处理
- 统一 Skill 调度
- 统一失败感知、断点重试
- 统一与用户层交互
- 天然知道哪个环节失败

### 2.2 Skill Worker 模型

- 每个 Skill = 持久化 Worker，App 启动时全部激活
- Skill 间通过 MessageBus RPC 通信
- Skill 内部自主决定是否调用大模型
- Skill 支持多接口（通过 `action` 字段路由）
- 天然支持后续水平分布式扩展

### 2.3 路径执行图

- 路径是用户固化的操作流程，持久化为 YAML 文件
- 存储位置：`data/paths/*.yaml`
- App 启动时加载到内存，通过 key 调用
- 模板变量：`{{step_name.field}}`
- 条件分支：`condition: "intent.confidence > 0.5"`
- 重试策略：`max_retries`, `retry_delay`
- 失败策略：`on_failure: abort | skip | fallback`

### 2.4 离线运行

- ModelHealthMonitor 后台定时 ping 模型
- 路径标记 `offline_capable: true/false`
- 模型离线时自动切换到 `offline_fallback` 路径
- Skill 支持 `action_offline()` 离线降级
- 中心 Orchestrator 和子 Skill 都支持离线模式

### 2.5 远程 Skill 自动发现与安装

- 网络上的 Skill 是 MD 文档
- 自动搜索、下载、安装
- SkillPackager 解析 MD 字段 → 查询配置中心 → 生成 MultiActionLlmWorker
- 配置中心管理 model、prompt、actions、input_schema
- App 需要某个 Skill 时：查找本地 → 搜索网络 → 找不到则创建

### 2.6 万能 Skill 兜底

- 当没有匹配的路径、没有匹配的 Skill 时
- 万能 Skill 接收用户原始需求
- 分析问题、调整操作、生成响应
- 大模型存在时作为最终兜底

### 2.7 协议适配层

| 类型 | 通信方式 | 说明 |
|------|---------|------|
| `callable` | Python 函数调用 | 兼容旧代码 |
| `script` | 子进程 JSON | 输入 stdin，输出 stdout |
| `executable` | 子进程命令 | CLI args |
| `worker` | MessageBus RPC | 新架构 |
| `http` | 远程 HTTP | 跨服务调用 |

### 2.8 错误传播

- 失败沿调用链反向冒泡到 Orchestrator
- Orchestrator 是唯一面向用户的出口
- 支持重试、降级、换路径
- Checkpoint 支持断点恢复

## 三、文件清单

### 新建核心文件

| 文件 | 职责 |
|------|------|
| `app/core/message_bus.py` | 异步消息总线（RPC + pub/sub） |
| `app/core/skill_worker.py` | SkillWorker 基类 + WorkerHealth |
| `app/core/worker_manager.py` | Worker 生命周期管理 |
| `app/core/model_health.py` | 模型健康监控 |
| `app/core/multi_action_llm_worker.py` | 多动作 LLM Worker |
| `app/core/protocol_adapter.py` | 协议适配层 |
| `app/services/path_store.py` | 路径持久化服务 |
| `app/services/app_orchestrator.py` | 中心调度器 |
| `app/services/skill_packager.py` | 远程 Skill 包装器 |
| `app/services/skill_config_center.py` | Skill 配置中心 |
| `app/services/skill_installer.py` | 远程 Skill 自动安装 |
| `app/services/universal_skill.py` | 万能 Skill 兜底 |

### 改造文件

| 文件 | 改动 |
|------|------|
| `app/services/skill_runtime.py` | 改为协议分发器，保留旧 API 兼容 |
| `app/core/skill_invoker.py` | 守卫逻辑迁移到 Bus 层 |
| `app/bootstrap/runtime.py` | 启动流程：WorkerManager + 路径加载 + 模型监控 |
| `app/bootstrap/skills.py` | 系统 Skill 改为 Worker 注册 |

## 四、路径 YAML 格式示例

```yaml
path_id: "path.maoxuan_analysis"
name: "毛选分析"
description: "用毛泽东思想分析市场/事件"
version: "1.0.0"
offline_capable: false
offline_fallback: "path.maoxuan_analysis_offline"

input_schema:
  type: object
  required: [query]
  properties:
    query: { type: string }
    depth: { type: string, enum: [brief, detailed], default: detailed }

output_schema:
  type: object
  properties:
    analysis: { type: string }
    conclusion: { type: string }

steps:
  - name: intent_parse
    skill: system.intent
    action: parse
    inputs:
      message: "{{user.query}}"
    timeout: 10.0
    max_retries: 2

  - name: maoxuan_analyze
    skill: skill.maoxuan
    action: analyze
    inputs:
      query: "{{intent_parse.intent_details}}"
      depth: "{{user.depth}}"
    condition: "intent_parse.confidence > 0.5"
    timeout: 30.0
    max_retries: 1
    on_failure: fallback

  - name: format_output
    skill: skill.format
    action: report
    inputs:
      analysis: "{{maoxuan_analyze.analysis}}"
    timeout: 10.0
```

## 五、实施路线

### Phase G.1: 基础设施
- MessageBus
- SkillWorker 基类
- WorkerManager
- 单元测试

### Phase G.2: 路径执行
- PathStore（YAML 加载/保存）
- AppOrchestrator（中心调度）
- 条件表达式安全解析
- Checkpoint + 断点重试

### Phase G.3: 离线运行
- ModelHealthMonitor
- 离线路径支持
- Skill 离线降级模板

### Phase G.4: 远程 Skill
- SkillConfigCenter
- SkillPackager（MD → Worker）
- SkillInstaller（自动搜索/下载/安装）
- MultiActionLlmWorker

### Phase G.5: 万能 Skill + 兜底
- UniversalSkill
- 未匹配路径/ Skill 时的兜底逻辑

### Phase G.6: 迁移与兼容
- skill_runtime 改为协议分发
- 系统 Skill 逐个 Worker 化
- 旧 API 端点适配
- 全量回归测试
