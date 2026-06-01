# 章节写作技能

## 核心能力
- **写新章节**：基于当前小说数据（大纲/前一章）生成新章节
- **修改章节**：更新已有章节的标题/内容
- **续写章节**：从章节中断处继续写作
- **章节结构**：规划章节的起承转合

## 操作方式
- 写新章节：调用 `call_asset_method(asset:novel_studio:v1, write_chapter, {"novel_id": "xxx"})`，引擎会自动找到下一个未写章节
- 更新章节：调用 `call_asset_method(asset:novel_studio:v1, update_chapter, {"novel_id": "xxx", "chapter_id": "...", "title": "...", "content": "..."})`
- 删除章节：调用 `call_asset_method(asset:novel_studio:v1, delete_chapter, {"novel_id": "xxx", "chapter_number": N})`

## 写作原则
1. **开场要抓人**：每章开头应有钩子（hook）吸引读者
2. **场景要有目的**：每个场景服务于情节推进、角色塑造或主题表达
3. **节奏要张弛有度**：紧张场景后安排舒缓段落
4. **对话推动情节**：角色对话应包含信息、冲突和角色性格展现
5. **章节结尾要有悬念**：用悬念（cliffhanger）促使读者读下一章
6. **展示不告知**：通过动作、对话、环境展示，避免直接说明
