# AgentSystem + Novel Studio 生产级优化 Tasklist

> 生成日期：2026-08-08
> 目标：把小说 app（novel_studio）从「能跑」优化到「好用、生产级」，同时整理整个 AgentSystem 项目。
> 原则：每项优化必须可验证（有验收标准）；不动摇已跑通的管线核心；优先修复影响交付的可靠性问题。

---

## 现状诊断（已核实的代码事实）

- **小说 app 规模**：约 11,530 行，核心分层清晰（API → Engine → Pipeline 多 step → Storage/Models）。
- **管线已跑通**：write_next_chapter 全流程（world_design→chapter_plan→scene_loop→world_evolve→narrative→setting_check→editorial_review→character_emerge→memory_update），第一章 5394 字 / 5 场景，deepseek-v4-flash 生成通过。
- **已知隐患**：
  1. `world_check` 被临时注释禁用（base.py + __init__.py 两处），skill 明确建议用确定性校验替代 LLM 误报。
  2. `task_manager.py` 任务纯内存存储，进程重启丢失；`cleanup_old_tasks` 无定时调度。
  3. `storage.py` 单文件 JSON 读写，多线程 save 无锁（角色并行行动时可能竞态）；每次 save 全量备份。
  4. `worker.py` 有 100+ 硬编码操作别名映射（`op_map`），违反零硬编码原则；含大量疑似废弃的演化操作。
  5. `api.py` 1637 行单文件，路由（小说/角色/世界/章节/演化/聊天/会话/导出）全部堆叠。
  6. 模型 key 通过启动命令 `export FANGZHOU_API_KEY=...` 硬编码注入，无 .env 加载。
  7. 根目录散落大量历史一次性脚本（batch_*.py / generate_*.py / plot_*.py / debug_trace.py 等）。
  8. 测试硬编码 novel_id + Chrome 绝对路径，脆弱不可迁移。
  9. 启动脚本多样（start.sh / start_server.sh / start_web_server.sh / setup_and_start.sh）不统一。
  10. LLM 调用层无统一重试/熔断/metrics（onkuku 偶发 504 只能靠 pipeline 内隐式重试）。

---

## 优化任务清单

### 阶段 0：基线冻结（P0，先做）
- [ ] **T0.1 提交基线**：当前第一章 5394 字已生成、管线全通，立即 git commit 冻结一个稳定点，便于后续回滚。
- [ ] **T0.2 记录环境**：把当前模型配置（config.yaml 三层结构）、API key 注入方式、启动命令写入 `docs/ENV.md`，避免优化过程中丢失可运行状态。

### 阶段 1：项目整理（P0）
- [ ] **T1.1 归档根目录脚本**：`batch_*.py`、`generate_*.py`、`plot_*.py`、`debug_trace.py`、`test_*.py`（一次性）移入 `scripts/archive/`；`tasklist_*.md` 移入 `docs/archive/`。让根目录只剩入口 + 配置 + 包目录。
- [ ] **T1.2 统一启动脚本**：合并 4 个 start 脚本为单一 `scripts/dev.sh`（含 .env 加载、健康检查、日志重定向），删除冗余。
- [ ] **T1.3 补全依赖锁定**：完善 `pyproject.toml`（补 playwright、pytest-asyncio 等实际依赖），或生成 `requirements.txt` 锁定版本。
- [ ] **T1.4 .env 化密钥**：新建 `.env.example`（含所有 provider key 占位），启动脚本 `source .env`，移除启动命令中的明文 `export FANGZHOU_API_KEY=...`。
- [ ] **T1.5 日志策略**：日志输出到 `logs/novel_{date}.log`（滚动），过滤外部扫描请求噪音，按 task_id 关联。

