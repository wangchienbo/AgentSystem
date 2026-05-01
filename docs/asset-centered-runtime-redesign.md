# Asset-Centered Runtime Redesign

## v1 Schema 固定清单

### 1. Asset Descriptor v1
必填字段:
- `descriptor_version: int`
- `asset_id: str`
- `kind: str`
- `summary: str`
- `detail: str`

可选字段:
- `methods: list[AssetMethodSpec]`
- `model_requirement: AssetModelRequirement`
- `metadata: dict`

约束:
- descriptor 必须 versioned
- `summary/detail/methods/model_requirement` 必须同源生成
- method names 必须唯一
- additive extension 仅允许新增 optional fields，不允许重写必填语义

### 2. Model Requirement v1
必填字段:
- 无

可选字段:
- `preferred_model: str | null`
- `fallback_model: str | null`
- `minimum_requirements: dict`

约束:
- fallback 不得跨越最低语义能力门槛
- 当 fallback 不满足 `minimum_requirements` 时必须显式失败

### 3. Interaction Decision Envelope v1
必填字段:
- `decision: "text" | "need_asset_detail_id" | "invoke"`

条件必填字段:
- 当 `decision=text` 时，`text` 必填
- 当 `decision=need_asset_detail_id` 时，`need_asset_detail_id` 必填
- 当 `decision=invoke` 时，`invoke` 必填

可选字段:
- `metadata: dict`

三分支语义:
- `text`: 直接返回用户可读文本
- `need_asset_detail_id`: 请求装载某个资产 detail
- `invoke`: 请求对某个资产方法执行调用

## Descriptor Version / Additive Extension Rules
- v1 作为最小稳定协议
- 后续字段扩展必须优先 additive
- 不允许依赖 chat 记忆补解释 schema
- 版本升级前必须保留调试/观测视图兼容说明
