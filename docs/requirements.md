# App OS 系统需求文档

## 1. 项目概述

本项目目标是构建一个类似操作系统的应用管理与生成系统（以下简称 App OS）。

在该系统中：
- 系统本身负责管理多个应用（App）
- 每个功能以 App 的形式存在、安装、运行、修改和持久化
- 用户可以通过系统内的 Builder App 创建、安装、修改其他 App
- 系统优先使用确定性的基础模块（Foundation Modules）执行底层能力
- 仅在需求澄清、复杂决策、语义分析、结构生成等高价值场景使用大模型能力（Intelligence Skills）

本系统应基于成熟架构进行魔改和扩展，可参考并改造 OpenClaw 的运行时、会话、工具调度与多代理机制。

---

## 2. 目标

### 2.1 总体目标

构建一个支持以下能力的 App OS：
- 管理用户与应用
- 持久化应用定义、运行状态和业务数据
- 支持应用的创建、安装、运行、暂停、升级、修改和删除
- 支持 Builder App 引导用户创建新 App
- 支持多角色、多任务、多交互的 App 定义
- 支持 Foundation Modules 与 Intelligence Skills 的分层调用
- 保障应用稳定运行、可审计、可观测、可恢复

### 2.2 架构目标

系统必须满足：
- App 为一等公民
- App 必须是持久化对象，而非一次性执行流程
- Builder 本身也是 App
- 用户数据、应用数据、系统数据分层隔离
- 默认优先使用 Foundation Modules，而非大模型
- 仅在必要场景调用 Intelligence Skills

---

## 3. 术语定义

### 3.1 Foundation Module
指不依赖大模型、确定性执行的基础能力模块，包括但不限于：
- 文件读写
- 网络请求
- 存储访问
- 事件分发
- 状态管理
- 权限校验
- 配置读取
- 模板渲染
- 数据转换

### 3.2 Intelligence Skill
指依赖大模型能力、用于语义理解、结构生成、复杂分析与决策支持的智能能力，包括但不限于：
- 需求澄清
- App Blueprint 生成
- 角色建议
- 工作流草案生成
- 诊断与优化建议
- 数据语义分析

### 3.3 App
系统中的一个持久化软件单元，具备：
- 定义
- 安装状态
- 运行状态
- 数据空间
- 视图
- 角色
- 工作流

### 3.4 Builder App
系统内置的特殊 App，用于帮助用户创建、安装、修改和升级其他 App。

### 3.5 App Blueprint
App 的结构化定义，包括：
- 目标
- 角色
- 任务
- 交互
- 工作流
- 视图
- 存储计划
- 权限策略
- 所需模块与技能

---

## 4. 系统范围

### 4.1 In Scope

本期纳入范围：
- App OS 内核与系统服务
- App Registry
- App Lifecycle 管理
- App Definition / Blueprint 管理
- Builder App
- App Runtime
- 多角色与任务交互模型
- 用户/应用/系统数据管理
- Foundation Modules 运行层
- Intelligence Skills 运行层
- 审计、日志、可观测性
- 测试框架与模型调用验证

### 4.2 Out of Scope（首期暂不做）

- 复杂 GUI 设计器
- 大规模应用市场
- 完整计费系统
- 多云多区域部署
- 高级自动化运营能力

---

## 5. 系统分层

### 5.1 Kernel Layer
基于成熟运行时改造，负责：
- session/runtime
- 工具调度
- agent/subagent 能力
- 基础执行宿主

### 5.2 System Services Layer
包括：
- User Management
- App Registry
- Lifecycle Manager
- Storage Service
- Config Service
- Policy Service
- Logging / Audit Service
- Event Bus

### 5.3 App Definition Layer
负责：
- Draft 管理
- Blueprint 管理
- Schema 校验
- 结构化持久化

### 5.4 Builder Layer
负责：
- 需求澄清
- 反问补全
- Blueprint 初稿生成
- 安装与修改入口

### 5.5 App Runtime Layer
负责：
- 工作流执行
- 角色调度
- 任务运行
- 状态流转
- 失败恢复

### 5.6 Foundation Module Layer
负责确定性能力：
- File Module
- Network Module
- Storage Module
- Event Module
- Policy Module
- State Module

### 5.7 Intelligence Skill Layer
负责智能能力：
- Requirement Clarification Skill
- Blueprint Generation Skill
- Definition Diagnosis Skill
- Data Analysis Skill

### 5.8 View Layer
负责：
- 页面
- 表单
- 列表
- 角色可见视图
- 操作入口

### 5.9 Storage Layer
负责：
- User Data
- App Data
- Runtime State
- System Metadata

---

## 6. 核心对象模型

系统至少应包含以下核心对象：
- User
- Tenant
- AppBlueprint
- AppInstance
- AppVersion
- Role
- Task
- Interaction
- Workflow
- WorkflowRun
- View
- Event
- Policy
- FoundationModule
- IntelligenceSkill
- StorageBinding
- AppDataRecord
- RuntimeState
- AuditLog