### 阶段 2：小说 app 可靠性（P0）
- [ ] **T2.1 修复 world_check 误报并重启用**：改为确定性校验——`last_updated_chapter >= 当前章 - 1` 且 `len(known_facts) >= 阈值` 程序化判断，不再依赖 LLM 主观判断。从 base.py 和 __init__.py 移除注释禁用。
- [ ] **T2.2 storage 并发安全**：`save_novel` 加进程级文件锁 / 串行写队列，避免角色并行行动时 JSON 写竞态；备份策略优化（仅当数据变化大时备份，或保留 N 份而非每次全量 copy）。
- [ ] **T2.3 任务持久化**：task_manager 状态落盘（`logs/tasks/` 或 data 下），进程重启后可从磁盘恢复/清理任务；定时调度 `cleanup_old_tasks`。
- [ ] **T2.4 LLM 调用兜底**：在 model_client 层加统一重试（指数退避）+ 超时 + 熔断 + 失败归因，替换 pipeline 各 step 各自为政的隐式处理。
- [ ] **T2.5 数据自愈增强**：`get_novel` 反序列化失败时，除 backup 恢复外，增加字段级校验与修复日志，避免静默丢数据。

### 阶段 3：可观测性（P1）
- [ ] **T3.1 结构化日志**：关键步骤输出 JSON 日志（含 task_id、step、耗时、模型），便于检索与告警。
- [ ] **T3.2 生成指标**：每次章节生成记录耗时、LLM 调用次数、token 消耗、每 step 耗时，存入任务 result，UI 可查。
- [ ] **T3.3 进度增强**：任务事件增加场景内角色级实时进度、已生成字数实时统计（scene_loop 内推进）。
- [ ] **T3.4 错误归因面板**：任务失败时定位到具体 step + 根因 + 提供「重试该 step / 全文重生成」按钮（API 支持）。

### 阶段 4：好用性（P1）
- [ ] **T4.1 拆分 api.py**：1637 行按资源拆分（novel / character / world / chapter / evolve / chat / session / export），各自 router，保持路由前缀兼容。
- [ ] **T4.2 重构 worker op_map**：移除 100+ 硬编码别名，改为从 LLM 工具 schema（JSON schema 定义的操作）驱动；删除废弃的演化操作，收敛 API 面。
- [ ] **T4.3 Web UI 增强**：章节质量评分展示（editorial_review 结果持久化）、续写/改写/重写交互、角色管理界面、世界设定可视化。
- [ ] **T4.4 角色对话完善**：补齐 character_chat 模板，支持与小说角色对话，接入现有 chat 端点。
- [ ] **T4.5 导出增强**：支持批量导出（全本 TXT / 目录结构 Markdown / EPUB 预研），一键下载。

### 阶段 5：测试与验证（P1）
- [ ] **T5.1 测试解耦**：E2E 测试不依赖硬编码 novel_id / Chrome 绝对路径，改为 fixture 动态创建 + 环境变量注入浏览器路径。
- [ ] **T5.2 单元测试补齐**：storage 并发、task_manager 持久化、world_check 确定性校验、model_client 重试/熔断、worker 操作路由。
- [ ] **T5.3 E2E 回归**：Playwright 全流程（创建小说 → 生成章节 → 阅读 → 导出），断言无 console error。
- [ ] **T5.4 性能基线**：记录第一章/长章节生成的耗时与 token 消耗基准，作为后续优化的对照。

### 阶段 6：架构演进（P2，可选）
- [ ] **T6.1 重生成参数化**：`max_regenerations` 从硬编码 2 改为配置项，支持按模板覆盖。
- [ ] **T6.2 多模型 failover**：按 step 配置主备模型，主模型失败自动切换备用。
- [ ] **T6.3 存储演进评估**：章节增多后全量 JSON 读写性能评估；如需则引入 SQLite 索引或增量章节文件。

---

## 建议执行顺序
1. **阶段 0** → 立即冻结（保证可回滚）。
2. **阶段 1** 项目整理 + **阶段 2** 可靠性（P0，收益最大、风险可控，先做）。
3. **阶段 3/4** 可观测性 + 好用性（P1）。
4. **阶段 5** 测试兜底贯穿始终。
5. **阶段 6** 演进（P2，按需）。

每一项完成都必须：验证生效（看日志预期输出 + 数据实际变化 + 测试通过），不能只看「代码写完」。
