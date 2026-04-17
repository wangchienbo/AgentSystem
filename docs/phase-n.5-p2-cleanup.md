# Phase N.5：Phase N P2 收尾

## 剩余 P2 项
1. **权限细化：写自己信息** — RuntimeCenter.register 只允许写自己的 asset_id
2. **build 时依赖解析** — manifest.dependencies 递归解析并复制
3. **Shared 包多版本隔离** — 每个 app build 时锁定依赖版本
4. **Skill 包独立打包** — skill 作为独立包，可被多个 app 引用

---

## N5-01: RuntimeCenter 权限细化
### 目标
register 只能写自己的 asset_id 信息，不能覆盖别人的。
