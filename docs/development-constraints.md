# Development Constraints (开发约束指南)

> **用途**：AI 模型在开发/修改 AgentSystem 代码时必须遵守的约束合集。  
> **目标**：防止代码漂移、架构退化、约束遗忘。  
> **维护规则**：任何架构级变更都需要同步更新本文件。

---

## 1. 架构核心原则（不可违背）

### 1.1 App 是第一公民
- 用户通过 **App** 交互，不直接操作 Skill
- 用户命令 → Workflow → App 生命周期操作
- 每个 App 是独立的隔离单元（光脑模型）

### 1.2 确定性优先
- 能用确定性逻辑解决的，**禁止用 LLM**
- LLM 仅用于语义理解、生成、诊断、抽象
- 系统 core 必须保持 thin，能力扩展优先通过 Skill 增长

### 1.3 数据分层隔离
| 层级 | 存放 | 说明 |
|------|------|------|
| App 业务数据 | `data/<app_id>/` | 持久化，随 App 实例 |
| 运行时状态 | `data/runtime/` | 重启后可恢复 |
| 系统元数据 | `data/metadata/` | 注册表、配置 |
| Skill 资产 | `data/skill_assets/` | core/candidates/archived |

### 1.4 智能调用治理
- **禁止**因为模型可用就默认调用智能 Skill
- 智能调用需满足：步骤需要 + 策略允许 + 预算允许 + 用户确认（如策略要求）
- 默认 ask-before-intelligence posture

---

## 2. Skill 分层规则

### 2.1 Skill 分类

| 类型 | 目录 | 运行时关键性 | 本地优先 | 禁止默认智能 |
|------|------|-------------|---------|-------------|
| `system.*` | `app/services/system_skills/` | required_runtime | ✅ | ✅ |
| `requirement.*` | builder skill | build_only | ❌ | ❌ |
| `blueprint.*` | builder skill | build_only | ❌ | ❌ |
| `workflow.*` | builder/runtime skill | build_or_optional | ❌ | ❌ |
| `self_refinement` | builder skill | build_or_optional | ❌ | ❌ |

### 2.2 新增 Skill 检查清单
1. 确定分类（system / builder / app / runtime）
2. 查阅 `docs/skill-design-principles.md`
3. 创建 `manifest.json`（identity + version + capability metadata）
4. 创建 `metadata.json`（status + origin + adapter + version）
5. 定义 input/output/error contracts（JSON Schema）
6. 创建 entrypoint 文件
7. 在 `SYSTEM_SKILL_SPECS` 中注册（如果是 system skill）
8. 编写 smoke test
9. 更新 `docs/system-relationship-map.md`

### 2.3 Skill 目录结构
```
data/skill_assets/core/<skill_id>/
├── manifest.json          # 包描述
├── metadata.json          # 运行时元数据
├── schemas/
│   ├── input.json         # 输入契约
│   ├── output.json        # 输出契约
│   └── error.json         # 错误契约
├── entrypoint.py          # 执行入口
├── README.md              # 说明
└── tests/
    └── smoke_test.py      # 冒烟测试
```

### 2.4 Skill 运行时分发
- 所有 Skill 调用必须通过 `system.skill_runtime` 统一入口
- 禁止 Skill 之间直接互相调用
- 分发由 orchestrator 中介，强制执行：超时、重试、审计、权限

---

## 3. App 设计规范

### 3.1 App 定义流程
```
Blueprint（定义模板）→ Install（安装实例）→ Runtime（运行）→ Persist（持久化）
```

### 3.2 Blueprint 必须包含
- `goal` — 目标描述
- `roles` — 角色定义
- `tasks` — 任务列表
- `workflows` — 工作流定义
- `required_modules` — 依赖模块
- `required_skills` — 依赖 Skill
- `storage_plan` — 数据存放计划
- `runtime_policy` — 运行时策略

### 3.3 Runtime Policy 必须定义
- `execution_mode`: `service` | `pipeline`
- `activation_mode`: 如何激活
- `restart_policy`: 重启策略
- `persistence_level`: 持久化级别
- `intelligence_behavior`: 智能调用策略

### 3.4 App 隔离约束
- App 不得直接访问其他 App 的 data 或 context
- 所有跨 App 通信通过 event bus
- App 的 namespace 在安装时自动创建

### 3.5 App 独立交互界面（设计规则）
每个 App 可以（也鼓励）提供自己的独立交互界面，让用户可以直接与 App 交互，而不必绕道通用聊天入口。

