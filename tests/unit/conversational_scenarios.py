from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScenarioTurn:
    turn_number: int
    user_message: str
    expected_decision: str | None = None
    expected_asset_id: str | None = None
    expected_method: str | None = None
    allow_text_fallback: bool = True


@dataclass(frozen=True)
class ConversationalScenario:
    scenario_id: str
    category: str
    title: str
    description: str
    turns: tuple[ScenarioTurn, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "user_message": t.user_message,
                    "expected_decision": t.expected_decision,
                    "expected_asset_id": t.expected_asset_id,
                    "expected_method": t.expected_method,
                    "allow_text_fallback": t.allow_text_fallback,
                }
                for t in self.turns
            ],
            "tags": list(self.tags),
        }


def load_all_scenarios() -> list[ConversationalScenario]:
    return _scenarios


_simple_query_scenarios = [
    ConversationalScenario(
        scenario_id="SQ001",
        category="simple_query",
        title="查看系统状态",
        description="用户想快速了解当前系统的整体运行状态。",
        turns=(
            ScenarioTurn(1, "现在系统状态怎么样，还正常吗？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="strategy_overview"),
        ),
        tags=("simple", "status"),
    ),
    ConversationalScenario(
        scenario_id="SQ002",
        category="simple_query",
        title="有什么可用的资产",
        description="用户首次进入系统，想知道有哪些功能资产可用。",
        turns=(
            ScenarioTurn(1, "这个系统都有哪些功能？", expected_decision="text"),
        ),
        tags=("simple", "asset_list"),
    ),
    ConversationalScenario(
        scenario_id="SQ003",
        category="simple_query",
        title="查询自我迭代资产详情",
        description="用户想深入了解自我迭代治理资产的具体能力。",
        turns=(
            ScenarioTurn(1, "自我迭代那个资产具体是做什么的？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("simple", "detail"),
    ),
    ConversationalScenario(
        scenario_id="SQ004",
        category="simple_query",
        title="查看配置中心能力",
        description="用户询问配置管理相关能力。",
        turns=(
            ScenarioTurn(1, "配置中心能做什么？", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("simple", "detail"),
    ),
    ConversationalScenario(
        scenario_id="SQ005",
        category="simple_query",
        title="快速问候",
        description="用户发送简短问候，系统应直接回答。",
        turns=(
            ScenarioTurn(1, "你好", expected_decision="text"),
        ),
        tags=("simple", "greeting"),
    ),
    ConversationalScenario(
        scenario_id="SQ006",
        category="simple_query",
        title="当前时间",
        description="用户询问当前时间。",
        turns=(
            ScenarioTurn(1, "现在几点了？", expected_decision="text"),
        ),
        tags=("simple", "utility"),
    ),
    ConversationalScenario(
        scenario_id="SQ007",
        category="simple_query",
        title="查看模型配置",
        description="用户想了解当前模型的配置信息。",
        turns=(
            ScenarioTurn(1, "现在用的是哪个模型？", expected_decision="invoke", expected_asset_id="asset:config_center:v1", expected_method="model_config_summary"),
        ),
        tags=("simple", "model_info"),
    ),
    ConversationalScenario(
        scenario_id="SQ008",
        category="simple_query",
        title="资产健康状态",
        description="用户询问各资产的健康状态。",
        turns=(
            ScenarioTurn(1, "各个资产都健康吗？", expected_decision="invoke", expected_asset_id="asset:asset_center:v1", expected_method="list_models"),
        ),
        tags=("simple", "health"),
    ),
    ConversationalScenario(
        scenario_id="SQ009",
        category="simple_query",
        title="帮助请求",
        description="用户寻求帮助。",
        turns=(
            ScenarioTurn(1, "你能帮我做什么？", expected_decision="text"),
        ),
        tags=("simple", "help"),
    ),
    ConversationalScenario(
        scenario_id="SQ010",
        category="simple_query",
        title="查看资产中心能力",
        description="用户想了解资产中心自身的能力。",
        turns=(
            ScenarioTurn(1, "资产中心是做什么的？", expected_decision="need_asset_detail_id", expected_asset_id="asset:asset_center:v1"),
        ),
        tags=("simple", "asset_center"),
    ),
]

_detail_request_scenarios = [
    ConversationalScenario(
        scenario_id="DR001",
        category="detail_request",
        title="深入理解自我迭代",
        description="用户希望详细了解自我迭代的策略视图。",
        turns=(
            ScenarioTurn(1, "给我看一下自我迭代的详细能力", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "它的治理策略是什么？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="strategy_overview"),
        ),
        tags=("multi_turn", "detail", "governance"),
    ),
    ConversationalScenario(
        scenario_id="DR002",
        category="detail_request",
        title="对比两个资产",
        description="用户想知道两个资产之间的区别。",
        turns=(
            ScenarioTurn(1, "自我迭代和配置中心有什么区别？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "那配置中心呢？", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "好的，总结一下差异", expected_decision="text"),
        ),
        tags=("multi_turn", "comparison", "detail"),
    ),
    ConversationalScenario(
        scenario_id="DR003",
        category="detail_request",
        title="查看资产方法列表",
        description="用户想查看某个资产支持的所有方法。",
        turns=(
            ScenarioTurn(1, "自我迭代支持哪些操作？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("simple", "methods"),
    ),
    ConversationalScenario(
        scenario_id="DR004",
        category="detail_request",
        title="请求不存在的资产详情",
        description="用户请求一个不存在的资产，系统应明确告知。",
        turns=(
            ScenarioTurn(1, "给我看一下资产 nonexistent 的详情", expected_decision="text"),
        ),
        tags=("error", "not_found"),
    ),
    ConversationalScenario(
        scenario_id="DR005",
        category="detail_request",
        title="重复请求已加载详情",
        description="用户重复请求已加载的资产详情，系统应利用缓存。",
        turns=(
            ScenarioTurn(1, "自我迭代的详情是什么？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "再说一次自我迭代的详情", expected_decision="text"),
        ),
        tags=("multi_turn", "cache", "repeat"),
    ),
    ConversationalScenario(
        scenario_id="DR006",
        category="detail_request",
        title="请求资产详情后执行方法",
        description="用户先获取详情，然后触发方法执行。",
        turns=(
            ScenarioTurn(1, "配置的详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(2, "帮我查一下当前配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("multi_turn", "detail_to_invoke"),
    ),
    ConversationalScenario(
        scenario_id="DR007",
        category="detail_request",
        title="查看自我迭代模型需求",
        description="用户关注资产的模型需求。",
        turns=(
            ScenarioTurn(1, "self-iteration需要什么模型？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("simple", "model_requirement"),
    ),
    ConversationalScenario(
        scenario_id="DR008",
        category="detail_request",
        title="请求多个资产详情",
        description="用户连续请求多个资产的详情。",
        turns=(
            ScenarioTurn(1, "self-iteration的详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "配置中心的详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "资产中心呢？", expected_decision="need_asset_detail_id", expected_asset_id="asset:asset_center:v1"),
        ),
        tags=("multi_turn", "multi_detail"),
    ),
]

_invoke_scenarios = [
    ConversationalScenario(
        scenario_id="IV001",
        category="invoke",
        title="执行自我迭代策略概览",
        description="用户触发自我迭代的策略概览方法。",
        turns=(
            ScenarioTurn(1, "帮我跑一下自我迭代的策略概览", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="strategy_overview"),
        ),
        tags=("invoke", "strategy"),
    ),
    ConversationalScenario(
        scenario_id="IV002",
        category="invoke",
        title="执行配置查询",
        description="用户触发配置中心的配置查询。",
        turns=(
            ScenarioTurn(1, "查一下当前系统配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1", expected_method="get_config"),
        ),
        tags=("invoke", "config"),
    ),
    ConversationalScenario(
        scenario_id="IV003",
        category="invoke",
        title="带参数的方法调用",
        description="用户在自然语言中隐式包含参数。",
        turns=(
            ScenarioTurn(1, "把最大token数改成16000", expected_decision="invoke", expected_asset_id="asset:config_center:v1", expected_method="update_config"),
        ),
        tags=("invoke", "parameter"),
    ),
    ConversationalScenario(
        scenario_id="IV004",
        category="invoke",
        title="调用不存在的方法",
        description="用户请求资产中不存在的方法。",
        turns=(
            ScenarioTurn(1, "让自我迭代跑一下不存在的功能", expected_decision="text"),
        ),
        tags=("invoke", "error", "method_not_found"),
    ),
    ConversationalScenario(
        scenario_id="IV005",
        category="invoke",
        title="连续执行多个方法",
        description="用户连续触发多个资产的方法。",
        turns=(
            ScenarioTurn(1, "先看自我迭代的策略", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="strategy_overview"),
            ScenarioTurn(2, "再看看配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1", expected_method="get_config"),
            ScenarioTurn(3, "总结一下", expected_decision="text"),
        ),
        tags=("multi_turn", "invoke", "summary"),
    ),
    ConversationalScenario(
        scenario_id="IV006",
        category="invoke",
        title="触发模型配置摘要",
        description="用户触发配置中心的模型配置摘要方法。",
        turns=(
            ScenarioTurn(1, "总结一下当前的模型配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1", expected_method="model_config_summary"),
        ),
        tags=("invoke", "model"),
    ),
    ConversationalScenario(
        scenario_id="IV007",
        category="invoke",
        title="触发自我迭代治理摘要",
        description="用户触发自我迭代的治理摘要方法。",
        turns=(
            ScenarioTurn(1, "给我一个治理摘要", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="governance_summary"),
        ),
        tags=("invoke", "governance"),
    ),
    ConversationalScenario(
        scenario_id="IV008",
        category="invoke",
        title="先详情后调用",
        description="用户先查看资产详情，然后触发方法。",
        turns=(
            ScenarioTurn(1, "配置的详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(2, "查配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("multi_turn", "invoke"),
    ),
    ConversationalScenario(
        scenario_id="IV009",
        category="invoke",
        title="查询模型列表",
        description="用户触发资产中心的模型列表查询。",
        turns=(
            ScenarioTurn(1, "有哪些可用模型？", expected_decision="invoke", expected_asset_id="asset:asset_center:v1"),
        ),
        tags=("invoke", "model_list"),
    ),
]

_fallback_scenarios = [
    ConversationalScenario(
        scenario_id="FB001",
        category="fallback",
        title="首选模型不健康时的降级",
        description="首选模型不可用时，系统应自动降级到fallback模型。",
        turns=(
            ScenarioTurn(1, "帮我分析当前系统的问题", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("fallback", "model_selection"),
    ),
    ConversationalScenario(
        scenario_id="FB002",
        category="fallback",
        title="fallback也不满足最低要求",
        description="fallback模型不满足最低语义能力，系统应明确失败。",
        turns=(
            ScenarioTurn(1, "需要一个强推理的任务", expected_decision="text"),
        ),
        tags=("fallback", "failure"),
    ),
    ConversationalScenario(
        scenario_id="FB003",
        category="fallback",
        title="部分资产可用fallback模型",
        description="某些资产的模型需求较低，可以用fallback模型。",
        turns=(
            ScenarioTurn(1, "查一下配置摘要", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("fallback", "simple_asset"),
    ),
]

_failure_recovery_scenarios = [
    ConversationalScenario(
        scenario_id="FR001",
        category="failure_recovery",
        title="调用失败后的重试",
        description="资产方法调用失败后，用户尝试重新执行。",
        turns=(
            ScenarioTurn(1, "执行一个会失败的操作", expected_decision="invoke"),
            ScenarioTurn(2, "再试一次", expected_decision="invoke"),
        ),
        tags=("failure", "retry"),
    ),
    ConversationalScenario(
        scenario_id="FR002",
        category="failure_recovery",
        title="资产不可用后的替代方案",
        description="某个资产不可用时，用户转向其他可用资产。",
        turns=(
            ScenarioTurn(1, "用self-iteration跑一下", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "那个不行，换配置中心看看", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("failure", "alternative"),
    ),
    ConversationalScenario(
        scenario_id="FR003",
        category="failure_recovery",
        title="模型全部不可用",
        description="所有模型都不可用时，系统应给出明确错误信息。",
        turns=(
            ScenarioTurn(1, "帮我做一个复杂分析", expected_decision="text"),
        ),
        tags=("failure", "model_down"),
    ),
]

_clarification_scenarios = [
    ConversationalScenario(
        scenario_id="CL001",
        category="clarification",
        title="需求不明确的澄清",
        description="用户提出模糊需求，系统需要请求澄清。",
        turns=(
            ScenarioTurn(1, "帮我做点什么吧", expected_decision="text"),
            ScenarioTurn(2, "嗯...就是日常维护", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("clarification", "vague"),
    ),
    ConversationalScenario(
        scenario_id="CL002",
        category="clarification",
        title="多资产意图的澄清",
        description="用户的请求可能涉及多个资产，需要澄清。",
        turns=(
            ScenarioTurn(1, "帮我优化一下系统", expected_decision="text"),
            ScenarioTurn(2, "就是性能和配置方面", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("clarification", "multi_asset"),
    ),
    ConversationalScenario(
        scenario_id="CL003",
        category="clarification",
        title="参数缺失的澄清",
        description="用户触发需要参数的方法但未提供。",
        turns=(
            ScenarioTurn(1, "改一下配置", expected_decision="text"),
            ScenarioTurn(2, "把超时改成30秒", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("clarification", "parameter"),
    ),
]

_topic_shift_scenarios = [
    ConversationalScenario(
        scenario_id="TS001",
        category="topic_shift",
        title="从状态查询切换到配置修改",
        description="用户从查看状态切换到修改配置。",
        turns=(
            ScenarioTurn(1, "系统状态怎么样？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "对了，把最大token改一下", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("topic_shift", "multi_turn"),
    ),
    ConversationalScenario(
        scenario_id="TS002",
        category="topic_shift",
        title="从技术讨论切到闲聊",
        description="用户从技术讨论切换到非技术话题。",
        turns=(
            ScenarioTurn(1, "自我迭代的治理策略是什么？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "算了，讲个笑话吧", expected_decision="text"),
        ),
        tags=("topic_shift", "multi_turn"),
    ),
    ConversationalScenario(
        scenario_id="TS003",
        category="topic_shift",
        title="从配置查询切到资产详情",
        description="用户从配置查询切换到了解资产详情。",
        turns=(
            ScenarioTurn(1, "当前模型配置是什么？", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(2, "那self-iteration这个资产呢？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("topic_shift", "multi_turn"),
    ),
    ConversationalScenario(
        scenario_id="TS004",
        category="topic_shift",
        title="连续话题跳跃",
        description="用户在不同资产间快速切换。",
        turns=(
            ScenarioTurn(1, "先看状态", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "再看配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "资产中心本身呢？", expected_decision="need_asset_detail_id", expected_asset_id="asset:asset_center:v1"),
            ScenarioTurn(4, "好了，总结一下", expected_decision="text"),
        ),
        tags=("topic_shift", "multi_turn", "complex"),
    ),
]

_follow_up_scenarios = [
    ConversationalScenario(
        scenario_id="FU001",
        category="follow_up",
        title="对策略概览的追问",
        description="用户在获取策略概览后继续追问细节。",
        turns=(
            ScenarioTurn(1, "自我迭代的策略概览", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1", expected_method="strategy_overview"),
            ScenarioTurn(2, "其中治理那块能再展开吗？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("follow_up", "multi_turn"),
    ),
    ConversationalScenario(
        scenario_id="FU002",
        category="follow_up",
        title="对配置结果的追问",
        description="用户在获取配置信息后追问修改历史。",
        turns=(
            ScenarioTurn(1, "当前配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(2, "上次改配置是什么时候？", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
        ),
        tags=("follow_up", "multi_turn"),
    ),
    ConversationalScenario(
        scenario_id="FU003",
        category="follow_up",
        title="连续三轮追问同一资产",
        description="用户连续追问同一资产的不同方面。",
        turns=(
            ScenarioTurn(1, "self-iteration的概览", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "它的模型需求是什么？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(3, "它的方法列表呢？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("follow_up", "multi_turn", "detail"),
    ),
    ConversationalScenario(
        scenario_id="FU004",
        category="follow_up",
        title="追问模型资源状态",
        description="用户追问模型资源层的运行时状态。",
        turns=(
            ScenarioTurn(1, "现在用的哪个模型？", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(2, "备选模型健康吗？", expected_decision="invoke", expected_asset_id="asset:asset_center:v1"),
        ),
        tags=("follow_up", "multi_turn", "model"),
    ),
]

_complex_mixed_scenarios = [
    ConversationalScenario(
        scenario_id="CM001",
        category="complex_mixed",
        title="完整诊断流程",
        description="用户执行从状态检查到配置调整再到验证的完整流程。",
        turns=(
            ScenarioTurn(1, "系统还好吗？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "有问题？看看配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "把超时调大一点", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(4, "再检查一下状态", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(5, "好了吗？", expected_decision="text"),
        ),
        tags=("complex", "multi_turn", "diagnostic"),
    ),
    ConversationalScenario(
        scenario_id="CM002",
        category="complex_mixed",
        title="资产发现到执行",
        description="用户从发现资产到了解详情再到执行操作的完整链路。",
        turns=(
            ScenarioTurn(1, "系统有哪些资产？", expected_decision="text"),
            ScenarioTurn(2, "self-iteration是干嘛的？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(3, "跑一下它的策略概览", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
        ),
        tags=("complex", "multi_turn", "discovery_to_action"),
    ),
    ConversationalScenario(
        scenario_id="CM003",
        category="complex_mixed",
        title="跨资产协调任务",
        description="用户需要协调多个资产完成一个复合任务。",
        turns=(
            ScenarioTurn(1, "帮我做一次全面检查", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "配置方面有没需要注意的？", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "模型资源呢？", expected_decision="invoke", expected_asset_id="asset:asset_center:v1"),
            ScenarioTurn(4, "给我一份总结报告", expected_decision="text"),
        ),
        tags=("complex", "multi_turn", "coordination"),
    ),
    ConversationalScenario(
        scenario_id="CM004",
        category="complex_mixed",
        title="长链路复杂对话",
        description="用户在一个长对话中经历多种交互模式。",
        turns=(
            ScenarioTurn(1, "你好", expected_decision="text"),
            ScenarioTurn(2, "系统状态？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(3, "我想看看self-iteration的详细能力", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(4, "它的模型需求是啥？", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(5, "执行策略概览", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(6, "再看看配置中心", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(7, "改一下max_tokens", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(8, "好了，总结一下做了什么", expected_decision="text"),
        ),
        tags=("complex", "multi_turn", "long_chain", "mixed"),
    ),
    ConversationalScenario(
        scenario_id="CM005",
        category="complex_mixed",
        title="失败+恢复+切换",
        description="用户经历失败后恢复并切换到其他资产。",
        turns=(
            ScenarioTurn(1, "跑一个复杂分析", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(2, "失败了？那看看配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(3, "配置没问题，再试一次分析", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(4, "还是不行，先这样吧", expected_decision="text"),
        ),
        tags=("complex", "multi_turn", "failure", "recovery"),
    ),
    ConversationalScenario(
        scenario_id="CM006",
        category="complex_mixed",
        title="10轮极限对话",
        description="用户进行一个10轮的复杂对话，覆盖多种模式。",
        turns=(
            ScenarioTurn(1, "你好，系统怎么样了？", expected_decision="text"),
            ScenarioTurn(2, "看看状态", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(3, "self-iteration详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(4, "配置中心详情", expected_decision="need_asset_detail_id", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(5, "跑self-iteration策略", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(6, "查配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(7, "改配置", expected_decision="invoke", expected_asset_id="asset:config_center:v1"),
            ScenarioTurn(8, "模型资源状态", expected_decision="invoke", expected_asset_id="asset:asset_center:v1"),
            ScenarioTurn(9, "有没风险？", expected_decision="invoke", expected_asset_id="asset:self_iteration_center:v1"),
            ScenarioTurn(10, "好，总结", expected_decision="text"),
        ),
        tags=("complex", "multi_turn", "10_turns", "stress"),
    ),
]

_all_groups = [
    _simple_query_scenarios,
    _detail_request_scenarios,
    _invoke_scenarios,
    _fallback_scenarios,
    _failure_recovery_scenarios,
    _clarification_scenarios,
    _topic_shift_scenarios,
    _follow_up_scenarios,
    _complex_mixed_scenarios,
]

_scenarios: list[ConversationalScenario] = []
for group in _all_groups:
    _scenarios.extend(group)
