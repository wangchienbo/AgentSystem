# Phase H+ 风险护栏设计文档

> **创建时间**: 2026-04-22  
> **目标**: 为 AgentSystem 主路径添加风险护栏，防止系统滥用、失控或产生不可预料的副作用

## 背景

Phase H 已完成主路径闭环，支持上下文注入、动态决策和自动化执行。Phase H+ 需要为系统添加风险护栏，确保：
- 不会因无限循环或过度调用导致资源浪费
- 不会因权限问题导致越权操作
- 不会因异常导致系统崩溃
- 所有操作可追溯、可审计

## 风险分类与护栏设计

### 1. Query 上限（Rate Limiting）

**风险**: 单次会话或单用户短时间内发起过多查询，导致系统负载过高或 LLM 费用失控

**设计**:
- 单会话并发查询上限：`MAX_CONCURRENT_QUERIES_PER_SESSION = 5`
- 单用户查询速率：`MAX_QUERIES_PER_USER_PER_MINUTE = 30`
- 单会话查询速率：`MAX_QUERIES_PER_SESSION_PER_MINUTE = 20`
- 超出上限后行为：拒绝新请求，返回 `429 Too Many Requests` 错误

**实现位置**:
- `app/services/light_brain_gateway.py` - 查询入口限流
- `app/services/rate_limiter.py` (新建) - 通用限流器

**配置项**:
```python
# config/rate_limits.py
RATE_LIMITS = {
    "max_concurrent_queries_per_session": 5,
    "max_queries_per_user_per_minute": 30,
    "max_queries_per_session_per_minute": 20,
    "max_tool_calls_per_command": 10,
}
```

### 2. Tool Loop 上限（Tool Call Limit）

**风险**: 单个命令触发过多 tool 调用，导致无限循环或资源浪费

**设计**:
- 单命令最大 tool 调用次数：`MAX_TOOL_CALLS_PER_COMMAND = 10`
- 单会话累计 tool 调用次数：`MAX_TOOL_CALLS_PER_SESSION = 100`
- 超出上限后行为：中断执行，返回错误提示

**实现位置**:
- `app/services/tool_calling_engine.py` - 统计并限制 tool 调用
- `app/models/command.py` - 增加 `tool_call_count` 字段

**错误处理**:
```python
class ToolCallLimitExceeded(Exception):
    def __init__(self, limit: int, current: int):
        self.limit = limit
        self.current = current
        super().__init__(f"Tool call limit exceeded: {current}/{limit}")
```

### 3. Budget 控制（成本预算）

**风险**: LLM 调用、API 调用等产生不可控的费用

**设计**:
- 单会话 Token 预算：`TOKEN_BUDGET_PER_SESSION = 100000`
- 单用户日预算：`TOKEN_BUDGET_PER_USER_PER_DAY = 500000`
- 单次命令预算：`TOKEN_BUDGET_PER_COMMAND = 20000`
- 预算使用量追踪：每次 LLM 调用后更新预算使用量
- 预算耗尽后行为：拒绝新请求，提示用户预算不足

**实现位置**:
- `app/services/budget_tracker.py` (新建) - 预算追踪器
- `app/services/llm_client.py` - 调用前后检查预算

**配置项**:
```python
# config/budgets.py
BUDGETS = {
    "token_budget_per_session": 100000,
    "token_budget_per_user_per_day": 500000,
    "token_budget_per_command": 20000,
    "api_cost_per_1k_tokens": 0.002,  # USD
}
```

### 4. Observability（可观测性）

**风险**: 系统出现问题时无法快速定位原因

**设计**:
- 所有命令执行记录日志（包含输入、输出、耗时、错误信息）
- 关键路径打点（命令接收、工具调用、结果返回）
- 错误分类统计（权限错误、超时错误、LLM 错误等）
- 指标暴露（Prometheus 格式或简单 JSON 导出）

**实现位置**:
- `app/services/observability.py` (新建) - 可观测性模块
- `app/middleware/logging_middleware.py` - 日志中间件

**日志格式**:
```json
{
  "timestamp": "2026-04-22T04:00:00Z",
  "session_id": "sess_123",
  "user_id": "user_456",
  "command": "start_app",
  "target_app": "小说 App",
  "status": "success",
  "duration_ms": 150,
  "tool_calls": 2,
  "tokens_used": 1200,
  "error": null
}
```

