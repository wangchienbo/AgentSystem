# Phase N.5：Phase N P2 收尾

## 剩余 P2 项
1. **权限细化：写自己信息** — RuntimeCenter.register 只允许写自己的 asset_id
2. **build 时依赖解析** — manifest.dependencies 递归解析并复制
3. **Shared 包多版本隔离** — 每个 app build 时锁定依赖版本
4. **Skill 包独立打包** — skill 作为独立包，可被多个 app 引用

---

## N5-01: RuntimeCenter 权限细化
### 状态
✅ 已在 runtime_center.py 的 register 方法中加入 caller_id 校验。
非 system.* 调用者只能注册自己 owned 的 asset_id。

## N5-02: build 时依赖解析
### 状态
✅ 已在 AssetCenter.build() 后调用 _resolve_and_copy_dependencies()。
依赖递归解析并复制到 build_output/deps/{dep_id}/。

## N5-03: Shared 包多版本隔离
### 状态
✅ 每个 build 产出独立 build/{asset_id}/{build_hash}/ 目录。
不同版本的依赖自然隔离，不互相覆盖。

## N5-04: Skill 包独立打包
### 状态
✅ generated_executable_skills 的 manifest 已实现独立 asset_id。
skill 作为独立 asset_type="skill" 包，可被多个 app 引用。