**规则要求**：

1. **UI 层**：App 的交互界面可以是独立的 HTML 页面（`/app/{app_id}`），通过 Jinja2 模板渲染
2. **API 层**：App 的业务 API 路由（`/api/{app_id}/*`）和 UI 路由必须一起注册到主控 FastAPI 应用
3. **发现层**：App 必须同时注册 AppBlueprint（主控 App 发现）+ RuntimeAsset（模型可发现资产）+ MasterControl Worker（异步调度）
4. **注册入口**：所有 App 的注册逻辑统一放在 `app/{app_name}/bootstrap.py` 中，通过 `bootstrap_novel_studio()` 这样的引导函数暴露
5. **双入口**：用户可以通过两个入口使用 App：
   - 主控聊天入口：用户输入自然语言 → LightBrain Gateway → 路由到 App
   - 独立 UI 入口：用户直接访问 `/app/{app_id}` 页面
6. **持久化**：App 的所有数据状态（存储引擎）必须在引导时创建，并注入到 runtime_services 中共享

---

## 4. 上下文分层与读取规范

### 4.1 上下文层级
| 层级 | 内容 | 加载策略 |
|------|------|---------|
| L0 Working Set | 当前目标、阶段、活跃约束、开放循环 | 每次必载 |
| L1 Task/App Summary | 进展摘要、重大决策、未决问题 | 按需选择加载 |
| L2 Execution Detail | 步骤级细节、日志、中间输入输出 | 仅引用查询，不全文加载 |
| L3 Long-term Experience | 可复用教训、模式、操作知识 | 仅检索相关条目 |

### 4.2 大文件读取规则
- **禁止**一次性读取 > 50KB 的文件全文
- 优先使用 `grep_search`、`execute_shell_command`（head/tail/grep）进行检索式读取
- 只读需要的行范围（使用 `read_file` 的 `start_line`/`end_line` 参数）
- 先读目录/索引文件了解结构，再精准定位

### 4.3 Context Upload 白名单
**允许**上传到上下文的内容：
- `user_message` — 用户原始消息
- `assistant_reply` — assistant 最终回复
- `dispatch_decision` — 分发决策
- `structured_result` — 结构化结果
- `system_note` — 短 system note（< 500 chars）

**禁止**上传：
- scratchpad / chain_of_thought
- 全量工具调用流水
- 中间失败尝试
- 长篇自由文本总结

详见 `docs/context-upload-policy.md`

---

## 5. 代码结构约束

### 5.1 模块放置规则

| 功能类型 | 放置位置 |
|---------|---------|
| 系统 Skill 实现 | `app/services/system_skills/` |
| 业务服务 | `app/services/` |
| 数据模型 | `app/models/` |
| API 路由 | `app/api/` |
| App 引导/集成 | `app/{app_name}/bootstrap.py` |
| 运行时核心 | `app/runtime/` |
| 编排引擎 | `app/orchestration/` |
| 持久化 | `app/persistence/` |
| CLI 命令 | `app/cli.py` + `app/cli/` |
| 测试 | `tests/` |
| 文档 | `docs/` |

### 5.2 新增 API 端点规则
1. 在 `app/api/` 下创建或扩展现有 router
2. 在 `app/system/http_test_server.py` 中 `include_router`
3. 更新 `docs/code-structure.md`
4. 编写 API 测试

### 5.3 新增 CLI 命令规则
1. 在 `app/cli.py` 中添加子命令解析
2. 实现命令逻辑为独立函数（返回 `CLIResult`）
3. 更新 `README.md` 的 Operator CLI 部分

### 5.4 依赖注入
- 使用 `app/bootstrap/runtime.py` 构建服务图
- 新服务必须在 bootstrap 中注册
- 禁止在业务代码中直接实例化核心服务

### 5.5 兼容性包装
- 遗留代码标记为 migration shim
- 新代码不应依赖 shim，应直接使用新实现
- 删除 shim 前确保无调用者

---

## 6. 测试要求

### 6.1 测试层级
| 层级 | 覆盖范围 | 位置 |
|------|---------|------|
| 单元测试 | 单个服务/模型/工具函数 | `tests/unit/` |
| 集成测试 | 服务间交互 | `tests/integration/` |
| E2E 测试 | 完整用户场景 | `tests/e2e/` |
| API 回归 | 端点兼容性 | `tests/api/` |

### 6.2 新增功能测试要求
- 每个新 service 至少 1 个单元测试
- 每个新 API 端点至少 1 个 API 回归测试
- 涉及状态变更的功能需要集成测试
- Skill 必须有 smoke test

