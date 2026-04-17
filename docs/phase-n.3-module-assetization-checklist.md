# Phase N.3：模块资产化与系统串联缺口清单

> 生成时间：2026-04-17
> 目标：把 AgentSystem 从“代码已解耦、链路部分接通”推进到“模块可安装、可升级、可发现、可调用、可端到端验收”的完成状态。
> 执行原则：按依赖顺序推进，前面的改造不阻塞后面的扩展，优先收口静态资产真源，再收口运行链路。

---

## 一、最终目标定义

完成后系统需要满足：

1. **每个可运行模块都有清晰的静态资产描述**
2. **每个模块可被安装 / 升级 / 卸载 / 回退**
3. **运行时可注册 / 心跳 / 服务发现 / 健康检查**
4. **模块之间可通过统一调用面互相发现、互相调用**
5. **Gateway → MasterControl → Worker / Asset / RuntimeCenter 全链路收口**
6. **source/ → build/ → installed/ 成为唯一正式安装链路**
7. **最终通过真实端到端场景验收，而不是只靠单测**

---

## 二、现状结论（审计结果）

### 已有
- 代码物理解耦已完成第一轮
- `AssetCenter` 已具备 `discover/build/install/rollback`
- `RuntimeCenter` 已具备 `register/heartbeat/unregister/cleanup`
- `SystemCatalog` / `ToolRegistry` / `MasterControl` 已接入运行时
- `start_asset/stop_asset/health_check_asset` 已有第一版
- `MetaAppCreationOrchestrator` 已能写入 `source/{asset_id}/manifest.json`

### 缺口
- `source/ build/ installed/` 目录当前基本为空，真实资产库存未迁入
- 现有 generated skill manifest 缺少 `asset_id/asset_type/entry/owner/owner_role`
- `AppInstaller` 仍未统一走 `AssetCenter.build + install`
- `caller_ids` 有机制但未真正按模块配置
- `RuntimeCenter` 只接了一部分链路，升级/卸载未完全接入
- 进程仍不是 subprocess 真托管
- 服务发现内容不完整，app → skill / tool 的可见性图未收口

---

## 三、执行清单（按顺序）

# P0：统一静态资产真源

### N3-01 统一 manifest 标准（必须字段）
**目标**：定义系统唯一有效的静态资产描述格式。

必须字段：
- `asset_id`
- `asset_type`
- `name`
- `version`
- `entry`
- `owner`
- `owner_role`
- `dependencies`
- `source_path`
- `description`
- `metadata`

**完成标准**：
- 文档写清楚
- 代码里有统一校验入口
- 所有后续资产都按这个格式生成

---

### N3-02 清查并补齐现有 generated skill manifest
**目标**：把当前 `data/namespaces/generated_executable_skills/...` 下不完整 manifest 修成合格资产描述。

**要补**：
- `asset_id`
- `asset_type=skill`
- `entry`
- `owner`
- `owner_role`
- `dependencies`
- `metadata.skill_kind`

**完成标准**：
- 所有现存 manifest 都能被 `AssetCenter.discover()` 正常识别
- 无关键字段缺失

---

### N3-03 补 source/ 正式资产库存
**目标**：把当前“运行着但未入库”的核心模块，至少补一批正式 source 资产。

优先资产：
- `system.master`
- `system.gateway`
- `app.workspace.assistant`
- 可执行 generated skill 样例资产

**完成标准**：
- `source/` 不再为空
- 至少有一批真实资产能走 build/install

---

# P1：收口安装升级主链路

### N3-04 AppInstaller 接入 AssetCenter
**目标**：所有 app 安装统一走正式资产链路。

改造方向：
- `AppInstaller.install_app()` 不再只走 runtime registry
- 要先经过：
  - `source`
  - `build`
  - `install`
  - `installed`
- 再注册 lifecycle / runtime_host / app_registry

**完成标准**：
- app 安装与升级不再绕过 `AssetCenter`

---

### N3-05 升级/回退/卸载接 RuntimeCenter
**目标**：运行态和静态资产信息一致。

需要补：
- `upgrade_app`
- `rollback_app`
- `uninstall_app`
- 同步更新：
  - `AssetCenter`
  - `RuntimeCenter`
  - `SystemCatalog`

**完成标准**：
- 升级后 runtime 中版本变化正确
- 卸载后 runtime/catalog/install 状态一致

---

# P2：收口服务发现与调用边界

### N3-06 真正配置 caller_ids
**目标**：不同模块只能看到应该看到的工具。

优先规则：
- `system.master` 可见全部
- `system.gateway` 仅可见主控与查询相关工具
- `app.*` 只可见授权工具和绑定 skill
- `skill.*` 不可越权看到系统工具

**完成标准**：
- `get_tools_for_caller()` 对不同 caller 返回不同结果
- 不再出现 `app.demo` 看见全部 30 个工具的情况

---

### N3-07 收口服务发现模型
**目标**：静态目录 + 运行目录 + 可见性规则统一。

要统一的对象：
- `SystemCatalog`
- `RuntimeCenter`
- `AssetRegistry`
- `query_visible_assets`
- `query_asset_detail`

**完成标准**：
- app 能发现自己绑定的 skill / tool
- system 能发现全部
- user 只能发现自己的和公开的

---

# P3：收口进程模型

### N3-08 start/stop 改为真实 subprocess 托管
**目标**：真正做到“一个进程一个运行体”。

需要补：
- `subprocess.Popen`
- pid 托管
- stop 时真实 kill
- heartbeat 来自真实运行进程
- endpoint 探活

**完成标准**：
- `RuntimeCenter.pid` 不再是占位值
- `health_check_asset` 具备真实意义

---

# P4：系统全链路验收

### N3-09 端到端场景验收
**目标**：不用大规模 pytest，直接走真实主链路场景。

必测场景：
1. 创建 App
2. 安装 App
3. 启动 App
4. 查询运行状态
5. 停止 App
6. 升级 App
7. 回退 App
8. 卸载 App
9. 服务发现
10. tool 调用权限隔离

**完成标准**：
- 每个场景都有真实执行记录
- 结果写入文档

---

## 四、推荐执行顺序

### Step 1
- N3-01 manifest 标准
- N3-02 补 generated skill manifest
- N3-03 补 source 资产库存

### Step 2
- N3-04 AppInstaller 接 AssetCenter
- N3-05 升级/回退/卸载接 RuntimeCenter

### Step 3
- N3-06 caller_ids 真配置
- N3-07 服务发现统一

### Step 4
- N3-08 subprocess 真托管
- N3-09 端到端验收

---

## 五、当前执行状态

- [ ] N3-01 统一 manifest 标准
- [ ] N3-02 补 generated skill manifest
- [ ] N3-03 补 source 资产库存
- [ ] N3-04 AppInstaller 接入 AssetCenter
- [ ] N3-05 升级/回退/卸载接 RuntimeCenter
- [x] N3-06 caller_ids 真配置
- [x] N3-07 服务发现统一
- [x] N3-08 subprocess 真托管
- [ ] N3-09 端到端验收
