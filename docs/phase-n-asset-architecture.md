# Phase N：资产包管理架构（进程自注册模型）

> 设计时间：2026-04-16
> 状态：方案设计，待实现

---

## 一、核心架构原则

### 1.1 进程即包

每个进程是完整、独立的运行体。打包时将所有依赖代码完整复制，不共享。
一个进程 = 一个包 = 独立代码副本。

**为什么这样：**
- 消除交叉依赖导致的隐性耦合
- 升级一个包不影响其他包
- 回退简单且安全

### 1.2 资产中心（Registry）

负责记录**静态位置信息**：包路径、版本、启动命令、依赖声明。

```
资产中心 (data/asset_registry.json)
───────────────────────────────────────
app.novel/       version=1.2.0  location=./installed/app.novel/   entry=main.py  owner=wangchienbo
app.qa/          version=1.0.0  location=./installed/app.qa/       entry=main.py  owner=wangchienbo
skill.chat/      version=0.3.0  location=./installed/skill.chat/  entry=handler.py  owner=system
system/          version=2.1.0  location=./installed/system/       entry=gateway  owner=system
```

### 1.3 运行资源中心

负责记录**动态运行时信息**：哪些进程在跑、状态、endpoint。

```
运行资源中心 (data/runtime_center.json)
───────────────────────────────────────
app.novel/  status=running  pid=12345  endpoint=http://localhost:8001  uptime=2h
app.qa/     status=stopped   pid=null   endpoint=null                  uptime=0
```

### 1.4 自注册 + 自注销

每个进程启动时调用标准接口向运行资源中心注册自己；退出时注销自己。
进程崩溃？由心跳检测发现后由 MasterControl 清理。

---

## 二、包粒度设计

按进程边界划分，四类包：

| 包类型 | asset_type | 安装路径 | 启动方式 | 可卸载 |
|--------|-----------|---------|---------|--------|
| **system** | `system` | `installed/system/` | 内建，不走 Tool | ❌ |
| **app** | `app` | `installed/app.{name}/` | `start_asset` Tool | ✅ |
| **skill** | `skill` | `installed/skill.{name}/` | 作为 App/System 的依赖被加载 | ✅ |
| **shared** | `shared` | `installed/shared.{name}/` | 无独立入口，被 app 依赖复制 | ✅ |

### 2.1 manifest.json 标准格式

```json
{
  "asset_id": "app.novel",
  "asset_type": "app",
  "name": "小说助手",
  "version": "1.2.0",
  "location": "installed/app.novel/",
  "entry": "main.py",
  "description": "武侠小说生成 App",
  "dependencies": [
    "shared.utils:>=1.0.0"
  ],
  "owner": "wangchienbo",
  "owner_role": "admin",
  "tags": ["ai", "writing"],
  "metadata": {
    "app_shape": "generic",
    "required_skills": [],
    "required_modules": []
  }
}
```

### 2.2 版本号含义

格式：`major.minor.patch`

- **major** 变化：不兼容变更，需用户确认
- **minor** 变化：功能新增，向后兼容
- **patch** 变化：Bug 修复

---

## 三、标准接口定义

### 3.1 启动 Tool（MasterControl 调用）

每个资产要实现的标准启动接口：

```python
# Tool 名称：start_asset
{
    "name": "start_asset",
    "parameters": [
        {"name": "asset_id",  "type": "string",  "required": True},
        {"name": "version",   "type": "string",  "required": False},  # 不指定则用最新
    ],
    "returns": {"status": "running", "endpoint": "", "pid": 0}
}

# Tool 名称：stop_asset
{
    "name": "stop_asset",
    "parameters": [
        {"name": "asset_id",  "type": "string",  "required": True},
    ],
    "returns": {"status": "stopped"}
}

# Tool 名称：health_check_asset
{
    "name": "health_check_asset",
    "parameters": [
        {"name": "asset_id",  "type": "string",  "required": True},
    ],
    "returns": {"status": "ok|running|stopped|error", "uptime": "2h", "pid": 12345}
}
```

### 3.2 自注册接口（进程启动时调用）

```python
# 进程启动后调用
POST /api/v1/runtime/register
{
    "asset_id": "app.novel",
    "version": "1.2.0",
    "pid": 12345,
    "endpoint": "http://localhost:8001",
    "owner": "wangchienbo"
}

# 定期心跳（心跳间隔：30s）
POST /api/v1/runtime/heartbeat
{"asset_id": "app.novel", "pid": 12345}

# 进程退出时调用
POST /api/v1/runtime/unregister
{"asset_id": "app.novel"}
```

### 3.3 权限控制

| 操作 | 权限 |
|------|------|
| 写入自己信息（register/heartbeat/unregister） | 进程自身 token（pid 校验） |
| 读取所有资产信息 | 所有已认证用户 |
| 启动/停止 app | >= admin 角色 |
| 启动/停止 system | ❌ 禁止 |
| 升级 app 版本 | >= admin 角色 |
| 卸载 app | >= admin 角色 |
| 创建新 app | >= user 角色 |

---

## 四、完整生命周期

### 4.1 新建 App（MetaAppCreationOrchestrator 触发）

```
用户: "创建一个小说 App"
  → MetaAppOrchestrator 设计 + 生成 blueprint
  → 写入 source/app.novel/manifest.json  ← 新增 Step 4（之前已有）
  → AppManagementWorker 创建实例
  → 写入资产中心（asset_id=app.novel, version=0.1.0, location=...）  ← 新增
  → 注册到运行资源中心（status=running）  ← 新增
  → 完成
```

### 4.2 升级 App

