# AgentSystem 配置指南

## 快速启动

```bash
cd /root/projects/AgentSystem
source .venv/bin/activate
export OPENAI_API_KEY="你的API密钥"
agentsystem start --port 8765
```

打开浏览器访问 `http://<服务器IP>:8765`，登录后即可使用。

## 一键启动脚本

把下面这个保存为 `start.sh`，以后一声令下就能跑：

```bash
#!/bin/bash
cd /root/projects/AgentSystem
source .venv/bin/activate
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
exec python -m app.cli start --port 8765
```

如果 API key 已设好，直接运行即可。

## 配置文件位置

| 位置 | 用途 |
|------|------|
| `~/.config/agentsystem/config.yaml` | 主配置文件（默认） |
| `~/.local/share/agentsystem/config/config.yaml` | 运行时配置文件（从默认迁移而来） |
| `$AGENTSYSTEM_HOME/config.yaml` | 环境变量指定路径，覆盖默认位置 |

配置文件也可以不写——全部用环境变量：

```bash
export OPENAI_API_KEY=your-key
export OPENAI_BASE_URL=https://crs.ruinique.com/v1
export OPENAI_MODEL=gpt-5.4
agentsystem start
```

## 配置文件格式

```yaml
# ~/.config/agentsystem/config.yaml

model:
  default: "gpt-5.4"
  provider: OpenAICompatible
  base_url: https://crs.ruinique.com/v1
  api_key_env: OPENAI_API_KEY
  api_key: your-key-here             # 优先于环境变量
  timeout_seconds: 30.0

models:
  gpt-5.4:
    model: gpt-5.4
    base_url: https://crs.ruinique.com/v1
    api_key_env: OPENAI_API_KEY
  deepseek:
    model: deepseek-chat
    base_url: https://api.deepseek.com/v1
    api_key_env: DEEPSEEK_API_KEY

routing:
  default: gpt-5.4
  callers:
    architect: gpt-5.4
    supervisor: gpt-5.4
    builder: gpt-5.4

skills:
  default_model: gpt-5.4
```

## 服务命令

```bash
agentsystem start                  # 启动（默认 0.0.0.0:80）
agentsystem start --port 8765      # 指定端口
agentsystem status                 # 查看运行状态
agentsystem stop                   # 停止
agentsystem restart                # 重启
agentsystem doctor                 # 健康诊断
```

## 用户接口

服务启动后：

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /` | 页面 | 登录页面 |
| `POST /api/chat` | JSON | 发送聊天消息 |
| `POST /api/action` | JSON | 按钮/工具回调 |
| `GET /api/status` | 无参 | 健康检查 |

**`POST /api/chat` 请求格式：**

```json
{
  "message": "帮我看看当前服务器状态",
  "session_id": "会话ID（可选）"
}
```

**响应格式：**

```json
{
  "success": true,
  "data": "...",
  "actions": [],
  "session_id": "..."
}
```

## 环境变量速查

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENAI_API_KEY` | LLM API 密钥 | `sk-xxx` |
| `OPENAI_BASE_URL` | LLM 接口地址 | `https://crs.ruinique.com/v1` |
| `OPENAI_MODEL` | 默认模型名 | `gpt-5.4` |
| `AGENTSYSTEM_HOME` | 运行时数据目录（可选） | `~/.local/share/agentsystem` |

## 后端 API 探活

```bash
curl http://localhost:8765/api/status
# 返回: {"status":"ok","active_sessions":0,...}
```

## 常见问题

**Q: 启动报错 `Missing OPENAI_API_KEY`**
→ 没设 API key。export 或者在配置文件里填 `api_key`。

**Q: 启动报错 `Configuration file not found`**
→ 缺少 `~/.config/agentsystem/config.yaml`。用上面的示例模板创建一个。

**Q: `/api/chat` 返回 LLM 错误**
→ 检查 API key 和 base_url 是否正确，以及模型名是否在 endpoint 上可用。
