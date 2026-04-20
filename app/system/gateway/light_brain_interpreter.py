"""LightBrain Interpreter — rule-based intent parsing with optional LLM fallback.

Translates natural language user messages into structured InterpretedCommand objects.
Phase 8.1 uses keyword/pattern matching; Phase 8.3 adds LLM-based parsing fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.tool_registry import ToolRegistry, ToolDefinition

from app.models.chat import ActionSuggestion, InterpretedCommand


class LightBrainInterpreter:
    def __init__(self) -> None:
        self._pending_runtime_asset_clarifications: dict[str, dict[str, Any]] = {}

    """Rule-based interpreter that maps user messages to structured commands.

    Phase 8.3: optionally falls back to LLM parsing when rule-based confidence
    is low (returns 'unclear' with confidence < 0.5). Results are cached so
    identical messages don't trigger repeated LLM calls.
    
    Two-tier intent recognition:
    - EXACT_MATCH_PATTERNS: 100% precise patterns, always bypass LLM (zero cost)
    - FUZZY_MATCH_PATTERNS: fuzzy patterns, routed through LLM when fuzzy_regex_match=False
    - fuzzy_regex_match: config switch (default False). When False, only exact matches
      bypass LLM; everything else goes through LLM for intent analysis.
    """

    # ---- EXACT MATCH PATTERNS (always bypass LLM, zero cost) ----
    # These are 100% unambiguous — pure greetings, help requests, status queries
    EXACT_MATCH_PATTERNS: list[tuple[str, re.Pattern, str]] = [
        ("greet", re.compile(r"^(你好|嗨|hi|hello|hey|哈喽)$", re.IGNORECASE), "Pure greeting"),
        ("query_help", re.compile(r"^(帮助|help|教教我|怎么用)$", re.IGNORECASE), "Pure help request"),
        ("query_status", re.compile(r"^(系统状态|状态|运行情况)$", re.IGNORECASE), "Pure status query"),
    ]

    # ---- FUZZY MATCH PATTERNS (routed through LLM when fuzzy_regex_match=False) ----
    FUZZY_MATCH_PATTERNS: list[tuple[str, re.Pattern, str]] = [
        # (intent_name, compiled_regex, description)
        ("create_app", re.compile(r"(创建|新建|建|建立|生成|做一个|搞一个).*(app|应用|程序|模块)", re.IGNORECASE), "Create a new app"),
        ("create_app", re.compile(r"(帮我|给我|我要).*(创建|新建|建|建立).*(监控|日报|提醒|翻译|爬虫|定时|通知|记录|工具|小说|日记|博客|音乐)", re.IGNORECASE), "Create app by action type"),
        ("start_app", re.compile(r"(启动|开启|运行|开始|激活|打开).*(app|应用|程序|监控|日报|提醒|翻译|服务|小说|日记|博客|音乐|监控)", re.IGNORECASE), "Start an app"),
        ("start_app", re.compile(r"(启动|开启|运行|开始)\s+[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Start app by name"),
        ("start_app", re.compile(r"^(启动|开启|恢复|继续|运行)(一下)?$", re.IGNORECASE), "Start/resume"),
        ("start_app", re.compile(r"把\s*.+\s*打开", re.IGNORECASE), "Start app (把...打开)"),
        ("stop_app", re.compile(r"把\s*.+\s*关掉", re.IGNORECASE), "Stop app (把...关掉)"),
        ("stop_app", re.compile(r"(停止|关闭|关掉|停掉|终止).*(app|应用|程序|监控|日报|提醒|翻译|服务|小说|日记|博客|音乐)", re.IGNORECASE), "Stop an app"),
        ("stop_app", re.compile(r"(停止|关闭|关掉|停掉)\s+[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Stop app by name"),
        ("pause_app", re.compile(r"(暂停|挂起).{0,5}[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Pause an app"),
        ("resume_app", re.compile(r"(恢复|继续|恢复运行).{0,5}[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Resume an app"),
        ("modify_app", re.compile(r"(修改|更改|更新|调整|改一下|编辑|配置).*(app|应用|程序|设置|配置)", re.IGNORECASE), "Modify an app"),
        ("modify_app", re.compile(r"把.+改成|把.+改为|把.+调整为"), "Modify app (把...改成)"),
        ("delete_app", re.compile(r"(删除|删掉|移除|干掉|销毁).*(app|应用|程序)", re.IGNORECASE), "Delete an app"),
        ("query_app", re.compile(r"(查看|查询|状态|详情|信息).*(app|应用|程序)", re.IGNORECASE), "Query app status"),
        ("query_app", re.compile(r".*(异常|问题|错误|告警|报告|完成).*(今天|最近|今天有|今天发现)", re.IGNORECASE), "Query app results"),
        ("list_apps", re.compile(r"(列出|看看|有哪些|列表|我的|我).*(app|应用|程序|在跑|运行)", re.IGNORECASE), "List apps"),
        ("list_apps", re.compile(r"(我的|我).*(app|应用|程序)", re.IGNORECASE), "List apps - my apps"),
        ("list_apps", re.compile(r"^.*(app|应用|程序).*(列表|有哪些|几个)", re.IGNORECASE), "List apps alt"),
        ("modify_interactive_app", re.compile(r"(修改|改一下|优化|调整|美化|换|换一|设计|重新设计).*(界面|聊天|页面|前端|主题|样式|UI|外观|皮肤|风格)", re.IGNORECASE), "Modify interactive app UI"),
        ("modify_interactive_app", re.compile(r"(加个|添加|增加|来个|做个|搞个).*(侧边栏|顶部|导航|按钮|快捷|深色|浅色|亮|暗)", re.IGNORECASE), "Add UI element"),
        ("modify_interactive_app", re.compile(r"(自己改|自修改|self.modify|改自己|改一下自己|优化自己|修改自己)", re.IGNORECASE), "Self-modify interactive app"),
        ("modify_interactive_app", re.compile(r"(界面太|太暗|太亮|太丑|不好看|不好看|优化一下|好看一点)", re.IGNORECASE), "UI improvement request"),
        ("modify_interactive_app", re.compile(r"(换个|切换).*(主题|颜色|风格|皮肤)", re.IGNORECASE), "Theme switch"),
        # Permission management
        ("grant_admin", re.compile(r"(给|授予|赋|提升|升级)\s*[^\s，,。.!！]+\s*(管理员|admin|sudo)"), "Grant admin role"),
        ("grant_admin", re.compile(r"(grant|give)\s*(admin|sudo|manager)\s*(to|for)\s*"), "Grant admin role (EN)"),
        ("grant_root", re.compile(r"(给|授予|赋|提升|升级)\s*[^\s，,。.!！]+\s*(root|超级管理员|最高权限)"), "Grant root role"),
        ("grant_root", re.compile(r"(promote|upgrade)\s*[^\s，,。.!！]+\s*to\s*root"), "Grant root role (EN)"),
        ("revoke_role", re.compile(r"(撤销|取消|剥夺|移除|降级)\s*[^\s，,。.!！]+\s*(的)?\s*(管理员|admin|sudo|权限|角色)"), "Revoke role"),
        ("revoke_role", re.compile(r"(revoke|remove|demote)\s*(admin|sudo|role|permission)"), "Revoke role (EN)"),
        ("show_permissions", re.compile(r"(查看|显示|查询)\s*[^\s，,。.!！]*\s*权限"), "Show permissions"),
        ("show_permissions", re.compile(r"(show|check|get)\s*(permission|role)"), "Show permissions (EN)"),
        ("list_users", re.compile(r"(列出|查看|显示|查询)\s*(所有|全部)?\s*(用户|成员|账号)"), "List users"),
        ("list_users", re.compile(r"(list|show|get)\s*(all\s*)?(user|member)"), "List users (EN)"),
        ("show_self", re.compile(r"(我[^的]*什么|我的|查看我的)\s*(权限|角色|级别|身份)"), "Show own permissions"),
        ("list_assets", re.compile(r"(有哪些|有什么|列出|看看).*(资产|服务|能力|runtime|运行态)", re.IGNORECASE), "List runtime assets"),
        ("query_asset_info", re.compile(r"(查看|查询|看看).*(资产|服务).*(详情|信息|能力)", re.IGNORECASE), "Query runtime asset info"),
        ("call_asset_method", re.compile(r"(调用|执行|运行).*(资产|服务).*(方法|能力)", re.IGNORECASE), "Call runtime asset method"),
    ]

    # Combined pattern view used by current interpreter flow
    INTENT_PATTERNS = EXACT_MATCH_PATTERNS + FUZZY_MATCH_PATTERNS

    # Config: fuzzy regex matching (default True in the current runtime)
    # True: all patterns try regex first (no LLM needed for common intents)
    # False: only exact matches bypass LLM; everything else goes through LLM
    fuzzy_regex_match: bool = True

    # Valid intent values the LLM may return
    VALID_INTENTS = {
        "greet", "list_apps", "create_app", "start_app", "stop_app",
        "pause_app", "resume_app", "query_app", "modify_app", "delete_app",
        "query_status", "query_help", "unclear",
        "modify_interactive_app", "self_modify", "query_user", "register_user",
        "grant_admin", "grant_root", "revoke_role", "show_permissions", "list_users", "show_self",
        "list_assets", "query_asset_info", "call_asset_method", "query_asset_detail",
    }

    # LLM intent parsing result cache: key -> InterpretedCommand
    _llm_cache: dict[str, InterpretedCommand] = {}

    # -- intent patterns -----------------------------------------------------

    INTENT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
        # (intent_name, compiled_regex, description)
        ("create_app", re.compile(r"(创建|新建|建|建立|生成|做一个|搞一个).*(app|应用|程序|模块)", re.IGNORECASE), "Create a new app"),
        ("create_app", re.compile(r"(帮我|给我|我要).*(创建|新建|建|建立).*(监控|日报|提醒|翻译|爬虫|定时|通知|记录|工具|小说|日记|博客|音乐)", re.IGNORECASE), "Create app by action type"),
        ("start_app", re.compile(r"(启动|开启|运行|开始|激活|打开).*(app|应用|程序|监控|日报|提醒|翻译|服务|小说|日记|博客|音乐|监控)", re.IGNORECASE), "Start an app"),
        ("start_app", re.compile(r"(启动|开启|运行|开始)\s+[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Start app by name"),
        ("start_app", re.compile(r"^(启动|开启|恢复|继续|运行)(一下)?$", re.IGNORECASE), "Start/resume"),
        ("start_app", re.compile(r"把\s*.+\s*打开", re.IGNORECASE), "Start app (把...打开)"),
        ("stop_app", re.compile(r"把\s*.+\s*关掉", re.IGNORECASE), "Stop app (把...关掉)"),
        ("stop_app", re.compile(r"(停止|关闭|关掉|停掉|终止).*(app|应用|程序|监控|日报|提醒|翻译|服务|小说|日记|博客|音乐)", re.IGNORECASE), "Stop an app"),
        ("stop_app", re.compile(r"(停止|关闭|关掉|停掉)\s+[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Stop app by name"),
        ("pause_app", re.compile(r"(暂停|挂起).{0,5}[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Pause an app"),
        ("resume_app", re.compile(r"(恢复|继续|恢复运行).{0,5}[\u4e00-\u9fa5a-zA-Z]{2,15}", re.IGNORECASE), "Resume an app"),
        ("modify_app", re.compile(r"(修改|更改|更新|调整|改一下|编辑|配置).*(app|应用|程序|设置|配置)", re.IGNORECASE), "Modify an app"),
        ("modify_app", re.compile(r"把.+改成|把.+改为|把.+调整为"), "Modify app (把...改成)"),
        ("delete_app", re.compile(r"(删除|删掉|移除|干掉|销毁).*(app|应用|程序)", re.IGNORECASE), "Delete an app"),
        ("query_app", re.compile(r"(查看|查询|状态|详情|信息).*(app|应用|程序)", re.IGNORECASE), "Query app status"),
        ("query_app", re.compile(r".*(异常|问题|错误|告警|报告|完成).*(今天|最近|今天有|今天发现)", re.IGNORECASE), "Query app results"),
        ("list_apps", re.compile(r"(列出|看看|有哪些|列表|我的|我).*(app|应用|程序|在跑|运行)", re.IGNORECASE), "List apps"),
        ("list_apps", re.compile(r"(我的|我).*(app|应用|程序)", re.IGNORECASE), "List apps - my apps"),
        ("list_apps", re.compile(r"^.*(app|应用|程序).*(列表|有哪些|几个)", re.IGNORECASE), "List apps alt"),
        ("query_status", re.compile(r"(系统状态|状态|健康|运行情况|运行正常|整体情况|概况|多少.*app.*在跑|多少.*在跑|多少.*运行)", re.IGNORECASE), "System status query"),
        ("query_help", re.compile(r"(帮助|help|怎么用|如何使用|能做什么|功能|说明|教教|教程|引导|新手|入门|你能帮我做什么|你能做什么|你能干啥|有什么能力|有什么功能)", re.IGNORECASE), "Help query"),
        ("greet", re.compile(r"^(你好|嗨|hi|hello|hey|哈喽|早上好|下午好|晚上好|早上好|下午好|晚上好)", re.IGNORECASE), "Greeting"),
        ("modify_interactive_app", re.compile(r"(修改|改一下|优化|调整|美化|换|换一|设计|重新设计).*(界面|聊天|页面|前端|主题|样式|UI|外观|皮肤|风格)", re.IGNORECASE), "Modify interactive app UI"),
        ("modify_interactive_app", re.compile(r"(加个|添加|增加|来个|做个|搞个).*(侧边栏|顶部|导航|按钮|快捷|深色|浅色|亮|暗)", re.IGNORECASE), "Add UI element"),
        ("modify_interactive_app", re.compile(r"(自己改|自修改|self.modify|改自己|改一下自己|优化自己|修改自己)", re.IGNORECASE), "Self-modify interactive app"),
        ("modify_interactive_app", re.compile(r"(界面太|太暗|太亮|太丑|不好看|不好看|优化一下|好看一点)", re.IGNORECASE), "UI improvement request"),
        ("modify_interactive_app", re.compile(r"(换个|切换).*(主题|颜色|风格|皮肤)", re.IGNORECASE), "Theme switch"),
        # Permission management (root/admin) — use \s* for flexible spacing
        ("grant_admin", re.compile(r"(给|授予|赋|提升|升级)\s*[^\s，,。.!！]+\s*(管理员|admin|sudo)"), "Grant admin role"),
        ("grant_admin", re.compile(r"(grant|give)\s*(admin|sudo|manager)\s*(to|for)\s*"), "Grant admin role (EN)"),
        ("grant_root", re.compile(r"(给|授予|赋|提升|升级)\s*[^\s，,。.!！]+\s*(root|超级管理员|最高权限)"), "Grant root role"),
        ("grant_root", re.compile(r"(promote|upgrade)\s*[^\s，,。.!！]+\s*to\s*root"), "Grant root role (EN)"),
        ("revoke_role", re.compile(r"(撤销|取消|剥夺|移除|降级)\s*[^\s，,。.!！]+\s*(的)?\s*(管理员|admin|sudo|权限|角色)"), "Revoke role"),
        ("revoke_role", re.compile(r"(revoke|remove|demote)\s*(admin|sudo|role|permission)"), "Revoke role (EN)"),
        ("show_permissions", re.compile(r"(查看|显示|查询)\s*[^\s，,。.!！]*\s*权限"), "Show permissions"),
        ("show_permissions", re.compile(r"(show|check|get)\s*(permission|role)"), "Show permissions (EN)"),
        ("list_users", re.compile(r"(列出|查看|显示|查询)\s*(所有|全部)?\s*(用户|成员|账号)"), "List users"),
        ("list_users", re.compile(r"(list|show|get)\s*(all\s*)?(user|member)"), "List users (EN)"),
        ("show_self", re.compile(r"(我[^的]*什么|我的|查看我的)\s*(权限|角色|级别|身份)"), "Show own permissions"),
        ("show_self", re.compile(r"(my|what\s*are\s*my)\s*(permission|role|level)"), "Show own permissions (EN)"),
    ]

    # -- known app name patterns ---------------------------------------------

    # Extract app names from common patterns like "启动XX" "看看XX"
    APP_EXTRACT_PATTERNS: list[re.Pattern] = [
        re.compile(r"(启动|停止|暂停|恢复|查看|看看|修改|删除|删除|关闭|开启|关掉|打开|运行).{0,3}?([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})(的|这|个|一下|吗|吧|呗|！|!|\s|$)"),
        re.compile(r"把.([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})\s*(改成|改为|改成|设置成|设置|调整为|调整为)"),
        # Extract app name from "把 XXX 打开/关掉/启动/停止"
        re.compile(r"把\s*([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})\s*(打开|关掉|启动|停止|暂停|恢复|删除|运行|关闭)"),
        # Extract app name from create patterns like "帮我建一个XX App" "创建一个XX应用"
        re.compile(r"(?:帮我)?(?:创建|新建|建立|生成|做一个|搞一个|建)(?:一个|个)?.{0,3}?([\u4e00-\u9fa5a-zA-Z]{2,15})\s*(?:app|应用|程序|模块|工具)", re.IGNORECASE),
    ]

    # -- public API ----------------------------------------------------------

    def set_llm_responder(self, llm_responder: Any) -> None:
        """Set an optional LLM responder for fallback intent parsing.

        The responder must have a ``parse_intent(user_message, available_apps)``
        method that returns a dict (or None on failure).
        """
        self._llm_responder = llm_responder

    def set_tool_registry(self, tool_registry: ToolRegistry) -> None:
        """Set the tool registry for tool-aware intent parsing."""
        self._tool_registry = tool_registry

    def set_system_catalog(self, system_catalog: Any) -> None:
        """Set the static system catalog for asset-aware LLM parsing.
        
        The catalog provides installed-asset visibility and prompt context.
        Runtime liveness is intentionally tracked elsewhere.
        """
        self._system_catalog = system_catalog

    def set_runtime_context_provider(self, provider: Any) -> None:
        """Set an optional runtime context provider for LLM parsing.

        The provider should expose either `build_prompt(caller_id)` or be callable
        with `caller_id` and return a concise runtime summary string.
        """
        self._runtime_context_provider = provider

    @classmethod
    def clear_llm_cache(cls) -> None:
        """Clear the LLM parsing result cache. Useful for testing."""
        cls._llm_cache.clear()

    def interpret(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None = None,
        user_id: str = "system",
    ) -> InterpretedCommand:
        """Parse a user message into a structured command.

        Rule-based matching runs first (zero cost). If it returns "unclear"
        with low confidence (< 0.5) and an LLM responder is available, the
        LLM is consulted as a fallback.
        """
        stripped = message.strip()
        if not stripped:
            return self._empty_command()

        # 1. EXACT match check (always runs, zero cost)
        intent, confidence, matched_text = self._match_exact_intent(stripped)
        
        # If exact match found, return immediately (bypass LLM)
        if intent != "unclear":
            target_app = self._extract_app_name(stripped, available_apps)
            parameters = self._extract_parameters(stripped, intent)
            suggested_actions = self._build_actions(intent, target_app, available_apps)
            requires_clarification, clarification_question = self._needs_clarification(
                intent, target_app, parameters, session_key=user_id
            )
            return InterpretedCommand(
                intent=intent,
                confidence=confidence,
                target_app=target_app,
                parameters=parameters,
                requires_clarification=requires_clarification,
                clarification_question=clarification_question,
                suggested_actions=suggested_actions,
                raw_interpretation=f"exact-match: matched '{matched_text}' target='{target_app}'",
            )

        # 2. FUZZY match check (controlled by fuzzy_regex_match config)
        if self.fuzzy_regex_match:
            # Try fuzzy regex patterns
            intent, confidence, matched_text = self._match_fuzzy_intent(stripped)
            if intent != "unclear" and confidence >= 0.5:
                # Fuzzy match succeeded with decent confidence
                target_app = self._extract_app_name(stripped, available_apps)
                parameters = self._extract_parameters(stripped, intent)
                suggested_actions = self._build_actions(intent, target_app, available_apps)
                requires_clarification, clarification_question = self._needs_clarification(
                    intent, target_app, parameters, session_key=user_id
                )
                return InterpretedCommand(
                    intent=intent,
                    confidence=confidence,
                    target_app=target_app,
                    parameters=parameters,
                    requires_clarification=requires_clarification,
                    clarification_question=clarification_question,
                    suggested_actions=suggested_actions,
                    raw_interpretation=f"fuzzy-match: matched '{matched_text}' target='{target_app}'",
                )

        # 3. LLM fallback (default path when fuzzy_regex_match=False)
        if hasattr(self, "_llm_responder") and self._llm_responder is not None:
            llm_result, _ = self._try_llm_fallback(stripped, available_apps, user_id)
            if llm_result is not None:
                return llm_result

        # 4. Standard rule-based path (fallback if LLM unavailable)
        target_app = self._extract_app_name(stripped, available_apps)
        parameters = self._extract_parameters(stripped, intent)
        suggested_actions = self._build_actions(intent, target_app, available_apps)
        requires_clarification, clarification_question = self._needs_clarification(
            intent, target_app, parameters
        )

        return InterpretedCommand(
            intent=intent,
            confidence=confidence,
            target_app=target_app,
            parameters=parameters,
            requires_clarification=requires_clarification,
            clarification_question=clarification_question,
            suggested_actions=suggested_actions,
            raw_interpretation=f"rule-based: matched '{matched_text}' target='{target_app}'",
        )

    def _match_exact_intent(self, message: str) -> tuple[str, float, str]:
        """Return (intent, confidence, matched_pattern_desc) for EXACT matches only."""
        for intent, pattern, desc in self.EXACT_MATCH_PATTERNS:
            if pattern.search(message):
                return intent, 0.95, desc
        return "unclear", 0.1, "no exact match"

    def _match_fuzzy_intent(self, message: str) -> tuple[str, float, str]:
        """Return (intent, confidence, matched_pattern_desc) for FUZZY matches."""
        tool_match = self._match_tool_aware_intent(message)
        if tool_match is not None:
            return tool_match
        for intent, pattern, desc in self.FUZZY_MATCH_PATTERNS:
            if pattern.search(message):
                return intent, 0.75, desc
        return "unclear", 0.1, "no fuzzy match"

    def _match_tool_aware_intent(self, message: str) -> tuple[str, float, str] | None:
        registry = getattr(self, "_tool_registry", None)
        if registry is None:
            return None
        lowered = message.lower()
        asset_tools = {
            tool.name: tool
            for tool in registry.list_all()
            if getattr(tool, "category", "") == "asset"
        }
        if not asset_tools:
            return None

        if self._looks_like_asset_info_request(lowered) and "query_asset_info" in asset_tools:
            return "query_asset_info", 0.84, "tool-aware asset info"
        if self._looks_like_asset_list_request(lowered) and "list_assets" in asset_tools:
            return "list_assets", 0.88, "tool-aware asset discovery"
        if self._looks_like_asset_call_request(lowered) and "call_asset_method" in asset_tools:
            return "call_asset_method", 0.82, "tool-aware asset call"
        if self._looks_like_asset_detail_request(lowered) and "query_asset_detail" in asset_tools:
            return "query_asset_detail", 0.8, "tool-aware asset detail"
        return None

    def _looks_like_asset_list_request(self, lowered: str) -> bool:
        return any(k in lowered for k in ["资产", "服务", "能力", "runtime", "运行态"]) and any(
            k in lowered for k in ["有哪些", "有什么", "列出", "看看", "查看"]
        )

    def _looks_like_asset_info_request(self, lowered: str) -> bool:
        return any(k in lowered for k in ["资产", "服务"]) and any(
            k in lowered for k in ["详情", "信息", "能力", "配置", "契约"]
        )

    def _looks_like_asset_call_request(self, lowered: str) -> bool:
        return any(k in lowered for k in ["调用", "执行", "运行"]) and any(
            k in lowered for k in ["资产", "服务", "方法", "能力"]
        )

    def _looks_like_asset_detail_request(self, lowered: str) -> bool:
        return any(k in lowered for k in ["资产", "服务"]) and any(
            k in lowered for k in ["使用说明", "怎么用", "详细", "契约"]
        )

    def _match_intent(self, message: str) -> tuple[str, float, str]:
        """Return (intent, confidence, matched_pattern_desc)."""
        for intent, pattern, desc in self.INTENT_PATTERNS:
            if pattern.search(message):
                return intent, 0.85, desc
        # Fallback
        return "unclear", 0.1, "no pattern matched"

    def _extract_app_name(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None,
    ) -> str | None:
        """Try to extract an app name from the message."""
        # First try: match against known app names
        if available_apps:
            for app in available_apps:
                name = app.get("name", "")
                if name and name in message:
                    return name
                app_id = app.get("app_id", "")
                if app_id and app_id in message:
                    return name or app_id

        # Second try: regex extraction
        for pattern in self.APP_EXTRACT_PATTERNS:
            match = pattern.search(message)
            if match:
                name = None
                if match.lastindex is None:
                    continue
                # Pattern-specific group selection:
                # - "把 XXX 打开/关掉/启动/停止" patterns: group(1) = app name
                # - "动词...APP名..." patterns: group(2) = app name
                # - "建...XX App" patterns: group(1) = app name
                pat_str = pattern.pattern
                if pat_str.startswith(r'把\s*') or '打开|关掉' in pat_str or '建' in pat_str[:10]:
                    name = match.group(1)
                elif match.lastindex >= 2:
                    name = match.group(2)
                else:
                    name = match.group(1)
                return name.strip() if name else None

        return None

    def _extract_parameters(self, message: str, intent: str) -> dict[str, Any]:
        """Extract structured parameters from the message."""
        params: dict[str, Any] = {}
        runtime_context = self._consume_runtime_clarification(message)
        if runtime_context:
            return runtime_context

        if intent == "create_app":
            # Look for common app types
            app_types = {
                "监控": "monitor", "日报": "daily_report", "提醒": "reminder",
                "翻译": "translator", "爬虫": "crawler", "定时": "scheduled",
                "通知": "notification", "记录": "logger", "工具": "utility",
                "小说": "novel", "日记": "diary", "博客": "blog", "音乐": "music",
                "周报": "weekly_report", "笔记": "notes", "任务": "task",
                "项目": "project", "聊天": "chat", "绘图": "drawing",
            }
            for cn, en in app_types.items():
                if cn in message:
                    params["app_type"] = en
                    break

            # Extract app name from message pattern like "帮我建一个XX App"
            name_match = re.search(r"(?:帮我)?(?:创建|新建|建立|生成|做一个|搞一个|建)(?:一个|个)?.{0,3}?([\u4e00-\u9fa5a-zA-Z]{2,15})\s*(?:app|应用|程序|模块|工具)", message, re.IGNORECASE)
            if name_match:
                app_name_cn = name_match.group(1).strip()
                params["app_name_display"] = app_name_cn

            # Look for time/frequency mentions
            if "每小时" in message or "每小" in message:
                params["schedule_type"] = "interval"
                params["schedule_interval"] = 3600
            elif "每天" in message:
                params["schedule_type"] = "cron"
                params["schedule_cron"] = "0 0 * * *"
            elif "每分钟" in message:
                params["schedule_type"] = "interval"
                params["schedule_interval"] = 60

            # Look for threshold mentions
            threshold_match = re.search(r"(\d+)\s*%", message)
            if threshold_match:
                params["threshold"] = int(threshold_match.group(1))

        elif intent == "call_asset_method":
            method_match = re.search(r"(?:方法|能力)\s*([a-zA-Z_][a-zA-Z0-9_]*)", message)
            asset_match = re.search(r"asset[:：][^\s，,。]+", message, re.IGNORECASE)
            trailing_method_phrase = re.search(r"(?:方法|能力)\s*$", message)
            if method_match:
                params["method"] = method_match.group(1)
            elif trailing_method_phrase:
                params["missing_method_name"] = True
            if asset_match:
                params["asset_id"] = asset_match.group(0).replace("：", ":")

        elif intent in ("query_asset_info", "query_asset_detail"):
            asset_match = re.search(r"asset[:：][^\s，,。]+", message, re.IGNORECASE)
            if asset_match:
                params["asset_id"] = asset_match.group(0).replace("：", ":")

        return params

    def _build_actions(
        self,
        intent: str,
        target_app: str | None,
        available_apps: list[dict[str, Any]] | None,
    ) -> list[ActionSuggestion]:
        """Build context-appropriate action suggestions."""
        actions: list[ActionSuggestion] = []

        if intent == "create_app":
            actions = [
                ActionSuggestion(
                    id="confirm_create", label="✅ 确认创建", action_type="confirm",
                    payload={
                        "intent": "create_app",
                        "target_app": target_app,
                        "parameters": {"app_type": intent.replace("_app", "") if intent else "unknown"},
                        "confirmed": True,
                    }, style="primary",
                ),
                ActionSuggestion(
                    id="modify_config", label="✏️ 修改配置", action_type="modify",
                    payload={"intent": "modify_before_create"}, style="secondary",
                ),
                ActionSuggestion(
                    id="cancel", label="❌ 取消", action_type="cancel",
                    payload={"intent": "cancel"}, style="ghost",
                ),
            ]
        elif intent in ("start_app", "stop_app", "pause_app", "resume_app", "delete_app"):
            actions = [
                ActionSuggestion(
                    id="confirm_action", label="✅ 确认", action_type="confirm",
                    payload={"intent": intent, "target": target_app, "confirmed": True}, style="primary",
                ),
                ActionSuggestion(
                    id="cancel", label="❌ 取消", action_type="cancel",
                    payload={"intent": "cancel"}, style="ghost",
                ),
            ]
        elif intent == "list_apps":
            actions = [
                ActionSuggestion(
                    id="create_new", label="➕ 新建 App", action_type="navigate",
                    payload={"intent": "create_app"}, style="primary",
                ),
                ActionSuggestion(
                    id="query_help", label="❓ 帮助", action_type="navigate",
                    payload={"intent": "query_help"}, style="secondary",
                ),
            ]
        elif intent == "greet":
            actions = [
                ActionSuggestion(
                    id="list_apps", label="📱 查看我的 App", action_type="navigate",
                    payload={"intent": "list_apps"}, style="primary",
                ),
                ActionSuggestion(
                    id="create_app", label="➕ 创建新 App", action_type="navigate",
                    payload={"intent": "create_app"}, style="secondary",
                ),
                ActionSuggestion(
                    id="query_status", label="📊 系统状态", action_type="navigate",
                    payload={"intent": "query_status"}, style="secondary",
                ),
            ]

        return actions

    def _needs_clarification(
        self,
        intent: str,
        target_app: str | None,
        parameters: dict[str, Any],
        session_key: str = "default",
    ) -> tuple[bool, str | None]:
        """Determine if we need to ask the user for clarification."""
        if intent == "unclear":
            return True, "我没太理解你的意思，能再说具体一点吗？比如：\n- 创建一个新的 App\n- 查看已有的 App\n- 启动或停止某个 App"

        if intent == "create_app" and not parameters.get("app_type"):
            return True, "你想创建什么类型的 App？比如：\n- 监控 App（定时检查某项指标）\n- 日报 App（每天生成汇总报告）\n- 提醒 App（到时间通知你）\n- 翻译 App（文本翻译工具）"

        if intent in ("start_app", "stop_app", "pause_app", "resume_app", "delete_app", "modify_app") and not target_app:
            return True, "你想操作哪个 App？请告诉我 App 的名称。"

        if intent in ("query_asset_info", "query_asset_detail") and not parameters.get("asset_id"):
            return True, "你想查看哪个运行态资产？请给我 asset_id，例如 asset:runtime_center:v1。"

        if intent == "call_asset_method":
            if not parameters.get("asset_id") and not parameters.get("method"):
                self._pending_runtime_asset_clarifications.pop(session_key, None)
                return True, "你想调用哪个资产的哪个方法？请给我 asset_id 和 method，例如 asset:model_router:v1 的 resolve_model。"
            if parameters.get("asset_id") and not parameters.get("method"):
                self._pending_runtime_asset_clarifications[session_key] = {
                    "intent": intent,
                    "parameters": {"asset_id": parameters.get("asset_id")},
                }
                return True, "我知道你要调用哪个资产了，但还缺方法名。请告诉我要调用的 method。"
            if parameters.get("method") and not parameters.get("asset_id"):
                self._pending_runtime_asset_clarifications[session_key] = {
                    "intent": intent,
                    "parameters": {"method": parameters.get("method")},
                }
                return True, "我知道你要调用哪个方法了，但还缺 asset_id。请告诉我要调用哪个资产。"
            self._pending_runtime_asset_clarifications.pop(session_key, None)

        return False, None

    def _consume_runtime_clarification(self, message: str) -> dict[str, Any] | None:
        pending = self._pending_runtime_asset_clarifications.get("default")
        if not pending:
            return None
        merged = dict(pending.get("parameters", {}))
        asset_match = re.search(r"asset[:：][^\s，,。]+", message, re.IGNORECASE)
        method_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)", message)
        if not merged.get("asset_id") and asset_match:
            merged["asset_id"] = asset_match.group(0).replace("：", ":")
        if not merged.get("method") and method_match:
            merged["method"] = method_match.group(1)
        if merged.get("asset_id") and merged.get("method"):
            self._pending_runtime_asset_clarifications.pop("default", None)
            return merged
        return None

    # -- LLM fallback --------------------------------------------------------

    def _cache_key(self, message: str, available_apps: list[dict[str, Any]] | None) -> str:
        """Generate a deterministic cache key for a message + app context."""
        h = hashlib.md5(message.encode("utf-8")).hexdigest()[:12]
        if available_apps:
            app_names = ",".join(sorted(a.get("name", "") for a in available_apps))
            h += ":" + hashlib.md5(app_names.encode("utf-8")).hexdigest()[:8]
        return h

    def _try_llm_fallback(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None,
        user_id: str = "system",
    ) -> tuple[InterpretedCommand | None, Any | None]:
        """Try LLM intent parsing. Returns (command, usage) tuple."""
        # Check cache first
        cache_key = self._cache_key(message, available_apps)
        if cache_key in self._llm_cache:
            cached = self._llm_cache[cache_key].model_copy()
            cached.raw_interpretation = f"llm-cache: cached result for '{message[:50]}'"
            return cached, None

        result, usage = self._interpret_with_llm(message, available_apps, user_id)
        if result is not None:
            # Cache the result
            self._llm_cache[cache_key] = result
            return result, usage
        return None, usage

    def _interpret_with_llm(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None,
        user_id: str = "system",
    ) -> tuple[InterpretedCommand | None, TokenUsage | None]:
        """Ask the LLM responder to parse intent from the message.

        Returns (command, usage) tuple. Command is None on any failure.
        """
        if not hasattr(self, "_llm_responder") or self._llm_responder is None:
            return None, None

        # Phase E.3: Tool-aware LLM parsing with asset catalog
        if hasattr(self, '_system_catalog') and self._system_catalog is not None:
            # Build static asset overview prompt for LLM
            caller_id = f"user.{user_id}" if user_id != "system" else "system"
            asset_prompt = self._system_catalog.build_llm_prompt(caller_id)
            runtime_prompt = ""
            provider = getattr(self, '_runtime_context_provider', None)
            if provider is not None:
                try:
                    if hasattr(provider, 'build_prompt'):
                        runtime_prompt = provider.build_prompt(caller_id)
                    elif callable(provider):
                        runtime_prompt = provider(caller_id)
                except Exception:
                    runtime_prompt = ""
            if runtime_prompt:
                asset_prompt = f"{asset_prompt}\n\n## 运行中实例概览\n{runtime_prompt}"

            # Use tool-aware parsing with asset context
            if hasattr(self._llm_responder, 'parse_intent_with_tools'):
                if hasattr(self, '_tool_registry') and self._tool_registry is not None:
                    parsed, usage = self._llm_responder.parse_intent_with_tools(
                        message, self._tool_registry, available_apps,
                        asset_context=asset_prompt,
                    )
                else:
                    parsed, usage = self._llm_responder.parse_intent_with_tools(
                        message, None, available_apps,
                        asset_context=asset_prompt,
                    )
            else:
                parsed, usage = self._llm_responder.parse_intent(
                    message, available_apps, asset_context=asset_prompt,
                )
        elif hasattr(self, '_tool_registry') and self._tool_registry is not None:
            # Use tool-aware parsing with registry context
            parsed, usage = self._llm_responder.parse_intent_with_tools(
                message, self._tool_registry, available_apps
            ) if hasattr(self._llm_responder, 'parse_intent_with_tools') else self._llm_responder.parse_intent(message, available_apps)
        else:
            parsed, usage = self._llm_responder.parse_intent(message, available_apps)
        if not parsed or not isinstance(parsed, dict):
            return None, usage

        # Extract and validate fields
        intent = parsed.get("intent", "unclear")
        if intent not in self.VALID_INTENTS:
            intent = "unclear"

        confidence = parsed.get("confidence", 0.3)
        if not isinstance(confidence, (int, float)):
            confidence = 0.3
        confidence = max(0.0, min(1.0, float(confidence)))

        target_app = parsed.get("target_app")
        if target_app is not None and not isinstance(target_app, str):
            target_app = str(target_app)

        parameters = parsed.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}

        requires_clarification = bool(parsed.get("requires_clarification", False))
        clarification_question = parsed.get("clarification_question")
        if clarification_question is not None and not isinstance(clarification_question, str):
            clarification_question = str(clarification_question)

        # Build suggested actions from the LLM-derived intent
        suggested_actions = self._build_actions(intent, target_app, available_apps)

        return InterpretedCommand(
            intent=intent,
            confidence=confidence,
            target_app=target_app,
            parameters=parameters,
            requires_clarification=requires_clarification,
            clarification_question=clarification_question,
            suggested_actions=suggested_actions,
            raw_interpretation=f"llm: parsed intent='{intent}' confidence={confidence:.2f}",
        ), usage

    # -- private helpers -----------------------------------------------------

    def _empty_command(self) -> InterpretedCommand:
        return InterpretedCommand(
            intent="unclear",
            confidence=0.0,
            requires_clarification=True,
            clarification_question="请输入你的指令，比如：\n- '帮我建一个监控 App'\n- '看看我的 App 列表'\n- '启动服务器监控'",
            suggested_actions=[
                ActionSuggestion(
                    id="query_help", label="❓ 帮助", action_type="navigate",
                    payload={"intent": "query_help"}, style="secondary",
                ),
            ],
            raw_interpretation="empty message",
        )
