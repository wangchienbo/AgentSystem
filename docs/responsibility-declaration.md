# 系统架构责任划分方案

> 设计时间: 2026-04-14
> 状态: 方案定稿
> 原则: 每个组件必须声明"我是谁、我能做什么、我不能做什么"

---

## 1. 系统级声明

### 1.1 全局常量（写死在系统中）

```python
# ── 资产类型 ──────────────────────────────────────────────────
ASSET_TYPE = {
    "system_app": "系统级 App（不可删除，不可修改）",
    "user_app": "用户 App（创建者所有）",
    "center_skill": "中心 Skill（系统内建基础设施）",
    "subordinate_skill": "从属 Skill（领域服务，可修改）",
    "system_config": "系统配置（root 可改）",
    "log": "日志记录（只读）",
}

# ── 权限级别 ──────────────────────────────────────────────────
ROLE_LEVEL = {
    "user": 0,    # 普通用户
    "admin": 1,   # 管理员
    "root": 2,    # 超级管理员
    "system": 99, # 系统自身
}

# ── 不可变系统 App ID（写死） ─────────────────────────────────
SYSTEM_APP_IDS = {
    "master": "system.master",  # 主控
}

# ── 中心 Skill ID 前缀（写死） ────────────────────────────────
CENTER_SKILL_PREFIXES = {
    "bus": "system.bus.",        # MessageBus
    "router": "system.router.",  # ModelRouter
    "worker": "system.worker.",  # WorkerManager
    "log": "system.log.",        # LogCenter
    "meta": "system.meta.",      # SkillMeta
    "path": "system.path.",      # PathStore
}
```

---

## 2. 系统主控 vs 用户交互层 责任划分

### 2.1 系统主控（Master Control / Kernel）

```
┌──────────────────────────────────────────────────────┐
│              系统主控声明                              │
│                                                      │
│  我是谁: system.master（全局唯一系统 App）             │
│  我的职责: 权限审批、系统管理、基础设施                │
│  我不做: 不直接跟用户对话，不理解用户意图              │
│  我的接口: /api/v1/system/master/*                    │
└──────────────────────────────────────────────────────┘
```

| 功能 | 主控做 | 交互层做 | 说明 |
|------|--------|----------|------|
| 意图理解 | ❌ | ✅ | 主控不理解用户语言 |
| 会话管理 | ❌ | ✅ | 主控不管理多轮对话 |
| 权限审批 | ✅ | ❌ | 主控是唯一的权限决策者 |
| 日志审计 | ✅ | ❌ | 主控记录所有操作 |
| 系统升级 | ✅ | ❌ | 主控执行升级/回滚 |
| Skill 管理 | ✅ | ❌ | 主控创建/修改/注册 Skill |
| App 管理 | ✅ | ❌ | 主控注册 App，但由交互层发起 |
| 基础设施 | ✅ | ❌ | MessageBus、ModelRouter 等 |
| 格式化输出 | ❌ | ✅ | 主控返回原始数据 |
| 收集意见 | ❌ | ✅ | 交互层引导用户补充细节 |
| 解释方案 | ❌ | ✅ | 交互层翻译技术方案 |

**主控的核心声明：**
```python
class MasterControlDeclaration:
    """我是系统内核，我的职责是：
    1. 权限审批：所有操作必须经过我
    2. 系统管理：Skill/App/配置/升级
    3. 日志审计：记录所有操作
    4. 基础设施：提供 MessageBus、ModelRouter 等
    
    我不直接跟用户对话，我只通过 API 提供服务。
    用户交互层是我的 Shell，他们调用我的 API。
    """
    
    WHO_AM_I = "system.master"
    MY_ROLE = "kernel"
    IMMUTABLE = True
    DELETABLE = False
    
    # 我能做什么
    CAPABILITIES = [
        "auth.request",      # 权限审批
        "execute",           # 执行操作
        "suggest",           # 系统建议评估
        "query",             # 系统查询
        "skill.manage",      # Skill 管理
        "app.manage",        # App 管理
        "system.upgrade",    # 系统升级
        "log.record",        # 日志记录
    ]
    
    # 我不能做什么
    CANNOT_DO = [
        "understand_intent",  # 不理解用户意图
        "manage_session",     # 不管理会话
        "format_output",      # 不格式化输出
        "chat_with_user",     # 不直接跟用户对话
    ]
```

### 2.2 用户交互层（User Interaction Layer / Shell）

