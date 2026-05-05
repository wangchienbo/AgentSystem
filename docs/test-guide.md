# AgentSystem 测试指导文档

> 本文档定义 AgentSystem 的完整测试策略、场景用例和质量标准。
> 维护者：wangchienbo / AI 协作者
> 更新：2026-04-23

---

## 一、测试架构总览

```
┌─────────────────────────────────────────────────────────┐
│  测试对象：AgentSystem 龙虾系统                           │
│  入口：HTTP 80 端口 (http_test_server.py)                  │
│  核心：LightBrain Gateway → ToolCallingEngine → LLM       │
└─────────────────────────────────────────────────────────┘
         ↑                          ↑
    交互层/前端              ModelRouter（读取 config.yaml）
```

### 测试分层

| 层级 | 范围 | 测试方式 |
|------|------|----------|
| **L0 精确匹配** | 你好/帮助/系统状态 | 无 LLM 调用，直接 handler → 回复 |
| **L1 LLM 透传** | "你能做什么"/自由聊天 | ToolCallingEngine → LLM → 返回自然语言 |
| **L2 工具调用** | 创建 App/查看资产 | LLM 选择工具 → 执行 → LLM 生成回复 |
| **L3 多轮链路** | 连续追问/App 创建流程 | 状态保持 + 多轮 LLM 对话 |
| **L4 E2E 全链路** | 用户从登录到完成复杂任务 | 完整流程验证 |

---

## 二、质量标准

### 2.1 合格标准

- ✅ **非保底**：`我还不会处理这个指令。试试说...` 只能出现在以下情况：
  - LLM 服务完全不可用（网络超时）
  - 模型返回空内容
- ✅ **自然语言**：回复必须是 LLM 动态生成的人类可读文字，不是预制模板
- ✅ **工具调用**：创建 App 等操作必须走 `list_files`/`write_file` 等真实工具，**不能仅返回「好的我来创建」
- ✅ **多轮续接**：同一 session 内的连续对话应保持上下文

### 2.2 不合格示例

```python
❌ "我明白了。有什么我可以帮你的吗？"  （仅当用户真的在说「谢谢」时合理）
❌ "我还不会处理这个指令。试试说创建 App"  （任何 LLM 可处理的意图都不该出现）
❌ "好的，我来帮你创建 App。"             （必须真实执行，不能仅返回确认）
❌ "系统正常。"                           （太简略，缺乏有用信息）
```

---

## 三、分层测试用例

### L0 精确匹配（零 LLM 成本）

| ID | 输入 | 期望 | 验证点 |
|----|------|------|--------|
| L0-01 | `你好` | 含「你好」+ 系统能力描述 | 不是保底 |
| L0-02 | `帮助` | 含「帮助」+ 指令列表 | 不是保底 |
| L0-03 | `系统状态` | 含状态/运行/App | 不是保底 |

### L1 LLM 透传（验证 LLM 正确接入）

| ID | 输入 | 期望 | 验证点 |
|----|------|------|--------|
| L1-01 | `你能做什么` | 自然语言能力描述，含「App/管理/资产」等 | 动态生成，非预制 |
| L1-02 | `介绍一下自己` | 含 AgentSystem/龙虾/能力介绍 | 动态生成 |
| L1-03 | `给我讲个笑话` | 笑话内容，非「我不理解」 | 动态生成 |
| L1-04 | `今天天气` | 天气相关内容 | 动态生成 |

### L2 工具调用（验证 LLM → 工具链）

> **关键**：日志中应出现 `list_files`/`search_files`/`write_file` 等工具名

| ID | 输入 | 期望 | 验证点 |
|----|------|------|--------|
| L2-01 | `读出我的安装目录结构` | 日志有 `list_files` 调用 + 结构化输出 | 工具真实执行 |
| L2-02 | `创建一个小说 App` | 日志有文件写入 + App 注册成功 | 链路完整 |
| L2-03 | `查看所有资产` | 日志有 `list_assets` 调用 + 资产列表 | 工具调用 |
| L2-04 | `搜索 AgentSystem 里的日志相关代码` | 日志有 `search_files` 调用 + 搜索结果 | 多工具协作 |
| L2-05 | `给项目添加一个健康检查 Skill` | 日志有 `write_file` + `register_skill` | 复杂多工具链 |

### L3 多轮链路（验证状态保持）