---

## 7. App 生命周期要求

每个 App 至少支持以下状态：
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

每个 App 至少支持以下操作：
- create draft
- validate
- compile
- install
- start
- stop
- pause
- update
- rollback
- archive
- delete

---

## 8. App 持久化要求

### 8.1 定义持久化
持久化 App Blueprint、角色、任务、视图、工作流、策略。

### 8.2 实例持久化
持久化已安装应用信息、所属用户、版本、绑定配置、授权信息。

### 8.3 运行态持久化
持久化运行状态、待办任务、执行上下文、错误与恢复点。

### 8.4 业务数据持久化
持久化 App 业务数据、文件、记录、输出结果。

---

## 9. 数据管理要求

### 9.1 用户数据
包括：
- 用户资料
- 用户设置
- 用户文件
- 用户偏好
- 用户授权信息

### 9.2 App 数据
包括：
- App 配置
- App 状态
- App 业务记录
- App 文件和缓存

### 9.3 系统数据
包括：
- 日志
- 审计信息
- Blueprint 索引
- Runtime trace
- Event 记录

### 9.4 数据隔离
必须支持：
- 用户级隔离
- App 级隔离
- 系统级隐藏空间
- Secret 独立管理

---

## 10. 角色与任务模型要求

### 10.1 角色类型
系统至少支持：
- human
- agent
- system
- external

### 10.2 角色属性
每个角色至少具备：
- name
- type
- responsibilities
- permissions
- visible_views
- accessible_data
- allowed_actions

### 10.3 任务属性
每个任务至少具备：
- id
- owner_role
- trigger
- input
- output
- success_condition
- failure_policy
- escalation_target

### 10.4 交互属性
每个交互至少具备：
- source_role
- target_role
- interaction_type
- payload_schema
- expected_result

---

## 11. Builder App 要求

Builder App 必须支持：
- 用户自然语言描述需求
- 自动提问与需求补全
- 生成 App Draft
- 生成 App Blueprint
- 校验定义冲突
- 安装 App
- 修改已安装 App
- 升级 App
- 查看生成与修改历史

Builder App 应优先调用：
- Foundation Modules 做结构化校验与持久化
- Intelligence Skills 做语义理解与建议

---

## 12. Foundation Modules 要求

首期必须提供的 Foundation Modules：
- file.read
- file.write
- file.list
- file.stat
- http.get
- http.post
- state.get
- state.set
- event.emit
- event.subscribe
- auth.check
- config.get
- config.set

要求：
- 确定性执行
- 明确输入输出
- 独立测试
- 支持日志追踪
- 支持权限控制

---

## 13. Intelligence Skills 要求

首期建议提供的智能技能：
- requirement.clarify
- blueprint.generate
- definition.diagnose
- workflow.suggest
- role.infer
- data.analyze

要求：
- 调用频率尽量低
- 输出尽量结构化
- 有失败兜底策略
- 可被审计
- 可配置模型参数

---

## 14. 大模型调用约束

系统必须遵守以下原则：
- 默认不用大模型
- 能由 Foundation Modules 和规则完成的，不调用大模型
- 仅在语义理解、复杂分析、结构生成、冲突诊断等场景调用大模型
- 大模型输出必须尽量结构化，便于进入后续流程
- 大模型能力应作为 Intelligence Skill 被统一封装

---

## 15. 稳定性要求

系统必须支持：
- App 稳定运行
- 任务失败重试
- 超时控制
- 人工接管
- 从检查点恢复
- 审计和追踪
- 配置与密钥隔离

---

## 16. 非功能需求

### 16.1 可维护性
- 清晰分层
- 明确 schema
- 模块可替换

### 16.2 可观测性
- 应用日志
- 工作流日志
- 模块调用日志
- 智能技能调用日志

### 16.3 可扩展性
- 支持新增 App 类型
- 支持新增 Foundation Modules
- 支持新增 Intelligence Skills

### 16.4 可测试性
- Foundation Modules 可单测
- Blueprint 可校验
- Workflow 可回放
- Intelligence Skills 可做集成测试与评测

---

## 17. OpenClaw 改造方向

建议复用与改造：
- session/runtime 作为基础执行上下文
- tool dispatch 作为 Module/Skill 执行入口
- subagent/session 作为角色代理与子任务执行机制
- memory/context 作为澄清与运行辅助上下文

建议新增：
- App Registry
- Lifecycle Manager
- Builder App
- App Definition Compiler
- Storage Namespace 管理
- App Runtime Host
- Policy & Permission 服务

---

## 18. MVP 范围

首期 MVP 目标：
- 实现 App OS 最小闭环
- 支持 Builder App 创建其他 App
- 支持 App Draft → Compile → Install → Run
- 支持用户/App/系统数据隔离
- 支持少量 Foundation Modules 与少量 Intelligence Skills
- 支持日志、状态、失败恢复基础能力

首期建议 App 类型：
- 文件同步 App
- 数据采集 App
- 简单审批 App
- Builder App
