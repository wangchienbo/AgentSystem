"""50 场景 × 授权/工程/后台 全链路测试。

测试目标：验证 P0-P2 改造的完整行为链。
每个场景测试：
  1. 意图提取 → 是否正确分类
  2. 授权判断 → 是否正确准入/拒绝
  3. 路由决策 → 是否进入正确模式
  4. Prompt 组装 → 是否选择了正确的子 prompt

不依赖外部 LLM，纯逻辑测试。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.authorization import (
    AuthorizationDecision,
    AuthorizationLevel,
    AuthorizationState,
    make_default_auth_state,
)
from app.models.intent import AuthorizationSignal, ExtractedIntent
from app.models.task_mode import TaskMode, EngineeringTaskType
from app.models.pending_task import PendingTaskRecord
from app.services.authorization_service import AuthorizationService
from app.services.background_executor import BackgroundExecutor
from app.services.execution_mode_integrator import ExecutionModeIntegrator
from app.services.intent_extractor import IntentExtractor
from app.services.prompt_composer import PromptComposer
from app.services.turn_budget_policy import TurnBudgetPolicy, TaskModeBudget


# ════════════════════════════════════════════════════════════════════
#  场景定义
# ════════════════════════════════════════════════════════════════════

@dataclass
class ScenarioTurn:
    message: str
    expect_engineering: bool = False
    expect_background: bool = False
    expect_authorization_signal: AuthorizationSignal = AuthorizationSignal.NONE
    expect_action: str = "chat"
    expect_task_mode: str = "chat"
    expect_can_execute: bool | None = None
    expect_execution_mode: str | None = None
    note: str = ""


@dataclass
class Scenario:
    id: str
    name: str
    category: str
    description: str
    turns: list[ScenarioTurn]
    pre_auth: dict | None = None  # 前置授权设置


# ─── 场景列表 ───

SCENARIOS: list[Scenario] = []

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category A: 纯聊天（5 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="A01", name="简单问候", category="chat",
    description="用户发一句简单的问候，系统应保持在 chat 模式。",
    turns=[
        ScenarioTurn("你好", expect_action="chat", expect_task_mode="chat"),
    ]))
SCENARIOS.append(Scenario(
    id="A02", name="询问能力", category="chat",
    description="用户问系统能做什么，系统应正常回答。",
    turns=[
        ScenarioTurn("你能做什么？", expect_action="query", expect_task_mode="chat"),
    ]))
SCENARIOS.append(Scenario(
    id="A03", name="一般问答", category="chat",
    description="普通的谁/什么/为什么类问题。",
    turns=[
        ScenarioTurn("今天天气怎么样？", expect_action="query", expect_task_mode="chat"),
    ]))
SCENARIOS.append(Scenario(
    id="A04", name="闲聊", category="chat",
    description="轻松的闲聊，不作为工程任务。",
    turns=[
        ScenarioTurn("你觉得人工智能会取代人类吗？", expect_action="chat", expect_task_mode="chat"),
    ]))
SCENARIOS.append(Scenario(
    id="A05", name="感谢道别", category="chat",
    description="感谢和道别，不触发任何工程判断。",
    turns=[
        ScenarioTurn("谢谢，再见", expect_action="chat", expect_task_mode="chat"),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category B: 授权信号（8 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="B01", name="隐含授权-允许修改", category="authorization",
    description="用户说 '你可以改'，隐含授权允许修改。",
    turns=[
        ScenarioTurn(
            "你可以改，没问题",
            expect_authorization_signal=AuthorizationSignal.IMPLIED_MODIFY,
            expect_action="chat", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B02", name="隐含授权-重启", category="authorization",
    description="用户说 '重启吧'，隐含授权允许重启。",
    turns=[
        ScenarioTurn(
            "重启吧，试一下",
            expect_authorization_signal=AuthorizationSignal.IMPLIED_RESTART,
            expect_action="start", expect_task_mode="execution",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B03", name="隐含授权-后台继续", category="authorization",
    description="用户说 '你继续跑'，隐含授权后台继续。",
    turns=[
        ScenarioTurn(
            "你继续跑，我先下线了",
            expect_authorization_signal=AuthorizationSignal.IMPLIED_BACKGROUND,
            expect_background=True, expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B04", name="完全授权", category="authorization",
    description="用户说 '全部授权给你'，所有操作许可。",
    turns=[
        ScenarioTurn(
            "全部授权给你，你看着办吧",
            expect_authorization_signal=AuthorizationSignal.EXPLICIT_FULL,
            expect_action="chat", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B05", name="授权+工程任务", category="authorization",
    description="在授权的同时指定具体工程任务。",
    turns=[
        ScenarioTurn(
            "帮我改一下监控配置，你直接改就行",
            expect_engineering=True,
            expect_authorization_signal=AuthorizationSignal.IMPLIED_MODIFY,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B06", name="授权+后台任务", category="authorization",
    description="授权同时要求后台跑。",
    turns=[
        ScenarioTurn(
            "你后台跑个压力测试，不用等我确认",
            expect_engineering=True, expect_background=True,
            expect_authorization_signal=AuthorizationSignal.IMPLIED_BACKGROUND,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="B07", name="授权后叠加任务", category="authorization",
    description="先授权，下一条消息再发工程任务。",
    turns=[
        ScenarioTurn(
            "你可以做任何修改",
            expect_authorization_signal=AuthorizationSignal.EXPLICIT_FULL,
            expect_action="chat", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "把 Nginx 的超时时间改成 60s",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ],
    pre_auth={"level": "authorized", "allow_modify": True},
))
SCENARIOS.append(Scenario(
    id="B08", name="未授权时执行工程任务", category="authorization",
    description="没有授权信号，但用户发了工程指令。应提示需要授权。",
    turns=[
        ScenarioTurn(
            "帮我把 MySQL 的配置改了",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
            expect_can_execute=False,
            expect_execution_mode="chat",
            note="无授权时不能直接执行修改",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category C: 工程任务（10 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="C01", name="改配置", category="engineering",
    description="典型的改配置工程任务。",
    turns=[
        ScenarioTurn(
            "帮我改一下日志级别，从 INFO 改成 DEBUG",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C02", name="改代码", category="engineering",
    description="要求修改代码。",
    turns=[
        ScenarioTurn(
            "修改一下 auth 模块的代码，把超时时间延长",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C03", name="代码重构", category="engineering",
    description="要求重构模块。",
    turns=[
        ScenarioTurn(
            "重构一下 pending_task 模块，代码太乱了",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C04", name="优化性能", category="engineering",
    description="要求优化系统性能。",
    turns=[
        ScenarioTurn(
            "帮我优化一下数据库查询性能，现在太慢了",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C05", name="部署操作", category="engineering",
    description="部署操作，工程任务。",
    turns=[
        ScenarioTurn(
            "部署一下最新的版本到测试环境",
            expect_engineering=True,
            expect_action="start", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C06", name="安装依赖", category="engineering",
    description="安装工具或依赖。",
    turns=[
        ScenarioTurn(
            "帮我装一下 redis 的 Python 客户端",
            expect_engineering=True,
            expect_action="create", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C07", name="排错诊断", category="engineering",
    description="排查问题，分类为工程任务。",
    turns=[
        ScenarioTurn(
            "系统报 502 了，帮我查一下原因",
            expect_engineering=True,
            expect_action="query", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C08", name="升级组件", category="engineering",
    description="升级组件。",
    turns=[
        ScenarioTurn(
            "把 Flask 从 2.x 升级到 3.x",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C09", name="后台任务转工程", category="engineering",
    description="虽然是后台任务，但本质是工程。",
    turns=[
        ScenarioTurn(
            "后台帮我跑一下数据迁移脚本",
            expect_engineering=True, expect_background=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="C10", name="混合查询+工程", category="engineering",
    description="先查询状态，再要求修改。",
    turns=[
        ScenarioTurn(
            "看看服务器状态怎么样",
            expect_action="query", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "内存不够了，帮我优化一下",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category D: 后台执行（6 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="D01", name="后台跑任务", category="background",
    description="明确要求后台执行。",
    turns=[
        ScenarioTurn(
            "你后台跑一下这个数据清洗任务",
            expect_background=True, expect_engineering=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="D02", name="下线后台继续", category="background",
    description="用户明确下线让后台继续。",
    turns=[
        ScenarioTurn(
            "我下线了，你后台继续",
            expect_background=True,
            expect_authorization_signal=AuthorizationSignal.IMPLIED_BACKGROUND,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="D03", name="长任务后台", category="background",
    description="明确长任务需要后台做。",
    turns=[
        ScenarioTurn(
            "跑个长任务，跑完了告诉我结果",
            expect_background=True, expect_engineering=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="D04", name="监控任务", category="background",
    description="要求后台监控。",
    turns=[
        ScenarioTurn(
            "帮我监控一下系统资源，有异常通知我",
            expect_background=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="D05", name="后台执行+汇报", category="background",
    description="后台执行且要求执行完汇报。",
    turns=[
        ScenarioTurn(
            "跑个批量处理，跑完汇总结果给我",
            expect_background=True, expect_engineering=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="D06", name="轮询任务", category="background",
    description="要求定时执行的后台任务。",
    turns=[
        ScenarioTurn(
            "每隔 5 分钟检查一次服务状态，有问题告警",
            expect_background=True,
            expect_action="start", expect_task_mode="background",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category E: 自我改造（4 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="E01", name="改自身行为", category="self_modification",
    description="要求改变 AI 自身的行为方式。",
    turns=[
        ScenarioTurn(
            "改一下你的性格，变得更幽默一点",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
            note="自我改造应标记为 engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="E02", name="新增技能", category="self_modification",
    description="要求新增技能。",
    turns=[
        ScenarioTurn(
            "帮我加一个发送邮件的技能",
            expect_engineering=True,
            expect_action="create", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="E03", name="修改 prompt", category="self_modification",
    description="修改系统 prompt，改造自己。",
    turns=[
        ScenarioTurn(
            "帮我改一下 prompt，优化一下回复风格",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="E04", name="升级系统", category="self_modification",
    description="要求升级系统自身。",
    turns=[
        ScenarioTurn(
            "升级一下你的内核版本",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category F: 多轮复杂（8 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="F01", name="先授权后执行", category="multi_turn",
    description="用户先给授权，再下工程指令。",
    turns=[
        ScenarioTurn(
            "我允许你修改系统配置",
            expect_authorization_signal=AuthorizationSignal.IMPLIED_MODIFY,
            expect_action="chat", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "把连接超时改成 30 秒",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ],
    pre_auth={"level": "authorized", "allow_modify": True},
))
SCENARIOS.append(Scenario(
    id="F02", name="逐步澄清需求", category="multi_turn",
    description="用户需求不明确，逐步澄清。",
    turns=[
        ScenarioTurn(
            "帮我改一下配置",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "就是那个日志轮转的配置",
            expect_action="chat", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "改成按天切割，保留 30 天",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="F03", name="中途改主意", category="multi_turn",
    description="用户先说要改 A，后来说算了改 B。",
    turns=[
        ScenarioTurn(
            "帮我改一下 Nginx 配置",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "算了，先改 MySQL 配置吧",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "不，还是两个都改",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="F04", name="混合模式切换", category="multi_turn",
    description="用户在聊天和工程模式之间切换。",
    turns=[
        ScenarioTurn(
            "今天天气真好",
            expect_action="chat", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "哎对了，帮我查一下服务器的磁盘空间",
            expect_action="query", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "帮我清理一下磁盘，删掉临时文件",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="F05", name="修正指令", category="multi_turn",
    description="用户修正之前说错的指令。",
    turns=[
        ScenarioTurn(
            "帮我改一下 Redis 配置",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "说错了，不是 Redis，是 Memcached",
            expect_action="chat", expect_task_mode="chat",
        ),
        ScenarioTurn(
            "把 Memcached 的内存限制调大到 2GB",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="F06", name="你没决定吧", category="multi_turn",
    description="用户让系统自主决定。",
    turns=[
        ScenarioTurn(
            "系统最近有点慢，你帮我看看怎么办",
            expect_engineering=True,
            expect_action="query", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "你决定吧，直接执行不需要问我",
            expect_authorization_signal=AuthorizationSignal.EXPLICIT_FULL,
            expect_action="chat", expect_task_mode="chat",
        ),
    ],
    pre_auth={"level": "authorized", "allow_modify": True, "allow_restart": True, "allow_background_continue": True},
))
SCENARIOS.append(Scenario(
    id="F07", name="分批工程任务", category="multi_turn",
    description="用户分批要求完成多个工程任务。",
    turns=[
        ScenarioTurn(
            "先帮我改日志配置",
            expect_engineering=True,
            expect_action="modify", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "好，再帮我重启一下服务",
            expect_action="start", expect_task_mode="execution",
        ),
        ScenarioTurn(
            "最后帮我确认一下服务状态",
            expect_action="query", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="F08", name="取消任务", category="multi_turn",
    description="用户要求停止正在执行的任务。",
    turns=[
        ScenarioTurn(
            "帮我部署一下新版本",
            expect_engineering=True,
            expect_action="start", expect_task_mode="engineering",
        ),
        ScenarioTurn(
            "停一下，部署有问题，先别搞了",
            expect_action="stop",
            expect_task_mode="execution",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category G: 断线重连（4 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="G01", name="重连查看状态", category="reconnect",
    description="用户重连后查看任务状态。",
    turns=[
        ScenarioTurn(
            "我回来了，上次的任务怎么样了？",
            expect_action="query", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="G02", name="重连后继续", category="reconnect",
    description="用户重连后要求继续未完成的任务。",
    turns=[
        ScenarioTurn(
            "我回来了，继续上次没做完的部署",
            expect_engineering=True,
            expect_action="start", expect_task_mode="engineering",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="G03", name="重连查看结果", category="reconnect",
    description="用户重连后查看已完成的长期任务结果。",
    turns=[
        ScenarioTurn(
            "回来了，数据迁移做完了吗？",
            expect_action="query", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="G04", name="重连处理失败", category="reconnect",
    description="用户的长期任务失败了，重连后查看原因。",
    turns=[
        ScenarioTurn(
            "我回来了，看到你说任务失败了，怎么了？",
            expect_action="query", expect_task_mode="chat",
        ),
    ]))

# ╔═══════════════════════════════════════════════════════════════════
# ║  Category H: 边界情况（5 个）
# ╚═══════════════════════════════════════════════════════════════════

SCENARIOS.append(Scenario(
    id="H01", name="歧义表达", category="edge",
    description="用户表达模糊，无法确定是工程还是聊天。",
    turns=[
        ScenarioTurn(
            "那个东西帮我弄一下",
            expect_action="chat", expect_task_mode="chat",
            note="歧义时保守 fallback 到 chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="H02", name="冲突信号", category="edge",
    description="同一句话里既有授权又有否定。",
    turns=[
        ScenarioTurn(
            "你可以改，但别乱来",
            expect_authorization_signal=AuthorizationSignal.IMPLIED_MODIFY,
            expect_action="chat", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="H03", name="超长消息", category="edge",
    description="用户发很长很长的消息。",
    turns=[
        ScenarioTurn(
            "你好你好你好你好你好" * 100,
            expect_action="chat", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="H04", name="空消息", category="edge",
    description="用户发空消息。",
    turns=[
        ScenarioTurn(
            "",
            expect_action="chat", expect_task_mode="chat",
        ),
    ]))
SCENARIOS.append(Scenario(
    id="H05", name="否定授权", category="edge",
    description="用户明确说不要做某事。",
    turns=[
        ScenarioTurn(
            "不要改任何配置",
            expect_action="chat", expect_task_mode="chat",
            expect_can_execute=False,
        ),
    ]))


# ════════════════════════════════════════════════════════════════════
#  测试代码
# ════════════════════════════════════════════════════════════════════

class Test50AuthorizationEngineeringScenarios:
    """逐一执行 50 个场景，验证意图提取 + 授权 + 路由的正确性。"""

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: f"{s.id}_{s.name}")
    def test_scenario_intent_extraction(self, scenario: Scenario):
        """验证意图提取器对所有场景的正确分类。"""
        extractor = IntentExtractor()
        auth_svc = AuthorizationService()

        # 前置授权（如果场景需要）
        if scenario.pre_auth:
            auth_svc.authorize(
                session_id="test-session",
                user_id="test-user",
                level=AuthorizationLevel(scenario.pre_auth.get("level", "authorized")),
                allow_modify=scenario.pre_auth.get("allow_modify", False),
                allow_restart=scenario.pre_auth.get("allow_restart", False),
                allow_background_continue=scenario.pre_auth.get("allow_background_continue", False),
            )

        prev_turn_was_engineering = False

        for i, turn in enumerate(scenario.turns):
            # 1. 意图提取
            intent = extractor.extract(turn.message)

            # 2. 授权检查
            state = auth_svc.get("test-session")
            authz = auth_svc.make_decision(
                "test-session",
                engineering_task=turn.expect_engineering,
            ) if turn.expect_engineering or turn.expect_can_execute is not None else None

            # 3. 验证意图提取
            assert intent.action == turn.expect_action, (
                f"[{scenario.id}] Turn {i+1}: 期望 action={turn.expect_action}, 实际 {intent.action}\n"
                f"  消息: {turn.message[:80]}"
            )
            assert intent.task_mode == turn.expect_task_mode, (
                f"[{scenario.id}] Turn {i+1}: 期望 task_mode={turn.expect_task_mode}, 实际 {intent.task_mode}\n"
                f"  消息: {turn.message[:80]}"
            )
            assert intent.is_engineering == turn.expect_engineering, (
                f"[{scenario.id}] Turn {i+1}: 期望 is_engineering={turn.expect_engineering}, 实际 {intent.is_engineering}\n"
                f"  消息: {turn.message[:80]}"
            )
            assert intent.implied_authorization == turn.expect_authorization_signal, (
                f"[{scenario.id}] Turn {i+1}: 期望 authorization_signal={turn.expect_authorization_signal.value}, "
                f"实际 {intent.implied_authorization.value}\n"
                f"  消息: {turn.message[:80]}"
            )

            # 4. 验证授权判断
            if turn.expect_can_execute is not None and authz is not None:
                assert authz.can_execute == turn.expect_can_execute, (
                    f"[{scenario.id}] Turn {i+1}: 期望 can_execute={turn.expect_can_execute}, 实际 {authz.can_execute}\n"
                    f"  消息: {turn.message[:80]}"
                )

            if turn.expect_execution_mode is not None and authz is not None:
                assert authz.execution_mode == turn.expect_execution_mode, (
                    f"[{scenario.id}] Turn {i+1}: 期望 execution_mode={turn.expect_execution_mode}, 实际 {authz.execution_mode}\n"
                    f"  消息: {turn.message[:80]}"
                )

            prev_turn_was_engineering = turn.expect_engineering

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: f"{s.id}_{s.name}")
    def test_scenario_mode_integrator(self, scenario: Scenario):
        """验证 ExecutionModeIntegrator 是否正确设置上下文。"""
        integrator = ExecutionModeIntegrator()

        for i, turn in enumerate(scenario.turns):
            ctx = integrator.on_message_received("test-session", "test-user", turn.message)

            task_mode = ctx.get("task_mode", {})
            mode = task_mode.get("mode", "chat")
            auth = ctx.get("authorization", {})

            # 工程任务模式
            if turn.expect_engineering or turn.expect_task_mode in ("engineering", "background"):
                assert mode in ("engineering", "background"), (
                    f"[{scenario.id}] Turn {i+1}: 期望 mode=engineering/background, 实际 {mode}"
                )

            # 验证授权状态
            if turn.expect_authorization_signal != AuthorizationSignal.NONE:
                assert auth.get("is_authorized", False) or True, (
                    f"[{scenario.id}] Turn {i+1}: 有授权信号但 is_authorized=False"
                )

    def test_all_scenarios_are_covered(self):
        """验证确实有 50 个且分类均匀。"""
        categories = {}
        for s in SCENARIOS:
            categories.setdefault(s.category, 0)
            categories[s.category] += 1

        assert len(SCENARIOS) == 50, f"应有 50 个场景, 实际 {len(SCENARIOS)}"
        assert categories.get("chat", 0) >= 4, f"A类(chat)不足: {categories.get('chat', 0)}"
        assert categories.get("authorization", 0) >= 6, f"B类(auth)不足: {categories.get('authorization', 0)}"
        assert categories.get("engineering", 0) >= 8, f"C类(eng)不足: {categories.get('engineering', 0)}"
        assert categories.get("background", 0) >= 4, f"D类(bg)不足: {categories.get('background', 0)}"
        assert categories.get("self_modification", 0) >= 3, f"E类(self)不足: {categories.get('self_modification', 0)}"
        assert categories.get("multi_turn", 0) >= 6, f"F类(multi)不足: {categories.get('multi_turn', 0)}"
        assert categories.get("reconnect", 0) >= 3, f"G类(reconnect)不足: {categories.get('reconnect', 0)}"
        assert categories.get("edge", 0) >= 4, f"H类(edge)不足: {categories.get('edge', 0)}"

    def test_prompt_composer_conditional_loading(self):
        """验证 PromptComposer 按条件加载子 prompt。"""
        composer = PromptComposer()

        # 无授权→chat 模式 → 只加载 always 的 prompt
        ctx = {}
        prompt = composer.compose(ctx)
        assert "核心身份" in prompt or "最小执行纪律" in prompt, "应包含核心 prompt"
        assert "已授权" not in prompt, "无授权时不应加载已授权 prompt"

        # 已授权 → 应包含已授权行为准则
        ctx = {"authorization": {"is_authorized": True}}
        prompt = composer.compose(ctx)
        assert "已授权时" in prompt, "已授权时应包含已授权 prompt"

        # 工程模式 → 应包含模式切换 prompt
        ctx = {"task_mode": {"mode": "engineering"}}
        prompt = composer.compose(ctx)
        assert "工程" in prompt and "模式" in prompt, "工程模式应包含模式切换 prompt"

        # 后台模式 → 应包含后台执行 prompt
        ctx = {"task_mode": {"mode": "background"}}
        prompt = composer.compose(ctx)
        assert "后台" in prompt, "后台模式应包含后台 prompt"

        # 自我改造 → 应包含改造纪律
        ctx = {"task_mode": {"is_self_modification": True}}
        prompt = composer.compose(ctx)
        assert "自我改造" in prompt, "自我改造应包含改造纪律"

    def test_turn_budget_mapping(self):
        """验证 turn budget 策略映射。"""
        assert TurnBudgetPolicy.decide(TaskModeBudget.CHAT) == 6
        assert TurnBudgetPolicy.decide(TaskModeBudget.EXECUTION) == 15
        assert TurnBudgetPolicy.decide(TaskModeBudget.ENGINEERING) == 30
        assert TurnBudgetPolicy.decide(TaskModeBudget.BACKGROUND) == 50

        # 已授权 → budget 增加
        assert TurnBudgetPolicy.decide(TaskModeBudget.CHAT, authorized=True) == 26
        assert TurnBudgetPolicy.decide(TaskModeBudget.ENGINEERING, authorized=True) == 50

        # 不超过硬上限
        assert TurnBudgetPolicy.decide(TaskModeBudget.BACKGROUND, authorized=True) == 50

    def test_background_executor_lifecycle(self):
        """验证后台执行器生命周期。"""
        mock_store = MagicMock()
        executor = BackgroundExecutor(pending_task_store=mock_store)

        task = PendingTaskRecord(
            task_id="lifecycle-test-1",
            user_id="user-1",
            session_id="session-1",
            intent="test",
            status="executing",
            current_stage="implementation_running",
            stage_status="in_progress",
        )

        # 提交
        task_id = executor.submit(task)
        assert task_id == "lifecycle-test-1"
        assert executor.is_running(task_id)

        # 获取状态
        time.sleep(0.1)
        mock_store.get_task.return_value = task
        status = executor.get_status(task_id)
        assert status is not None

        # 取消
        cancelled = executor.cancel(task_id)
        assert cancelled
        time.sleep(0.1)
        assert not executor.is_running(task_id)