### 5. Contract Lint（契约校验）

**风险**: 模块间接口契约不一致导致运行时错误

**设计**:
- 定义核心接口契约（App 生命周期、工具调用、会话管理等）
- 在关键路径前进行契约校验（开发/测试环境强制，生产环境可选）
- 契约违反时记录警告或抛出异常

**实现位置**:
- `app/utils/contract_lint.py` (新建) - 契约校验工具
- `tests/contract/` - 契约测试

**契约示例**:
```python
# app/contracts/lifecycle.py
from typing import Protocol

class LifecycleContract(Protocol):
    async def handle_start_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        """启动 App 的标准接口"""
        ...
    
    async def handle_stop_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        """停止 App 的标准接口"""
        ...
```

## 实现优先级

### P0（必须实现）
1. ✅ Tool Loop 上限 - 防止无限循环
2. ✅ Query 上限 - 防止资源滥用
3. ✅ Observability 基础日志 - 确保问题可追溯

### P1（应该实现）
4. Contract Lint 基础校验 - 确保接口一致性
5. Budget 基础追踪 - 了解成本分布

### P2（可选实现）
6. Budget 硬限制 - 成本严格控制
7. 高级可观测性（指标导出、告警）

## 实现计划

### 阶段 1: 基础护栏（当前迭代）
- [ ] 创建 `app/services/rate_limiter.py` - 限流器
- [ ] 创建 `app/services/budget_tracker.py` - 预算追踪
- [ ] 修改 `app/services/tool_calling_engine.py` - 添加 tool 调用计数
- [ ] 创建 `app/utils/observability.py` - 基础日志和指标
- [ ] 创建 `app/utils/contract_lint.py` - 契约校验工具

### 阶段 2: 集成与测试
- [ ] 在 `LightBrainGateway` 中集成限流器
- [ ] 在 `ToolCallingEngine` 中集成 tool 计数
- [ ] 在 `LLMClient` 中集成预算追踪
- [ ] 创建测试用例验证护栏生效

### 阶段 3: 配置与调优
- [ ] 创建 `config/rate_limits.py` - 限流配置
- [ ] 创建 `config/budgets.py` - 预算配置
- [ ] 根据实际使用情况调整阈值

## 测试用例

### Rate Limiter 测试
```python
def test_rate_limiter_allows_within_limit():
    limiter = RateLimiter(max_per_minute=20)
    assert limiter.is_allowed("session_1")
    assert limiter.is_allowed("session_1")

def test_rate_limiter_blocks_over_limit():
    limiter = RateLimiter(max_per_minute=2)
    assert limiter.is_allowed("session_1")
    assert limiter.is_allowed("session_1")
    assert not limiter.is_allowed("session_1")
```

### Tool Loop 测试
```python
def test_tool_call_limit_enforced():
    engine = ToolCallingEngine(max_calls=10)
    for i in range(10):
        engine.call_tool("some_tool")
    with pytest.raises(ToolCallLimitExceeded):
        engine.call_tool("some_tool")
```

### Budget 测试
```python
def test_budget_tracking():
    tracker = BudgetTracker(token_budget=1000)
    tracker.consume_tokens(500)
    assert tracker.remaining_tokens == 500
    tracker.consume_tokens(600)  # 超出预算
    assert tracker.is_over_budget()
```

## 配置管理

所有护栏参数应通过配置文件管理，支持动态调整：

```yaml
# config/risk_guards.yaml
rate_limits:
  max_concurrent_queries_per_session: 5
  max_queries_per_user_per_minute: 30
  max_queries_per_session_per_minute: 20

tool_limits:
  max_tool_calls_per_command: 10
  max_tool_calls_per_session: 100

budgets:
  token_budget_per_session: 100000
  token_budget_per_user_per_day: 500000
  token_budget_per_command: 20000

observability:
  log_level: INFO
  log_file: logs/agentsystem.log
  enable_metrics: true
```

## 监控与告警

- 护栏触发次数统计
- 预算使用率告警（80%、90%、100%）
- 异常错误率告警
- 系统负载告警

## 下一步

1. 创建基础护栏服务（rate_limiter, budget_tracker, observability）
2. 在主路径中集成护栏
3. 编写测试用例
4. 根据实际使用情况调整参数