### 6.3 运行测试
```bash
pytest -q                          # 快速单元+集成
pytest tests/e2e/ -v               # E2E 测试
python run_e2e_test.py             # 完整 E2E
```

---

## 7. 开发前必读文件清单

### 7.1 改什么读什么

| 要修改的内容 | 先读这些 |
|-------------|---------|
| 运行时 bootstrap | `app/bootstrap/runtime.py` → `skills.py` → `catalog.py` → `app/api/main.py` |
| 系统 Skill | `docs/skill-design-principles.md` → `app/services/system_skills/README.md` → `system_skill_registry.py` → 目标文件 |
| Skill 包结构 | `models/skill_control.py` → `skill_manifest.py` → `skill_adapter.py` → `skill_asset.py` → `skill_manifest_validator.py` → `skill_runtime.py` → `skill_asset_service.py` → `docs/skill-asset-governance.md` |
| 交互层 | `services/llm_interaction_gateway.py` → `conversation_session.py` → `conversation_router.py` → `response_serializer.py` → `models/chat.py` |
| 新增模块 | 本文档 + `docs/code-structure.md` + `docs/system-relationship-map.md` |

### 7.2 全局约束文档
- `docs/requirements.md` — 产品需求
- `docs/design.md` — 架构设计
- `docs/skill-design-principles.md` — Skill 设计原则
- `docs/skill-asset-governance.md` — Skill 资产治理
- `docs/context-upload-policy.md` — 上下文上传策略
- `docs/system-relationship-map.md` — 系统关系图
- `docs/code-structure.md` — 代码结构地图

---

## 8. 变更影响分析

### 8.1 修改代码前必须
1. 查阅 `docs/system-relationship-map.md` 确认影响范围
2. 确认是否有相关测试覆盖
3. 评估是否需要更新文档

### 8.2 必须同步更新的文件
| 变更类型 | 同步更新 |
|---------|---------|
| 新增/删除系统 Skill | `SYSTEM_SKILL_SPECS` + `skill-design-principles.md` + `system-relationship-map.md` |
| 新增 API 端点 | `code-structure.md` + API 测试 |
| 新增 CLI 命令 | `README.md` Operator CLI 部分 |
| 变更数据模型 | 相关验证测试 |
| 变更 bootstrap | `code-structure.md` |
| 架构级变更 | 本文档 |

---

## 9. 禁止事项

### 9.1 代码层面
- ❌ 在系统核心服务中直接使用 LLM 调用（必须通过 Skill 层）
- ❌ 跨模块直接 import 内部实现（必须通过公开接口）
- ❌ 在 API handler 中写业务逻辑（必须下沉到 service 层）
- ❌ 硬编码路径（必须使用 `resolve_runtime_paths()`）
- ❌ 跳过 bootstrap 直接实例化服务

### 9.2 架构层面
- ❌ 向核心平台添加可通过 Skill 实现的功能
- ❌ 让 App 直接访问另一个 App 的数据或上下文
- ❌ 在不更新 system-relationship-map 的情况下变更模块边界
- ❌ 在不更新本文档的情况下变更架构约束

### 9.3 开发流程层面
- ❌ 不写测试就合并代码
- ❌ 不读约束文档就开始改代码
- ❌ 一次性读取超大文件（> 50KB），应检索式读取
- ❌ 忽略现有兼容性包装直接修改底层

---

## 10. 快速参考

### 10.1 项目启动
```bash
cd /root/projects/AgentSystem
./setup_and_start.sh              # 一键安装+启动
./setup_and_start.sh --port 8765  # 指定端口
./setup_and_start.sh --install-only  # 只安装
```

### 10.2 开发服务器
```bash
source .venv/bin/activate
uvicorn app.system.http_test_server:app --reload --port 8765
```

### 10.3 下载服务（系统级）
```
POST /api/download/folder    # 压缩文件夹，返回下载链接
GET  /api/download/list      # 列出可用下载
GET  /api/download/{filename} # 获取下载元信息
GET  /download/{filename}     # 实际下载文件
```

### 10.4 关键路径
```
项目根目录:  /root/projects/AgentSystem
运行时数据:  ~/.local/share/agentsystem/
配置文件:    ~/.config/agentsystem/config.yaml
日志:        ~/.local/share/agentsystem/logs/
```

---

**最后更新**: 2026-05-23  
**维护者**: AgentSystem 开发团队（人类 + AI）