```
┌──────────────────────────────────────────────────────┐
│              用户交互层声明                            │
│                                                      │
│  我是谁: LightBrainGateway（用户交互入口）             │
│  我的职责: 意图理解、会话管理、格式化输出              │
│  我不做: 不直接修改系统资源，不审批权限                │
│  我的依赖: 调用主控 API 执行操作                       │
└──────────────────────────────────────────────────────┘
```

| 功能 | 交互层做 | 主控做 | 说明 |
|------|----------|--------|------|
| 接收用户消息 | ✅ | ❌ | 交互层是唯一入口 |
| 意图理解 | ✅ | ❌ | 交互层解析用户语言 |
| 会话管理 | ✅ | ❌ | 交互层管理多轮对话 |
| 格式化输出 | ✅ | ❌ | 交互层生成卡片/列表 |
| 请求授权 | ✅ | ❌ | 交互层向主控请求 |
| 收集意见 | ✅ | ❌ | 交互层引导用户补充 |
| 解释方案 | ✅ | ❌ | 交互层翻译技术方案 |
| 权限审批 | ❌ | ✅ | 主控是唯一决策者 |
| 系统升级 | ❌ | ✅ | 主控执行升级 |
| Skill 管理 | ❌ | ✅ | 主控创建/修改 Skill |
| App 管理 | ❌ | ✅ | 主控注册 App |
| 日志审计 | ❌ | ✅ | 主控记录所有操作 |

**交互层的核心声明：**
```python
class InteractionLayerDeclaration:
    """我是用户交互层，我的职责是：
    1. 意图理解：解析用户输入，理解意图
    2. 会话管理：管理多轮对话状态
    3. 格式化输出：把数据翻译成用户友好的格式
    4. 请求授权：向主控请求权限
    5. 收集意见：引导用户补充系统建议细节
    6. 解释方案：把技术方案翻译成用户语言
    
    我不直接修改系统资源，所有操作都通过主控 API。
    我是主控的 Shell，用户通过我跟系统交互。
    """
    
    WHO_AM_I = "interaction.layer"
    MY_ROLE = "shell"
    
    # 我能做什么
    CAPABILITIES = [
        "understand_intent",   # 意图理解
        "manage_session",      # 会话管理
        "format_output",       # 格式化输出
        "request_auth",        # 请求授权
        "collect_feedback",    # 收集意见
        "explain_plan",        # 解释方案
        "multi_turn_dialog",   # 多轮对话
    ]
    
    # 我不能做什么
    CANNOT_DO = [
        "approve_permission",  # 不审批权限
        "modify_system",       # 不直接修改系统
        "manage_skills",       # 不管理 Skill
        "manage_apps",         # 不管理 App
        "upgrade_system",      # 不升级系统
        "audit_logs",          # 不记录审计日志
    ]
```

---

## 3. 中心 Skill vs 从属 Skill 责任划分

### 3.1 中心 Skill（Center Skill / Kernel Module）

```
┌──────────────────────────────────────────────────────┐
│              中心 Skill 声明                           │
│                                                      │
│  我是谁: 系统内建基础设施                              │
│  我的 ID: system.* 前缀                               │
│  我的职责: 提供系统级能力（消息总线、模型路由等）       │
│  我不做: 不处理业务逻辑，不直接服务用户                │
│  谁能修改: 只有系统自身（不可修改）                    │
│  谁能使用: 所有用户（只读 + 组装）                     │
└──────────────────────────────────────────────────────┘
```

| 中心 Skill | ID 前缀 | 职责 | 使用者 |
|-----------|---------|------|--------|
| MessageBus | `system.bus.*` | 进程间通信、RPC 调用 | 所有从属 Skill |
| ModelRouter | `system.router.*` | 模型路由、负载均衡 | 所有需要 LLM 的 Skill |
| WorkerManager | `system.worker.*` | Worker 生命周期管理 | 主控 |
| LogCenter | `system.log.*` | 日志收集、分级存储 | 所有 Skill |
| SkillMeta | `system.meta.*` | Skill 元信息管理 | 所有 Skill |
| PathStore | `system.path.*` | 路径定义存储 | 所有 Skill |

