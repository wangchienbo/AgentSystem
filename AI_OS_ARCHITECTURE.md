# 新时代 AI 操作系统 —— 重构架构设计

> 定位：把 AgentSystem 从「内置几个 App 的平台」重构为「新时代 AI 操作系统」——
> 用户像用操作系统一样，通过统一入口**自由设计 App**、**用底层 Skill 组合 App**、安装/运行/管理 App。
> App 不是手写代码，而是由底层 Skill（原子能力）**声明式组合装配**而成。

---

## 一、产品愿景

AgentSystem 是一个 **AI 原生应用操作系统（AI OS）**：

- **内核（Kernel）**：统一管理权限、审计、生命周期、模型路由、上下文、任务调度 —— 已有 `master_control / runtime_center / context_center / model_router`。
- **能力层（Skill）**：原子能力单元，可复用、可组合、可治理 —— 已有 `system_skill_registry / skill_asset_service`。
- **应用层（App）**：由 Skill 组合装配的声明式程序，用户可自由设计 —— 已有 `app_designer / meta_app`。
- **入口层（Shell/工作台）**：统一对话入口 + App 桌面（浏览 / 启动 / 设计 / 管理）—— 已有对话 shell。

**一句话**：用户说「帮我做个 X App」，系统用底层 Skill 组合出一个可运行的 App —— 像操作系统按需装配程序，而不是每次重写代码。

---

## 二、现状能力盘点（已具备的基础，勿重复造轮子）

| # | 能力 | 实现 | 状态 |
|---|------|------|------|
| 1 | Skill 注册表 / 资产 | `app/skills/system_skill_registry.py` + `skill_asset_service.py` | ✅ 有 |
| 2 | App 架构设计（skill 组合） | `app/orchestration/app_designer/architect.py`（LLM 组合现有 skill，优先复用） | ✅ 有 |
| 3 | App 设计编排 | `app_designer/orchestrator.py`：intent→design→confirm→create | ✅ 有 |
| 4 | App 创建执行 | `app_create_modify_executor.py` + `app_mgmt` worker + `system_meta_app_worker` | ✅ 有 |
| 5 | App 生命周期查询 | `app_lifecycle_query_executor.py`（运行时视图 / 静态视图） | ✅ 有 |
| 6 | App 呈现 | `app_presenter.py`（列表 / 状态卡 / 确认 / 权限拒绝） | ✅ 有 |
| 7 | 对话 Shell | `app/static/index.html`（「用自然语言管理你的 App，一切皆可对话」） | ✅ 有 |
| 8 | 主控 / 治理 | `master_control` + `governance` API（回归 / 审计 / 队列） | ✅ 有 |
| 9 | 运行时 | `runtime_center / context_center / model_router` | ✅ 有 |

> **结论**：自由设计 App + Skill 组合的**后端闭环已经存在**。重构的重点是——
> **把零散能力整合、补全、产品化，形成完整、统一、像操作系统一样的新时代体验**，
> 并**验证「设计 → 装配 → 真实可运行」的端到端闭环**，而不只是生成蓝图。

---

## 三、目标分层架构

```
┌────────────────────────────────────────────────────────────┐
│  入口层 Shell / 工作台（OS 桌面）                            │
│   - 统一对话入口  - App 桌面（图标/启动/状态）                │
│   - Skill 库浏览  - 自由设计 App 向导                        │
├────────────────────────────────────────────────────────────┤
│  应用层 App（声明式 Manifest = Skill 组合）                   │
│   - App Manifest：skills[] + entrypoints + config + 权限     │
│   - App 装配器：manifest → 可运行实例                        │
├────────────────────────────────────────────────────────────┤
│  能力层 Skill（原子能力，可组合/复用/治理）                    │
│   - 声明式定义：id/名称/输入输出/runtime_adapter/依赖资产      │
├────────────────────────────────────────────────────────────┤
│  运行时 Runtime                                             │
│   - 会话上下文  - 模型路由  - 任务调度  - App 实例生命周期      │
├────────────────────────────────────────────────────────────┤
│  内核 Kernel（Master Control）                              │
│   - 权限  - 审计  - 生命周期  - 能力声明                      │
└────────────────────────────────────────────────────────────┘
```

**核心机制：App = Skill 组合**（已有 AppArchitect）
1. 用户表达诉求 → `intent_analyzer` 结构化意图
2. `architect` 检索 Skill 库 → 组合复用现有 Skill + 按需新建
3. `orchestrator` 确认 → 创建 Skill → 装配 Blueprint → 安装 App
4. 用户从工作台启动 / 运行 / 管理该 App

---

## 四、差距分析（重构要补的）

| # | 差距 | 现状 | 重构目标 |
|---|------|------|----------|
| G1 | **App 目录 / 状态卡** | 只能对话查询 app 列表 | 统一 App 桌面，图标化列出已装 App + 运行状态 + 一键启动 |
| G2 | **Skill 库可发现性** | architect 内部注入 skill 清单，但用户看不到 | 工作台提供 Skill 库浏览，让用户设计前知道有哪些可复用能力 |
| G3 | **自由设计入口** | 需对话命令（隐晦） | 提供「设计 App」向导：描述诉求 → 预览 skill 组合方案 → 确认 → 装配 |
| G4 | **装配可运行性验证** | 设计产出 blueprint，未见真实可运行闭环 | 验证「设计 → 装配 → 真实可运行」，设计出的 App 能启动 |
| G5 | **生命周期管理 UI** | 有查询服务，无统一管理界面 | App 启停 / 卸载 / 状态可视化 |

