     1|# 世界观构建技能
     2|
     3|## 核心能力
     4|- **创建/更新世界观**：设定世界名称、概述、规则体系
     5|- **世界规则**：物理规则、魔法体系、科技水平、社会结构
     6|- **场景构建**：地理位置、气候、人文特色
     7|- **文化体系**：历史、宗教、政治、经济
     8|
     9|## 操作方式
    10|- 保存世界观：`call_asset_method(asset_id="asset:novel_studio:v1", method="save_world", params={"novel_id": "xxx", "name": "...", "overview": "...", "rules": [...]})`
    11|- 添加场景：`call_asset_method(asset_id="asset:novel_studio:v1", method="add_scene", params={"novel_id": "xxx", "name": "...", "location": "...", "description": "..."})`
    12|- 更新场景：`call_asset_method(asset_id="asset:novel_studio:v1", method="update_scene", params={...})`
    13|- 删除场景：`call_asset_method(asset_id="asset:novel_studio:v1", method="delete_scene", params={...})`
    14|
    15|## 设计原则
    16|1. **一致性**：世界观规则需前后一致，不能随意破坏
    17|2. **有机展示**：通过角色视角自然展现世界，避免信息 dump
    18|3. **规则有限度**：规则越少越有力，太多规则会限制叙事灵活性
    19|4. **冲突源于设定**：世界观本身应蕴含冲突——资源稀缺、阶级矛盾、价值观对立
    20|5. **服务于故事**：世界观是为故事服务的，不要为了构建而构建
    21|