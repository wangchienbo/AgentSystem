# 主控重构方案：Master Control = 操作系统内核层

> 设计时间: 2026-04-14
> 状态: 方案设计完成，待实施

---

## 1. 核心理念

**主控 = 操作系统内核 = 全局唯一系统级 App**

- 拥有自己的 `AppBlueprint` 和 `AppInstance`
- 在 registry 中标记为 `system: true, immutable: true`
- 所有系统操作的唯一入口
- 不直接跟用户对话，通过交互层间接交互

**用户交互层 = Shell**

- 接收用户输入，理解意图
- 管理会话上下文、多轮对话
- 向主控请求授权 → 授权通过后执行
- 格式化输出给用户

---

## 2. 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                    用户空间 (User Space)                        │
│  ┌────────────────────────────────────────────────────┐      │
│  │         用户交互层 (Shell)                           │      │
│  │  • 接收用户输入，做意图理解                            │      │
│  │  • 管理会话上下文、多轮对话状态                        │      │
│  │  • 向主控请求授权 → 授权通过后执行                    │      │
│  │  • 格式化输出，生成回复                                │      │
│  └────────────────────────────────────────────────────┘      │
│                          ▲ 调用                                │
│                          │ 请求授权                             │
├──────────────────────────┼────────────────────────────────────┤
│    内核空间 (Kernel Space)│                                    │
│  ┌───────────────────────▼────────────────────────────┐      │
│  │              主控 (Master / Kernel)                  │      │
│  │  app_id: "system.master" (全局唯一，不可删除)         │      │
│  │                                                      │      │
│  │  ┌─ 中心 Skill (基础设施, 系统内建) ───────────┐     │      │
│  │  │  MessageBus │ ModelRouter │ WorkerManager  │     │      │
│  │  │  LogCenter  │ SkillMeta   │ PathStore      │     │      │
│  │  └────────────────────────────────────────────┘     │      │
│  │         ▲              ▲              ▲            │      │
│  │         │ RPC          │ RPC          │ RPC         │      │
│  │  ┌─ 从属 Skill (子模块, 领域服务) ───────────┐     │      │
│  │  │  AppManagementWorker (app注册/生命周期/安装)│     │      │
│  │  │  UserManager (用户/权限/角色)               │     │      │
│  │  │  SkillManager (skill工厂/注册/验证/修改)    │     │      │
│  │  │  RefinementWorker (App修改/精炼)            │     │      │
│  │  │  FileWorker (持久化/升级/回滚)              │     │      │
│  │  │  MetaAppWorker (元App设计/引导)             │     │      │
│  │  │  SuggestionWorker (系统建议/可行性评估)     │     │      │
│  │  └────────────────────────────────────────────┘     │      │
│  │                                                      │      │
│  │  ┌─ 用户 App 层 ───────────────────────────┐        │      │
│  │  │  用户创建的 App (由从属 skill 组合而成)   │        │      │
│  │  └──────────────────────────────────────────┘        │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 资产分类与权限模型

### 3.1 资产分类

| 资产类型 | 归属 | 谁能查看 | 谁能修改 | 谁能组装 |
|----------|------|----------|----------|----------|
| **中心 Skill** | 系统内建 | 所有用户 | 系统自身 | 所有用户 |
| **从属 Skill** | 系统共有 | 所有用户 | 权限 ≥ skill 本身的用户 | 所有用户 |
| **用户 App** | 创建者所有 | 所有用户 | 权限 ≥ App owner 的用户 | 所有用户 |
| **系统配置** | 系统 | admin+ | root | 只读 |
| **日志/审计** | 系统 | admin+ | root | 只读 |

### 3.2 权限级别

```python
ROLE_LEVEL = {
    "user": 0,    # 普通用户：查看 + 组装 + 修改自己的 App
    "admin": 1,   # 管理员：创建/修改 skill + 审批系统建议
    "root": 2,    # 超级管理员：系统升级 + 权限管理 + 全部操作
    "system": 99, # 系统自身：不可修改，只能由系统自我升级
}
```

### 3.3 Skill 权限规则

```
Skill 有 owner_role 属性（创建时决定）：

if user.role_level >= skill.owner_role_level:
    → 用户可以查看 + 修改 + 组装该 skill
else:
    → 用户只能查看 + 组装该 skill，不能修改
```

示例：
- `skill.conversation` 由 admin 创建，`owner_role = "admin"`
  - admin/root 用户可以修改
  - user 用户只能查看和组装
- `skill.echo` 由系统内建，`owner_role = "system"`
  - 只有系统自身可以修改
  - admin/root/user 都只能查看和组装

---

## 4. 交互链路

### 4.1 链路 A：用户级修改（改自己的 App）

