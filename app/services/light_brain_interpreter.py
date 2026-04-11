"""LightBrain Interpreter — rule-based intent parsing with optional LLM fallback.

Translates natural language user messages into structured InterpretedCommand objects.
Phase 8.1 uses keyword/pattern matching; Phase 8.3 adds LLM-based parsing fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.models.chat import ActionSuggestion, InterpretedCommand


class LightBrainInterpreter:
    """Rule-based interpreter that maps user messages to structured commands.

    Phase 8.3: optionally falls back to LLM parsing when rule-based confidence
    is low (returns 'unclear' with confidence < 0.5). Results are cached so
    identical messages don't trigger repeated LLM calls.
    """

    # Valid intent values the LLM may return
    VALID_INTENTS = {
        "greet", "list_apps", "create_app", "start_app", "stop_app",
        "pause_app", "resume_app", "query_app", "modify_app", "delete_app",
        "query_status", "query_help", "unclear",
    }

    # LLM intent parsing result cache: key -> InterpretedCommand
    _llm_cache: dict[str, InterpretedCommand] = {}

    # -- intent patterns -----------------------------------------------------

    INTENT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
        # (intent_name, compiled_regex, description)
        ("create_app", re.compile(r"(创建|新建|建|建立|生成|做一个|搞一个).*(app|应用|程序|模块)", re.IGNORECASE), "Create a new app"),
        ("create_app", re.compile(r"(帮我|给我|我要).*(创建|新建|建|建立).*(监控|日报|提醒|翻译|爬虫|定时|通知|记录|工具)", re.IGNORECASE), "Create app by action type"),
        ("start_app", re.compile(r"(启动|开启|运行|开始|打开|激活).*(app|应用|程序|监控|日报|提醒|翻译|服务)", re.IGNORECASE), "Start an app"),
        ("start_app", re.compile(r"(启动|开启|恢复|继续)", re.IGNORECASE), "Start/resume"),
        ("stop_app", re.compile(r"(停止|关闭|关掉|暂停|停掉|终止).*(app|应用|程序|监控|日报|提醒|服务)", re.IGNORECASE), "Stop an app"),
        ("pause_app", re.compile(r"(暂停|挂起)", re.IGNORECASE), "Pause an app"),
        ("resume_app", re.compile(r"(恢复|继续|恢复运行)", re.IGNORECASE), "Resume an app"),
        ("modify_app", re.compile(r"(修改|更改|更新|调整|改一下|编辑|配置).*(app|应用|程序|设置|配置)", re.IGNORECASE), "Modify an app"),
        ("modify_app", re.compile(r"把.+改成|把.+改为|把.+调整为"), "Modify app (把...改成)"),
        ("delete_app", re.compile(r"(删除|删掉|移除|干掉|销毁).*(app|应用|程序)", re.IGNORECASE), "Delete an app"),
        ("query_app", re.compile(r"(查看|查询|状态|详情|信息).*(app|应用|程序)", re.IGNORECASE), "Query app status"),
        ("query_app", re.compile(r".*(异常|问题|错误|告警|报告|完成).*(今天|最近|今天有|今天发现)", re.IGNORECASE), "Query app results"),
        ("list_apps", re.compile(r"(列出|看看|有哪些|列表|我的).*(app|应用|程序|在跑|运行)", re.IGNORECASE), "List apps"),
        ("list_apps", re.compile(r"^.*(app|应用|程序).*(列表|有哪些|几个)", re.IGNORECASE), "List apps alt"),
        ("query_status", re.compile(r"(系统状态|状态|健康|运行情况|运行正常|整体情况|概况)", re.IGNORECASE), "System status query"),
        ("query_help", re.compile(r"(帮助|help|怎么用|如何使用|能做什么|功能|说明)", re.IGNORECASE), "Help query"),
        ("greet", re.compile(r"^(你好|嗨|hi|hello|hey|哈喽|早上好|下午好|晚上好|早上好|下午好|晚上好)", re.IGNORECASE), "Greeting"),
    ]

    # -- known app name patterns ---------------------------------------------

    # Extract app names from common patterns like "启动XX" "看看XX"
    APP_EXTRACT_PATTERNS: list[re.Pattern] = [
        re.compile(r"(启动|停止|暂停|恢复|查看|看看|修改|删除|删除|关闭|开启).{0,3}?([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})(的|这|个|一下|吗|吧|呗|！|!|\s|$)"),
        re.compile(r"把.([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})\s*(改成|改为|改成|设置成|设置|调整为|调整为)"),
    ]

    # -- public API ----------------------------------------------------------

    def set_llm_responder(self, llm_responder: Any) -> None:
        """Set an optional LLM responder for fallback intent parsing.

        The responder must have a ``parse_intent(user_message, available_apps)``
        method that returns a dict (or None on failure).
        """
        self._llm_responder = llm_responder

    @classmethod
    def clear_llm_cache(cls) -> None:
        """Clear the LLM parsing result cache. Useful for testing."""
        cls._llm_cache.clear()

    def interpret(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None = None,
    ) -> InterpretedCommand:
        """Parse a user message into a structured command.

        Rule-based matching runs first (zero cost). If it returns "unclear"
        with low confidence (< 0.5) and an LLM responder is available, the
        LLM is consulted as a fallback.
        """
        stripped = message.strip()
        if not stripped:
            return self._empty_command()

        # 1. Rule-based intent matching (always runs first)
        intent, confidence, matched_text = self._match_intent(stripped)

        # 2. Check if we should fall back to LLM
        if (
            intent == "unclear"
            and confidence < 0.5
            and hasattr(self, "_llm_responder")
            and self._llm_responder is not None
        ):
            llm_result, _ = self._try_llm_fallback(stripped, available_apps)
            if llm_result is not None:
                return llm_result

        # 3. Standard rule-based path
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
                return match.group(2).strip()

        return None

    def _extract_parameters(self, message: str, intent: str) -> dict[str, Any]:
        """Extract structured parameters from the message."""
        params: dict[str, Any] = {}

        if intent == "create_app":
            # Look for common app types
            app_types = {
                "监控": "monitor", "日报": "daily_report", "提醒": "reminder",
                "翻译": "translator", "爬虫": "crawler", "定时": "scheduled",
                "通知": "notification", "记录": "logger", "工具": "utility",
            }
            for cn, en in app_types.items():
                if cn in message:
                    params["app_type"] = en
                    break

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

        elif intent == "modify_app":
            # Extract what to modify
            if "改成" in message or "改为" in message or "调整为" in message:
                modify_match = re.search(r"(改成|改为|调整为|设置成)(.+)", message)
                if modify_match:
                    params["modification"] = modify_match.group(2).strip()

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
                    payload={"intent": "create_app", "confirmed": True}, style="primary",
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
    ) -> tuple[bool, str | None]:
        """Determine if we need to ask the user for clarification."""
        if intent == "unclear":
            return True, "我没太理解你的意思，能再说具体一点吗？比如：\n- 创建一个新的 App\n- 查看已有的 App\n- 启动或停止某个 App"

        if intent == "create_app" and not parameters.get("app_type"):
            return True, "你想创建什么类型的 App？比如：\n- 监控 App（定时检查某项指标）\n- 日报 App（每天生成汇总报告）\n- 提醒 App（到时间通知你）\n- 翻译 App（文本翻译工具）"

        if intent in ("start_app", "stop_app", "pause_app", "resume_app", "delete_app", "modify_app") and not target_app:
            return True, "你想操作哪个 App？请告诉我 App 的名称。"

        return False, None

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
    ) -> tuple[InterpretedCommand | None, Any | None]:
        """Try LLM intent parsing. Returns (command, usage) tuple."""
        # Check cache first
        cache_key = self._cache_key(message, available_apps)
        if cache_key in self._llm_cache:
            cached = self._llm_cache[cache_key].model_copy()
            cached.raw_interpretation = f"llm-cache: cached result for '{message[:50]}'"
            return cached, None

        result, usage = self._interpret_with_llm(message, available_apps)
        if result is not None:
            # Cache the result
            self._llm_cache[cache_key] = result
            return result, usage
        return None, usage

    def _interpret_with_llm(
        self,
        message: str,
        available_apps: list[dict[str, Any]] | None,
    ) -> tuple[InterpretedCommand | None, TokenUsage | None]:
        """Ask the LLM responder to parse intent from the message.

        Returns (command, usage) tuple. Command is None on any failure.
        """
        if not hasattr(self, "_llm_responder") or self._llm_responder is None:
            return None, None

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
