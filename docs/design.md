# App OS 设计文档

## 1. 文档信息

- 项目名称：AgentSystem / App OS
- 代码仓库：https://github.com/wangchienbo/AgentSystem
- 当前工作目录：`/root/project`
- 关联文档：
  - `README.md`（需求文档）
  - `TESTING.md`（测试文档）

本文档基于当前需求整理，目标是输出一份逻辑完备、架构清晰、可直接进入实现阶段的系统设计方案。

---

## 2. 设计目标

系统目标不是构建单个应用，而是构建一个 **App OS（应用操作系统）**：
- 系统负责管理多个 App
- 每个功能作为 App 持久存在
- App 支持创建、安装、运行、暂停、修改、升级、归档
- 用户可通过 Builder App 创建和修改其他 App
- 系统优先通过 Foundation Modules 完成底层确定性工作
- 系统仅在语义理解、分析、规划、生成时调用 Intelligence Skills
- 系统需支持稳定运行、数据隔离、可追踪和可恢复

---

## 3. 核心设计原则

### 3.1 App 是一等公民
系统管理的最小长期对象不是 workflow，而是 App。

### 3.2 Builder 也是 App
创建应用的能力本身也被系统 App 化。

### 3.3 默认不用大模型
能通过 Foundation Modules 和规则完成的，不调用大模型。

### 3.4 Intelligence Skill 只用于高价值智能环节
仅用于：
- 需求澄清
- Blueprint 生成
- 角色推断
- 诊断与优化建议
- 数据语义分析

### 3.5 持久化分层
必须区分：
- 用户数据
- App 数据
- Runtime 状态
- 系统元数据

### 3.6 系统需要像 OS 一样可管理
必须支持：
- 注册
- 安装
- 启停
- 升级
- 回滚
- 日志
- 权限
- 资源控制

---

## 4. 系统总体架构

```text
[ User / Web UI / Chat / API ]
             |
             v
[ Builder App / App Views ]
             |
             v
[ App Definition Layer ]
             |
             v
[ App Lifecycle Manager ]
             |
             v
[ App Runtime Layer ]
      +------+------+
      |             |
      v             v
[ Foundation Modules ]   [ Intelligence Skills ]
      |             |
      +------+------+
             |
             v
[ Storage / Event / Policy / Logging ]
             |
             v
[ Kernel / OpenClaw-inspired Runtime ]
```

---

## 5. 分层设计

### 5.1 Interface Layer
负责：
- 用户交互
- App 使用入口
- Builder App 入口
- 管理控制台入口
- API 入口

输入形式：
- Web 控制台
- Chat 界面
- API 调用

### 5.2 App Definition Layer
负责应用蓝图管理：
- App Draft
- App Blueprint
- 角色定义
- 任务定义
- 交互定义
- 视图定义
- 存储计划
- 所需模块与智能技能

### 5.3 Builder Layer
负责：
- 将用户自然语言需求转为结构化草稿
- 提问补全缺失信息
- 校验逻辑冲突
- 生成可编译的 Blueprint
- 修改现有 App 的定义

### 5.4 Lifecycle Layer
负责管理 App 状态：
- draft
- validating
- compiled
- installed
- running
- paused
- stopped
- failed
- upgrading
- archived

### 5.5 Runtime Layer
负责：
- workflow 执行
- role/task 调度
- event 响应
- 模块调用
- skill 调用
- 失败恢复
- checkpoint 记录

### 5.6 Foundation Module Layer
负责所有非 LLM 基础能力：
- file.read / file.write / file.list / file.stat
- http.get / http.post
- state.get / state.set
- event.emit / event.subscribe
- auth.check
- config.get / config.set

### 5.7 Intelligence Skill Layer
负责少量模型能力：
- requirement.clarify
- blueprint.generate
- definition.diagnose
- role.infer
- workflow.suggest
- data.analyze

### 5.8 Storage Layer
负责持久化：
- User Data
- App Data
- Runtime State
- System Metadata
- Logs / Audit / Trace

### 5.9 Policy / Permission Layer
负责：
- 用户权限
- 角色权限
- App 权限
- 模块可见性
- 外部访问范围
- 数据可见范围

### 5.10 Event / Observability Layer
负责：
- 系统事件总线
- App 生命周期事件
- Runtime 事件
- 审计日志
- Workflow Trace
- 模型调用记录

---

## 6. 核心对象模型

### 6.1 User
```yaml
id: string
name: string
tenant_id: string
profile: object
preferences: object
```

### 6.2 AppBlueprint
```yaml
id: string
name: string
goal: string
roles: Role[]
tasks: Task[]
interactions: Interaction[]
workflows: Workflow[]
views: View[]
storage_plan: StoragePlan
required_modules: string[]
required_skills: string[]
policies: Policy[]
version: string
```

### 6.3 AppInstance
```yaml
id: string
blueprint_id: string
owner_user_id: string
status: string
installed_version: string
runtime_config: object
data_namespace: string
created_at: datetime
updated_at: datetime
```

### 6.4 Role
```yaml
id: string
name: string
type: human|agent|system|external
responsibilities: string[]
permissions: string[]
visible_views: string[]
accessible_data: string[]
allowed_actions: string[]
```

### 6.5 Task
```yaml
id: string
owner_role: string
trigger: string
inputs: object
outputs: object
success_condition: string
failure_policy: string
escalation_target: string
```