```
用户: "给小说 App 加个对话功能"
        ↓
交互层:
  1. 理解意图 → intent: modify_app
  2. 向主控请求授权:
     POST /master/auth/request
     { "user_id": "user_123", "operation": "modify_app",
       "target": "app_novel", "params": { "add": "对话功能" } }
        ↓
主控 (权限层):
  1. 查: user_123 的角色 level ≥ App owner level 吗？
  2. dry-run 分析: "对话功能" 需要新 skill 吗？
     → 需要 → 检查 user_123 有创建 skill 权限吗？
     → 没有 → 拦截
        ↓ 返回
交互层:
  "这个修改需要新 skill，只有管理员能创建。
   请联系管理员或联系已有 skill 重新组合。"
```

**权限通过时：**
```
交互层:
  "好的，我来帮你修改小说 App。确认吗？"
  [✅ 确认] [❌ 取消]
        ↓ 用户确认
交互层:
  POST /master/execute
  { "operation": "modify_app", "target": "app_novel", ... }
        ↓
主控 (执行层):
  1. 记录审计日志
  2. 调用 RefinementWorker
  3. 生成/复用 skill → 安装到 App
  4. 返回结果
        ↓
交互层:
  "✅ 小说 App 修改完成！"
```

### 4.2 链路 B：系统级修改（系统升级/自我迭代）

```
用户: "我觉得意图理解太差了，经常误解我的意思"
        ↓
交互层:
  "能举个最近的例子吗？"
  → 收集更多细节...
        ↓
用户: "我说'写小说'，它却创建了监控 App"
        ↓
交互层:
  POST /master/suggest
  { "user_id": "user_123", "category": "intent_understanding",
    "problem": "意图识别不准确", "expectation": "应该创建小说 App" }
        ↓
主控 (评估层):
  1. 分析: 这是 intent_analyzer 模块的问题
  2. 评估可行性:
     - 需要升级模型吗？可以
     - 需要修改 prompt 吗？可能
     - 风险等级: 低
  3. 生成修改方案
  4. 记录审计
        ↓
交互层 (拿到方案，和用户讨论):
  "系统分析后可以通过以下方式改善：
   1. 升级意图分析模型（qwen-turbo → qwen-plus）
   2. 优化 prompt，增加上下文感知
   预计额外消耗 ~10% token。要试试吗？"
   
   [✅ 执行] [✏️ 修改方案] [❌ 算了]
        ↓
用户: "先升级模型吧"
        ↓
交互层:
  POST /master/suggest/revise
  { "suggestion_id": "sgt_xxx", "actions": ["model_upgrade"] }
        ↓
主控:
  1. 重新评估方案
  2. 检查权限: user_123 是 admin 吗？
     → 不是 → 需要 admin 审批
  3. 记录审计
        ↓
交互层:
  "这个修改需要管理员审批。已提交申请。"
```

### 4.3 链路 C：Skill 修改（有权限的用户）

```
用户 (admin): "修改 skill.conversation，增加多轮对话支持"
        ↓
交互层:
  POST /master/auth/request
  { "user_id": "admin_1", "operation": "modify_skill",
    "target": "skill.conversation", "params": { "add": "多轮对话" } }
        ↓
主控:
  1. 查: skill.conversation 的 owner_role 是什么？
     → "admin"
  2. 查: admin_1 的角色 level ≥ "admin" 吗？
     → 是 → 权限通过
  3. dry-run 分析修改影响
  4. 记录审计
        ↓
交互层:
  "确认修改 skill.conversation？会影响以下 App:
   - 小说 App
   - 客服 App
   
   确认执行？"
  [✅ 确认] [❌ 取消]
        ↓ 用户确认
主控:
  1. 调用 SkillManager 修改
  2. 更新所有依赖 App 的版本引用
  3. 记录审计
  4. 返回结果
```

### 4.4 链路 D：Skill 查看/组装（无修改权限的用户）

```
用户 (user): "我想用 skill.conversation 创建一个客服 App"
        ↓
交互层:
  1. 查: skill.conversation 可以被 user 用户组装吗？
     → 可以（所有用户都能组装）
  2. 向主控请求:
     POST /master/execute
     { "operation": "create_app", "user_id": "user_123",
       "skills": ["skill.conversation", "skill.memory"], ... }
        ↓
主控:
  1. 检查权限: user_123 能创建 App 吗？
     → 可以（仅复用已有 skill）
  2. 记录审计
  3. 执行创建
        ↓
交互层:
  "✅ 客服 App 创建完成！"
```

---

## 5. 统一 API 入口

### 5.1 主控 API

