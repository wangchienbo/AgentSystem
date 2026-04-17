# Asset Manifest 标准（Phase N.3）

> 状态：生效中的统一静态资产规范

## 必填字段

```json
{
  "asset_id": "system.master",
  "asset_type": "system",
  "name": "Master Control",
  "version": "1.0.0",
  "entry": "main.py",
  "owner": "system",
  "owner_role": "system",
  "dependencies": [],
  "source_path": "source/system.master",
  "description": "系统主控进程",
  "metadata": {}
}
```

### 字段说明
- `asset_id`：全局唯一 ID，建议前缀：`system.` / `app.` / `skill.` / `shared.`
- `asset_type`：`system | app | skill | shared`
- `name`：人类可读名称
- `version`：语义化版本号
- `entry`：启动入口文件或处理入口
- `owner`：资产归属者
- `owner_role`：`system | root | admin | user`
- `dependencies`：依赖资产列表
- `source_path`：源码路径
- `description`：用途说明
- `metadata`：扩展静态元信息

## 推荐 metadata

### system/app
```json
{
  "interfaces": [],
  "service_discovery": true,
  "runtime_mode": "service",
  "health_check": "http"
}
```

### skill
```json
{
  "skill_kind": "generated_executable",
  "generated": true,
  "call_protocol": "callable"
}
```

## 校验原则
- 缺少任何必填字段，不得进入正式安装链路
- `asset_id + version` 应唯一标识一个可安装版本
- `source_path` 必须能定位到实际目录