**中心 Skill 的核心声明：**
```python
class CenterSkillDeclaration:
    """我是中心 Skill，我的职责是：
    1. 提供系统级基础设施能力
    2. 作为从属 Skill 的依赖
    3. 通过 MessageBus 提供 RPC 服务
    
    我不处理业务逻辑，不直接服务用户。
    我是从属 Skill 的基础，他们依赖我。
    """
    
    WHO_AM_I = "center.skill"
    MY_ROLE = "infrastructure"
    IMMUTABLE = True  # 不可修改
    OWNER_ROLE = "system"  # 只有系统能修改
    
    # 我能做什么
    CAPABILITIES = [
        "provide_rpc",         # 提供 RPC 服务
        "manage_lifecycle",    # 管理生命周期
        "route_requests",      # 路由请求
        "collect_logs",        # 收集日志
    ]
    
    # 我不能做什么
    CANNOT_DO = [
        "handle_business",     # 不处理业务逻辑
        "serve_users",         # 不直接服务用户
        "modify_self",         # 不能修改自己
    ]
    
    # 我的接口契约
    INTERFACE = {
        "input_schema": "system.skill.input",
        "output_schema": "system.skill.output",
        "error_schema": "system.skill.error",
    }
```

### 3.2 从属 Skill（Subordinate Skill / Domain Service）

```
┌──────────────────────────────────────────────────────┐
│              从属 Skill 声明                           │
│                                                      │
│  我是谁: 领域服务（App 管理、用户管理等）              │
│  我的 ID: 无前缀（如 skill.conversation）              │
│  我的职责: 处理特定领域的业务逻辑                      │
│  我的依赖: 中心 Skill（MessageBus、ModelRouter 等）    │
│  谁能修改: 权限 ≥ skill.owner_role 的用户              │
│  谁能使用: 所有用户（查看 + 组装）                     │
└──────────────────────────────────────────────────────┘
```

| 从属 Skill | 职责 | 依赖的中心 Skill | 权限要求 |
|-----------|------|-----------------|----------|
| AppManagementWorker | App 注册/生命周期/安装 | MessageBus, LogCenter | admin+ |
| UserManager | 用户/权限/角色 | MessageBus, LogCenter | admin+ |
| SkillManager | Skill 工厂/注册/验证 | MessageBus, ModelRouter, LogCenter | admin+ |
| RefinementWorker | App 修改/精炼 | MessageBus, ModelRouter, LogCenter | admin+ |
| FileWorker | 持久化/升级/回滚 | MessageBus, LogCenter | root |
| MetaAppWorker | 元 App 设计/引导 | MessageBus, ModelRouter, LogCenter | admin+ |
| SuggestionWorker | 系统建议/可行性评估 | MessageBus, ModelRouter, LogCenter | user+（评估），admin+（执行） |

**从属 Skill 的核心声明：**
```python
class SubordinateSkillDeclaration:
    """我是从属 Skill，我的职责是：
    1. 处理特定领域的业务逻辑
    2. 通过中心 Skill 提供 RPC 服务
    3. 被用户 App 组合使用
    
    我的依赖：中心 Skill（MessageBus、ModelRouter 等）
    我的修改权限：owner_role 或更高权限的用户
    """
    
    WHO_AM_I = "subordinate.skill"
    MY_ROLE = "domain_service"
    
    # 每个 Skill 必须声明
    REQUIRED_FIELDS = [
        "skill_id",        # 唯一 ID
        "name",            # 名称
        "goal",            # 目标
        "owner_role",      # 拥有者角色（决定谁能修改）
        "capabilities",    # 能力列表
        "dependencies",    # 依赖的中心 Skill
        "input_schema",    # 输入格式
        "output_schema",   # 输出格式
        "error_schema",    # 错误格式
    ]
    
    # 我的依赖
    DEPENDENCIES = [
        "system.bus.*",      # MessageBus
        "system.log.*",      # LogCenter
        # 可选
        "system.router.*",   # ModelRouter（如果需要 LLM）
    ]
```

---

## 4. 新 App 创建时的完整声明

### 4.1 App 创建时必须包含的字段

