# 世界观构建技能

## 核心能力
- **创建/更新世界观**：设定世界名称、概述、规则体系
- **世界规则**：物理规则、魔法体系、科技水平、社会结构
- **场景构建**：地理位置、气候、人文特色
- **文化体系**：历史、宗教、政治、经济

## 操作方式
- 保存世界观：`call_asset_method(asset:novel_studio:v1, save_world, {"novel_id": "xxx", "name": "...", "overview": "...", "rules": [...]})`
- 添加场景：`call_asset_method(asset:novel_studio:v1, add_scene, {"novel_id": "xxx", "name": "...", "location": "...", "description": "..."})`
- 更新场景：`call_asset_method(asset:novel_studio:v1, update_scene, ...)`
- 删除场景：`call_asset_method(asset:novel_studio:v1, delete_scene, ...)`

## 设计原则
1. **一致性**：世界观规则需前后一致，不能随意破坏
2. **有机展示**：通过角色视角自然展现世界，避免信息 dump
3. **规则有限度**：规则越少越有力，太多规则会限制叙事灵活性
4. **冲突源于设定**：世界观本身应蕴含冲突——资源稀缺、阶级矛盾、价值观对立
5. **服务于故事**：世界观是为故事服务的，不要为了构建而构建