### 6.6 Workflow
```yaml
id: string
name: string
steps: WorkflowStep[]
triggers: string[]
retry_policy: object
checkpoint_policy: object
```

### 6.7 View
```yaml
id: string
name: string
type: page|form|list|detail|dashboard
visible_roles: string[]
components: object[]
actions: object[]
```

---

## 7. App Builder 设计

Builder App 是系统预装 App，职责包括：
- 创建 App Draft
- 需求澄清
- Blueprint 生成
- Blueprint 修改
- App 安装
- App 升级
- App 结构诊断

### 7.1 Builder 工作流
1. 用户输入需求
2. requirement.clarify 输出缺失点
3. 用户补全信息
4. blueprint.generate 生成蓝图初稿
5. definition.diagnose 检查冲突
6. compile Blueprint
7. install App
8. 返回可运行 App

### 7.2 Builder 的智能与非智能边界
- Foundation Modules：持久化、schema 校验、状态更新、安装动作
- Intelligence Skills：提问、推断、生成、诊断

---

## 8. 生命周期设计

### 8.1 状态流转
```text
draft -> validating -> compiled -> installed -> running
                                   -> paused
                                   -> stopped
                                   -> failed
running -> upgrading -> running
running -> archived
```

### 8.2 核心操作
- create_draft
- validate_draft
- compile_blueprint
- install_app
- start_app
- pause_app
- stop_app
- update_app
- rollback_app
- archive_app

---

## 9. 数据与存储设计

### 9.1 数据分层
#### 用户数据
- 用户资料
- 用户配置
- 用户文件
- 用户偏好
- 用户鉴权绑定

#### App 数据
- App 配置
- App 业务数据
- App 输出记录
- App 文件空间

#### Runtime 数据
- workflow run state
- checkpoints
- pending tasks
- transient cache

#### 系统元数据
- registry
- audit logs
- traces
- module/skill execution records
- system events

### 9.2 隔离原则
- User Scope 隔离
- App Scope 隔离
- Runtime Scope 隔离
- Secret 独立托管

---

## 10. Foundation Modules 设计

首期模块：
- `file.read`
- `file.write`
- `file.list`
- `file.stat`
- `http.get`
- `http.post`
- `state.get`
- `state.set`
- `event.emit`
- `event.subscribe`
- `auth.check`
- `config.get`
- `config.set`

要求：
- 确定性
- 输入输出 schema 清晰
- 独立单元测试
- 可记录日志
- 支持权限拦截

---

## 11. Intelligence Skills 设计

首期智能技能：
- `requirement.clarify`
- `blueprint.generate`
- `definition.diagnose`
- `role.infer`
- `workflow.suggest`
- `data.analyze`

要求：
- 尽量结构化输出
- 支持模型配置切换
- 支持失败兜底
- 支持审计和重放

---

## 12. 运行时设计

### 12.1 Runtime 组成
- Workflow Executor
- Role Dispatcher
- Event Listener
- State Store
- Module Executor
- Skill Executor
- Recovery Manager

### 12.2 执行原则
- 默认优先执行 Foundation Modules
- 只有在必要节点调用 Intelligence Skills
- 所有节点都应有日志、trace 和状态记录

### 12.3 失败处理
支持：
- retry
- compensation
- escalation
- human handoff
- checkpoint restore

---

## 13. 权限与安全设计

### 13.1 权限维度
- 用户对 App 的权限
- 角色对 View 的权限
- App 对 Module 的权限
- App 对 Skill 的权限
- App 对外部网络和文件系统的权限

### 13.2 密钥策略
- 通过环境变量或 secret store 注入
- 不允许硬编码到仓库
- 日志与测试报告不得回显完整密钥

---

## 14. 基于 OpenClaw 的改造建议

建议借鉴并改造：
- session/runtime 作为任务执行宿主
- tool dispatch 作为 Foundation Module / Skill 执行入口
- subagents 作为角色代理执行机制
- memory/context 作为澄清和运行上下文

建议新增：
- App Registry
- Lifecycle Manager
- Builder App
- Blueprint Compiler
- App Runtime Host
- Storage Namespace 管理
- Policy Service

---

## 15. 实现路线建议

### Phase 1：定义与存储
- Blueprint schema
- AppInstance schema
- Role/Task/View schema
- Storage namespace

### Phase 2：基础运行时
- Lifecycle manager
- Foundation Modules executor
- Runtime state persistence

### Phase 3：Builder App
- requirement clarification
- blueprint generation
- install flow

### Phase 4：智能增强
- definition diagnosis
- role inference
- workflow suggestion

### Phase 5：可视化与运维
- App views
- logs / trace / audit dashboard

---

## 16. 非功能要求

- 可维护：分层清晰、schema 稳定
- 可测试：模块、工作流、技能均可验证
- 可观测：日志、trace、审计可查
- 可扩展：后续能增加更多 App 类型和模块
- 可恢复：支持中断恢复与版本回滚

---

## 17. 结论

本系统应被实现为一个 **以 App 为持久化一等公民的 App OS**。系统通过 Builder App 让用户持续创建和演化应用，通过 Foundation Modules 保证确定性执行，通过 Intelligence Skills 提供少量高价值智能能力，并通过生命周期、数据隔离、日志审计与恢复机制保障系统稳定运行。