| ID | 流程 | 期望 | 验证点 |
|----|------|------|--------|
| L3-01 | 「创建一个App」→「叫天气App」→「再加个城市选择功能」 | 同一 session，最终 App 包含城市选择 | 上下文保持 |
| L3-02 | 「我叫张三」→「我叫小明」→「我叫什么」 | 最后回复含「小明」 | 记忆更新 |
| L3-03 | 「读出目录」→「哪些不合理」→「改掉它们」 | 链路不断，第三轮有修改操作 | 多轮续接 |

### L4 E2E 完整场景（从用户角度看）

| ID | 场景 | 步骤 | 验收标准 |
|----|------|------|----------|
| L4-01 | **用户登录+自由对话** | 1. 访问 http://101.34.58.220 2. 输入任意账号密码登录 3. 说「你好」 | 页面加载正常，登录后跳转，显示助手回复 |
| L4-02 | **创建 App → 查看 → 启动** | 1. 说「帮我建一个日报 App」 2. 说「看看我的 App」 3. 说「启动日报 App」 | 三步全部返回自然语言，第三步确认启动成功 |
| L4-03 | **深度探索 → 自我改造** | 1. 「读出项目结构」 2. 「哪些地方不合理」 3. 「改掉第一个问题」 | 工具调用日志完整，第三步有实际文件修改 |
| L4-04 | **模糊需求 → 精确澄清** | 1. 「弄个监控」 2. (系统追问) 3. 「服务器 + CPU 监控」 | 第二轮追问内容合理，第三轮 App 创建完成 |
| L4-05 | **并发会话隔离** | 两个不同 session 同时说不同内容 | 互不干扰，各自独立上下文 |

---

## 四、日志分析方法

### 4.1 查看 LLM 调用日志

```bash
# 查看最近的 LLM 调用结果
tail -f /tmp/agent_test.log | grep "ToolCallingEngine result"
```

正常输出示例：
```
ToolCallingEngine result: final_text=我可以帮你做这些事：...,
  tool_calls=none                    ← LLM 直接回复，无工具调用
ToolCallingEngine result: final_text=[Reached max turns (8)],
  tool_calls=['list_files', ...]     ← LLM 调用了工具（需检查是否全部执行）
```

### 4.2 查看工具执行日志

```bash
# 查看工具调用链
tail -f /tmp/agent_test.log | grep "agentsystem:Command"
```

正常输出示例：
```
agentsystem:Command: list_files, Status: success, Duration: 20456ms, Tokens: 4
agentsystem:Command: direct_response, Status: success, Duration: 20880ms, Tokens: 140
```

### 4.3 判断是否走 LLM

```
INFO:httpx:HTTP Request: POST https://crs.ruinique.com/v1/chat/completions  ← 有这条 = 走了 LLM
直接返回（无这条）= 精确匹配 handler
```

---

## 五、测试执行方法

### 5.1 快速冒烟测试

```bash
cd <repo-root>
python3 e2e_test.py
```

### 5.2 手动测试命令

```bash
# 登录
curl -L -c /tmp/c.txt -X POST http://localhost:80/login \
  -d 'username=test&password=test'

# 测试各层级
curl -b /tmp/c.txt -X POST http://localhost:80/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"你好","session_id":"s1"}'

curl -b /tmp/c.txt -X POST http://localhost:80/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"你能做什么","session_id":"s1"}'

curl -b /tmp/c.txt -X POST http://localhost:80/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"读出项目目录结构","session_id":"s1"}'
```

### 5.3 查看日志

```bash
tail -f /tmp/agent_test.log
```

---

## 六、已知问题与状态

| # | 问题 | 状态 | 备注 |
|---|------|------|------|
| 1 | `direct_response` 返回「我明白了。有什么我可以帮你的吗？」 | ✅ 已修复（max_turns 8） | 2026-04-23 |
| 2 | http_test_server.py 错误读取 `model_providers.OpenAI` | ✅ 已修复 | 2026-04-23 |
| 3 | `logger` 未 import 导致 NameError | ✅ 已修复 | 2026-04-23 |
| 4 | `list_files` 工具未注册到 ToolCallingEngine | 🔄 需验证 | 2026-04-23 |

---

## 七、CI/自动化测试要求

每次推送代码前，必须运行：

```bash
cd <repo-root>
python3 e2e_test.py
```

测试通过条件：全部用例返回非保底回复（`is_fallback() == False`）。

---

## 八、测试数据

- 测试用户：`test` / `testpass`
- Session 前缀：`session_{uuid}`
- LLM 模型：`gpt-5.4` via `https://crs.ruinique.com`
- 测试配置文件：`~/.config/agentsystem/config.yaml`