---

## 五、落地路径（MVP → 增强）

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| M0 | **基线验证**：对话触发「创建 App」闭环能否跑通（不改变系统，只验证） | 现有闭环可运行 / 明确断点 |
| M1 | **App 目录 & 状态卡**：统一列出已装 App + 运行状态 | API 返回完整 App 目录；前端可展示 |
| M2 | **Skill 库浏览**：工作台可查看可复用 Skill 清单 | 前端展示 skill 库 |
| M3 | **工作台桌面化**：入口整合（App 图标 + 设计入口 + 管理） | 统一工作台可浏览 / 启动 / 设计 |
| M4 | **装配运行闭环**：设计→装配→真实可运行验证 | 设计出的 App 可启动运行 |
| M5 | **治理产品化**：权限 / 审计 / 生命周期可视化 | 治理数据产品化呈现 |

---

## 六、验收标准

1. 通过对话 / 界面能**自由设计**一个新 App（组合现有 Skill，而非手写代码）
2. 设计出的 App **装配后可运行**
3. 统一入口能**浏览 / 启动 / 管理**所有 App 与 Skill
4. 全程符合 AgentSystem 架构约定（4-Layer Bootstrap、零硬编码、治理贯穿）

---

## 落地状态（2026-08-09 更新）

| 里程碑 | 状态 | 落地证据 |
|--------|------|----------|
| M0 基线验证 | ✅ | 对话触发「创建 App」闭环可运行 |
| M1 App 目录 & 状态卡 | ✅ | `/api/os/overview` 返回完整 App 目录（含真实实例状态） |
| M2 Skill 库浏览 | ✅ | 工作台展示 15 个可复用 Skill |
| M3 工作台桌面化 | ✅ | `index.html` 登录后「🖥️」导航 → `/workbench` 统一工作台 |
| M4 装配运行闭环 | ✅ | 通过 `/api/os/apps/create` 用 Skill 组合实际创建 4 个可运行 App |
| M5 治理产品化 | ✅ | `/api/os/governance` + 工作台治理概览区块（审计/操作分类/最近记录） |

### 工作台功能闭环（G1–G5 差距补全）

| 差距 | 落地 |
|------|------|
| G1 App 目录/状态卡 | 工作台列出已装 App + 运行状态徽标 |
| G2 Skill 库可发现性 | Skill 卡片点击展开详情（适配器/版本/依赖/标签/能力画像） |
| G3 自由设计入口 | 工作台「自由设计新 App」textarea → `/api/os/apps/create` |
| G4 装配可运行性 | 实际创建 4 个 App（个人财务/待办/饮水/阅读打卡）均 running |
| G5 生命周期管理 UI | App 卡片启动/停止/删除按钮 → `/api/os/apps/{id}/start\|stop` + DELETE |

### 后端 OS API（app/system/http_test_server.py）

| 端点 | 说明 |
|------|------|
| `GET /api/os/overview` | 工作台统一数据（App 目录 + Skill 库 + 实例状态） |
| `GET /api/os/skills/{id}` | Skill 详情（回退 SYSTEM_SKILL_SPECS 兜底，保证 15 个 skill 全部可查） |
| `GET /api/os/governance` | 治理概览（审计事件 + 动作分类统计） |
| `POST /api/os/apps/create` | 确定性自由设计 App（intent→skill 组合→装配→安装） |
| `POST /api/os/apps/{id}/start\|stop\|pause\|resume` | 生命周期转换 |
| `DELETE /api/os/apps/{id}` | 卸载 App |

### 治理审计数据源

OS 端点（create/start/stop/pause/resume/delete）通过 `_os_audit()` 写入 `audit_logger`，
供 `/api/os/governance` 与工作台治理看板消费，保证治理数据**非空可验证**（闭环）。

### E2E 回归（Playwright）

正式套件：`tests/e2e/test_os_workbench_e2e.py`（Python playwright，`.venv/bin/python` 运行）

```bash
# 先启动服务器
python -m uvicorn app.system.http_test_server:app --port 8765
# 跑全量回归（OS API 层 + 工作台 UI）
.venv/bin/python tests/e2e/test_os_workbench_e2e.py
# 只跑 OS API 层（不经浏览器）
.venv/bin/python tests/e2e/test_os_workbench_e2e.py --api
```

覆盖：工作台加载 / App 生命周期按钮 / Skill 详情展开 / 治理概览 / 自由设计闭环 —— 100% 通过，无 console/page 错误。


---

## 七、设计原则（延续用户偏好）

- **零硬编码**：App 与 Skill 全部声明式定义，代码只做装配机械逻辑
- **组合优先**：设计 App 时优先复用现有 Skill，按需才新建
- **先验证后扩大**：M0 先验证现有闭环，再逐里程碑推进
- **架构约定**：新能力遵循 4-Layer Bootstrap（Router/Blueprint/Asset/Worker）+ 主控治理