```python
class AppCreationDeclaration:
    """新 App 创建时必须包含的完整声明。
    缺少任何字段都不允许创建。
    """
    
    # ── 必填字段（写死） ──────────────────────────────
    REQUIRED_FIELDS = {
        # 身份声明
        "id": "app.xxx",                    # App ID（全局唯一）
        "name": "小说 App",                  # 显示名称
        "goal": "帮助用户创作小说",           # 目标
        "version": "0.1.0",                 # 版本号
        
        # 权限声明
        "owner_user_id": "user_123",        # 创建者 ID
        "owner_role": "user",               # 创建者角色
        "owner_role_level": 0,              # 角色级别（写死）
        
        # 类型声明
        "app_kind": "service",              # App 类型
        "app_shape": "generic",             # App 形状
        
        # 技能声明
        "required_skills": ["skill.conversation"],  # 需要的 Skill
        "center_skills": ["system.bus.*"],           # 依赖的中心 Skill
        
        # 权限矩阵
        "permission_matrix": {
            "read": ["all"],                # 谁能查看
            "write": ["owner", "admin"],    # 谁能修改
            "execute": ["all"],             # 谁能执行
        },
        
        # 生命周期
        "lifecycle": {
            "created_at": "2026-04-14T03:10:00Z",
            "created_by": "user_123",
            "status": "active",
        },
        
        # 审计
        "audit": {
            "creation_log": "通过用户交互层创建",
            "approval_log": "主控授权通过",
        },
    }
    
    # ── 不可变字段（创建后不能修改） ─────────────────
    IMMUTABLE_FIELDS = [
        "id",
        "owner_user_id",
        "owner_role",
        "owner_role_level",
        "created_at",
        "created_by",
    ]
    
    # ── 可修改字段 ──────────────────────────────────
    MUTABLE_FIELDS = [
        "name",
        "goal",
        "version",
        "required_skills",
        "status",
    ]
```

### 4.2 App 创建流程（完整链路）

```
用户: "帮我创建一个小说 App"
        ↓
交互层:
  1. 理解意图 → intent: create_app
  2. 向主控请求授权:
     POST /master/auth/request
     { "user_id": "user_123", "operation": "create_app",
       "params": { "app_name": "小说 App", "skills": [...] } }
        ↓
主控:
  1. 检查权限: user_123 能创建 App 吗？
     → 是（仅复用已有 skill）
  2. 检查 skill 完整性: 所有 skill 都存在吗？
     → 是
  3. 生成 App 声明（包含所有必填字段）
  4. 记录审计日志
        ↓
主控返回授权: { granted: true, app_declaration: {...} }
        ↓
交互层:
  "好的，我来帮你创建小说 App。确认吗？"
  [✅ 确认] [❌ 取消]
        ↓ 用户确认
主控:
  1. 注册 App Blueprint（包含完整声明）
  2. 创建 App Instance
  3. 安装 App
  4. 记录审计日志
  5. 返回结果
        ↓
交互层:
  "✅ 小说 App 创建完成！"
```

---

## 5. 接口契约

### 5.1 主控 API 接口

```python
# ── 权限请求 ──────────────────────────────────────────
POST /api/v1/system/master/auth/request
Request:
{
    "user_id": "user_123",
    "operation": "modify_app",
    "target": "app_novel",
    "params": { "add": "对话功能" }
}
Response:
{
    "status": "granted",          # granted / denied / pending
    "message": "权限通过",
    "analysis": {                 # 可选：可行性分析
        "needs_new_skills": false,
        "risk_level": "low"
    }
}

# ── 执行操作 ──────────────────────────────────────────
POST /api/v1/system/master/execute
Request:
{
    "user_id": "user_123",
    "operation": "modify_app",
    "target": "app_novel",
    "params": { "add": "对话功能" }
}
Response:
{
    "status": "executed",
    "message": "修改完成",
    "data": {
        "app_id": "app_novel",
        "new_skills": ["skill.conversation"],
        "reused_skills": ["skill.memory"]
    }
}

# ── 系统建议 ──────────────────────────────────────────
POST /api/v1/system/master/suggest
Request:
{
    "user_id": "user_123",
    "category": "intent_understanding",
    "problem": "意图识别不准确",
    "expectation": "应该更准确理解用户需求"
}
Response:
{
    "status": "pending_approval",
    "suggestion_id": "sgt_xxx",
    "plan": {
        "target": "intent_analyzer",
        "actions": [
            {"type": "model_upgrade", "from": "qwen-turbo", "to": "qwen-plus"}
        ],
        "risk": "low",
        "estimated_cost": "额外 token 消耗 ~10%"
    },
    "required_role": "admin"
}

# ── 查询系统 ──────────────────────────────────────────
GET /api/v1/system/master/query
Request:
{
    "user_id": "user_123",
    "query_type": "system_logs",
    "params": { "limit": 10, "level": "ERROR" }
}
Response:
{
    "status": "ok",
    "data": [
        {"timestamp": "...", "level": "ERROR", "message": "..."},
        ...
    ]
}
```