```
POST /api/v1/system/master/execute
  → 执行操作（需要权限）
  → 支持: create_app, modify_app, delete_app, create_skill, modify_skill, ...

POST /api/v1/system/master/auth/request
  → 请求权限授权（检查可行性）
  → 返回: granted / denied + 原因 + 建议

POST /api/v1/system/master/suggest
  → 提交系统级建议
  → 返回: 可行性分析 + 修改方案 + 所需权限

POST /api/v1/system/master/suggest/revise
  → 修改建议方案
  → 返回: 更新后的方案

POST /api/v1/system/master/suggest/approve
  → 审批并执行建议（admin+）
  → 返回: 执行结果

GET /api/v1/system/master/query
  → 查询系统状态/日志/架构（只读）
  → 返回: 原始数据
```

### 5.2 请求/响应格式

```python
class MasterRequest(BaseModel):
    operation: str          # execute, auth/request, suggest, query
    user_id: str
    params: dict
    session_id: str | None = None

class MasterResponse(BaseModel):
    status: str             # granted, denied, pending, executed, error
    message: str
    data: dict | None = None   # 原始数据
    plan: dict | None = None   # 修改方案
    required_role: str | None = None
    suggestion_id: str | None = None
```

---

## 6. 职责划分总结

### 6.1 用户交互层（Shell）

| 职责 | 说明 |
|------|------|
| 意图理解 | 接收用户输入，理解意图 |
| 会话管理 | 管理多轮对话状态 |
| 格式化输出 | 把数据翻译成用户友好的格式 |
| 请求授权 | 向主控请求权限 |
| 收集意见 | 引导用户补充系统建议细节 |
| 解释方案 | 把技术方案翻译成用户语言 |
| 多轮讨论 | 和用户讨论修改方案 |

### 6.2 主控（Kernel）

| 职责 | 说明 |
|------|------|
| 权限审批 | 检查用户是否有权限执行操作 |
| 可行性评估 | 评估系统建议的可行性 |
| 生成方案 | 生成技术修改方案 |
| 日志审计 | 记录所有操作日志 |
| 系统升级 | 执行系统级升级/回滚 |
| Skill 管理 | Skill 创建/修改/注册/验证 |
| App 管理 | App 注册/生命周期/安装 |
| 基础设施 | MessageBus, ModelRouter, PathStore |
| 自己的 App 管理 | 主控自身的生命周期管理 |

### 6.3 交互原则

```
交互层不懂系统架构 → 但知道调用哪个系统 API
主控懂系统架构 → 但不直接跟用户对话
用户不需要懂系统 → 只需要说"哪里不好，想改成什么样"
```

---

## 7. 实施步骤

### Phase 1: 主控注册为系统 App
- [ ] 创建 `system.master` 的 AppBlueprint
- [ ] 注册到 AppRegistry（system: true, immutable: true）
- [ ] 创建 AppInstance
- [ ] 在 list_apps 中可见

### Phase 2: 锚点兼容
- [ ] `execute_action` 补上 modify_app 确认处理
- [ ] 所有确认按钮统一走 `/master/auth/request` 然后 `/master/execute`

### Phase 3: 从属 Skill Worker 封装
- [ ] AppManagementWorker（封装 AppRegistry + Lifecycle + Installer）
- [ ] UserManager（封装 UserService + PermissionSkill）
- [ ] SkillManager（封装 SkillFactory + SkillControl + Validation）
- [ ] RefinementWorker（封装 AppRefinementOrchestrator）
- [ ] FileWorker（封装 PersistenceService + UpgradeService）
- [ ] SuggestionWorker（新增：系统建议/可行性评估）

### Phase 4: 统一 API
- [ ] `POST /api/v1/system/master/execute`
- [ ] `POST /api/v1/system/master/auth/request`
- [ ] `POST /api/v1/system/master/suggest`
- [ ] `GET /api/v1/system/master/query`

### Phase 5: Skill 权限模型
- [ ] Skill 增加 `owner_role` 字段
- [ ] 修改权限检查: user.role_level >= skill.owner_role_level
- [ ] 所有用户都能查看/组装，只有权限足够的能修改

### Phase 6: 系统建议流程
- [ ] 交互层收集用户意见
- [ ] 主控评估可行性
- [ ] 多轮讨论 → 确认 → 执行

---

## 8. 现有代码对应关系

| 现有 | 新架构中 |
|------|---------|
| `LightBrainGateway` | 拆分为 UserInteractionLayer + MasterControl |
| `_handle_modify_app` | 交互层 → 主控 auth/request → RefinementWorker |
| `_execute_create_app` | 交互层 → 主控 auth/request → AppManagementWorker |
| `_check_app_modify_permission` | 主控权限层的一部分 |
| `GatewayOrchestratorBridge` | 交互层 → 从属 Worker 的路由层 |
| `system_skill_registry.py` | 中心 Skill 注册表 |
| 直接注入的 15+ 服务 | 封装为从属 Worker，通过 Bus RPC 调用 |