```
用户: "升级小说 App"
  → AssetCenter.build(app.novel)      → build/app.novel/v1.2.0/
  → 写入资产中心（新 version=1.2.0）
  → MasterControl.start_asset(app.novel, version=1.2.0) → 启动新实例
  → 新实例自注册到运行资源中心
  → 旧实例继续跑（直到被用户停止，或心跳超时被清理）
```

### 4.3 回退 App

```
用户: "回退小说 App 到 v1.1.0"
  → 查询资产中心：v1.1.0 的 location
  → stop_asset(app.novel)  → 停止当前实例
  → start_asset(app.novel, version=v1.1.0)  → 启动旧版本实例
  → 旧版本实例自注册
```

### 4.4 卸载 App

```
用户: "卸载小说 App"
  → MasterControl.stop_asset(app.novel)
  → 进程自注销（运行资源中心）
  → AssetCenter.uninstall(app.novel)  → 删除 installed/app.novel/
  → 资产中心标记为 uninstalled（或直接删除条目）
```

---

## 五、已实现模块清单

### ✅ 已完成

| 模块 | 文件 | 说明 |
|------|------|------|
| MasterControl 入口 | `app/services/master_control.py` | 统一执行 + 权限 + 审计 + 建议 |
| 6 个 Workers | `app/services/workers/` | AppMgmt/User/Skill/Refinement/File/Suggestion |
| Package Manager | `app/services/package_manager.py` | 7 个 Tool（list/show/build/install/uninstall/rollback/search）|
| ToolRegistry caller_ids | `app/services/tool_registry.py` | 权限过滤 + master_execute Tool 注册 |
| SkillBlueprint owner_role | `app/models/skill_blueprint.py` | owner_role 字段 |
| AssetCenter 基础 | `app/services/asset_center.py` | build + install + rollback + uninstall |
| SystemCatalog | `app/services/system_catalog.py` | 资产自注册 + 可见性过滤 |
| MasterControl Handler | `app/services/light_brain_gateway.py` | _handle_master_execute + MasterControl 注入 |
| AppBlueprint source_path | `app/models/app_blueprint.py` | source_path 字段（仅记录，无实际路径）|
| MetaAppOrchestrator 改造 | `app/services/meta_app/orchestrator.py` | Step 4-7：source/ + build + install + system_catalog 注册 |
| Runtime 注入 | `app/bootstrap/runtime.py` | MasterControl + 6 Workers + AssetCenter + SystemCatalog |

### ❌ 待实现

| 模块 | 优先级 | 说明 |
|------|--------|------|
| RuntimeCenter 自注册接口 | P0 | 进程注册/心跳/注销 API |
| start_asset / stop_asset / health_check Tool | P0 | MasterControl 调用的标准启动接口 |
| AppBlueprint 升级流程 | P0 | 版本+1 → build → 写入资产中心 → 启动新实例 |
| App 进程隔离 | P1 | 每个 App 独立子进程，当前是单进程共享 |
| 运行资源中心（runtime_center.json） | P1 | 替代 system_catalog 的运行时状态 |
| Skill 包独立打包 | P2 | skill 作为独立包，可被多个 app 引用 |
| App 进程自注册代码（入口注入） | P2 | 每个 app 进程启动时注入 register 调用 |
| Shared 包多版本隔离 | P2 | 每个 app build 时锁定依赖版本，不覆盖共享包 |
| 权限细化：写自己信息 | P2 | 进程 register 只允许写自己 asset_id 的信息 |
| build 时依赖解析 | P2 | manifest.dependencies 递归解析并复制 |

---

## 六、与 Phase M 的关系

Phase M 实现的 `PackageManagerExecutor`（7 个 Tool）**保留但语义变化**：

| 原语义 | 新语义 |
|--------|--------|
| `package_build` | 打包到 `build/{asset_id}/{version}/`（完整包）|
| `package_install` | 写入资产中心 + 可选立即启动 |
| `package_uninstall` | 停止进程 + 删除 installed/ + 资产中心注销 |
| `package_list_installed` | 查资产中心已安装列表 |
| `package_search` | 查 Registry 可用包（本地 source/ + Registry HTTP）|
| `package_rollback` | 停止当前 + 启动指定版本 |
| `package_show` | 查看资产中心详情 |

---

## 七、数据流总图

```
用户请求
    ↓
Gateway（交互层）
    ↓ 判断需要系统级变更？
MasterControl.execute(operation, ...)
    ↓
AssetCenter / RuntimeCenter（资产中心 / 运行资源中心）
    ↓
start_asset Tool → 进程启动
    ↓
进程自注册（register → 运行资源中心）
    ↓
进程运行中（定期 heartbeat）
    ↓
进程退出 → unregister（运行资源中心）
```

---

## 八、实现顺序

```
Step 1: RuntimeCenter（运行资源中心）         ← 基础设施
Step 2: start_asset/stop_asset/health Tool    ← MasterControl 可调用
Step 3: App 进程启动时注入 register           ← 自注册链路
Step 4: App 升级流程（build → 资产中心 → 启动新实例） ← 核心链路
Step 5: App 卸载流程（stop → unregister → uninstall）← 核心链路
Step 6: 权限细化（进程只能写自己的信息）      ← 安全收口
Step 7: Skill/Shared 包支持                   ← 可选，待定
```

---

## 九、关键设计决策

1. **不走 installed/ 覆盖**：每个版本装到独立目录 `installed/{asset_id}/{version}/`，不覆盖旧版本
2. **进程自注册而非中心轮询**：进程主动注册，资产中心只记录状态，减少中心压力
3. **心跳检测发现崩溃**：30s 心跳，超时 90s 未到则标记为 crashed，由 MasterControl 清理
4. **system 包强约束**：system 包的 start/stop 操作在 MasterControl 层硬编码禁止
5. **权限分层**：进程 Token（写自己）< user（读）< admin（启动/停止）< root（系统变更）