### 5.2 Skill 接口契约

```python
# ── 中心 Skill 接口 ───────────────────────────────────
class CenterSkillInterface:
    """中心 Skill 的接口契约（写死）"""
    
    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string"},
            "action": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["skill_id", "action"],
    }
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["success", "error"]},
            "data": {"type": "object"},
            "error": {"type": "string"},
        },
        "required": ["status"],
    }

# ── 从属 Skill 接口 ───────────────────────────────────
class SubordinateSkillInterface:
    """从属 Skill 的接口契约（每个 Skill 必须声明）"""
    
    # 每个 Skill 必须定义
    REQUIRED_DECLARATION = {
        "skill_id": "string",         # 唯一 ID
        "name": "string",             # 名称
        "goal": "string",             # 目标
        "owner_role": "string",       # 拥有者角色
        "capabilities": ["string"],   # 能力列表
        "dependencies": ["string"],   # 依赖的中心 Skill
        "input_schema": "object",     # 输入格式
        "output_schema": "object",    # 输出格式
        "error_schema": "object",     # 错误格式
    }
```

---

## 6. 调用规则

### 6.1 谁能调用谁

```
用户 ──→ 交互层 ──→ 主控 ──→ 从属 Skill ──→ 中心 Skill
  │        │         │         │              │
  │        │         │         │              │
  └────────┴─────────┴─────────┴──────────────┘
            │         │         │
            │         │         └── 中心 Skill 只能被从属 Skill 调用
            │         │
            │         └── 主控可以直接调用从属 Skill
            │
            └── 交互层只能调用主控 API，不能直接调用 Skill
```

**调用规则（写死）：**
1. 用户只能跟交互层对话
2. 交互层只能调用主控 API
3. 主控可以直接调用从属 Skill
4. 从属 Skill 可以调用中心 Skill
5. 中心 Skill 只能被从属 Skill 调用
6. 从属 Skill 之间通过 MessageBus 互相调用

### 6.2 权限检查规则

```python
def check_permission(user_id: str, operation: str, target: str) -> bool:
    """统一权限检查入口（主控负责）"""
    
    user = get_user(user_id)
    target_info = get_target_info(target)
    
    # ── 系统级操作 ─────────────────────────────────
    if operation in ["system_upgrade", "modify_system_config"]:
        return user.role_level >= ROLE_LEVEL["root"]
    
    # ── Skill 操作 ─────────────────────────────────
    if operation.startswith("skill."):
        skill = get_skill(target)
        if operation == "skill.read" or operation == "skill.assemble":
            return True  # 所有用户都能查看和组装
        if operation == "skill.modify":
            return user.role_level >= skill.owner_role_level
    
    # ── App 操作 ───────────────────────────────────
    if operation.startswith("app."):
        app = get_app(target)
        if operation == "app.read" or operation == "app.execute":
            return True  # 所有用户都能查看和执行
        if operation == "app.modify":
            return user.role_level >= app.owner_role_level
    
    return False
```

---

## 7. 总结

### 7.1 核心原则

1. **每个组件必须声明"我是谁、我能做什么、我不能做什么"**
2. **交互层只调用主控 API，不直接操作资源**
3. **主控是唯一的权限决策者**
4. **中心 Skill 是不可变的基础设施**
5. **从属 Skill 有 owner_role，权限足够的用户才能修改**
6. **新 App 创建时必须包含完整声明，缺少任何字段都不允许**
7. **调用规则写死，不能跨层调用**

### 7.2 类比操作系统

| 系统组件 | 操作系统类比 |
|----------|-------------|
| 系统主控 | 内核（Kernel） |
| 用户交互层 | Shell（bash/zsh） |
| 中心 Skill | 内核模块（Kernel Module） |
| 从属 Skill | 系统服务（System Service） |
| 用户 App | 用户态应用（User-space App） |
| MessageBus | 进程间通信（IPC） |
| LogCenter | syslog/auditd |
| ModelRouter | 设备驱动（Device Driver） |

### 7.3 一句话总结

```
交互层是 Shell，主控是 Kernel，中心 Skill 是内核模块，
从属 Skill 是系统服务，用户 App 是用户态应用。
Shell 不直接操作硬件，只通过 Kernel 系统调用。
Kernel 不跟用户聊天，只提供系统调用接口。
```
