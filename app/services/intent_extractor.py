"""IntentExtractor — 意图提取层。

用户消息先走一次 LLM 调用 + 结构化输出（JSON mode），
明确意图/参数/模式/授权信号，再路由到执行层。

不调工具，不做多轮，只做理解。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.models.intent import AuthorizationSignal, ExtractedIntent

logger = logging.getLogger(__name__)

# 意图提取 prompt — 也是第一个独立 prompt 文件的原型
EXTRACTION_PROMPT = """你是一个意图提取器。将用户消息结构化为标准意图。

输出严格的 JSON，不要额外文本。

{
  "action": "用户的核心操作意图 (create/modify/query/delete/start/stop/chat/...）",
  "target": "操作目标对象（app 名、配置名、功能名等）",
  "parameters": {"参数名": "参数值"},
  "task_mode": "chat | execution | engineering | background",
  "is_engineering": false,
  "needs_background": false,
  "implied_authorization": "none | implied_modify | implied_restart | implied_background | explicit_full",
  "confidence": 0.95,
  "reasoning": "简要推理过程"
}

判断规则：
- "帮我改xxx" "修改xxx" "改配置" "改代码" "修改系统" → is_engineering=true
- "你继续" "后台跑" "不要停" "断线续跑" → needs_background=true
- "你可以改" "允许修改" "你改吧" "帮我改" → implied_authorization=implied_modify
- "重启吧" "试一下" → implied_authorization=implied_restart
- "你继续" "你跑着" "后台执行" → implied_authorization=implied_background
- "全部授权给你" "你可以做任何修改" → implied_authorization=explicit_full
- 纯聊天/问候/状态查询 → task_mode=chat, is_engineering=false
"""


class IntentExtractor:
    """意图提取层。

    用法:
        extractor = IntentExtractor(model_router)
        intent = extractor.extract("帮我改一下监控配置")
        print(intent.action)  # "modify"
        print(intent.is_engineering)  # True
    """

    def __init__(self, model_router=None):
        self._router = model_router
        self._extraction_prompt = EXTRACTION_PROMPT

    def extract(
        self,
        message: str,
        context: dict | None = None,
    ) -> ExtractedIntent:
        """提取用户意图。

        单次 LLM 调用，JSON 结构化输出。
        """
        if not message or not message.strip():
            return ExtractedIntent(
                action="chat", task_mode="chat", confidence=1.0,
                raw_user_message=message or "",
            )

        # 尝试 LLM 提取
        if self._router:
            try:
                result = self._llm_extract(message, context)
                result.raw_user_message = message
                return result
            except Exception as e:
                logger.warning("IntentExtractor LLM call failed: %s", e)

        # fallback：简单关键词匹配
        return self._fallback_extract(message)

    def _llm_extract(
        self,
        message: str,
        context: dict | None = None,
    ) -> ExtractedIntent:
        """通过 LLM 结构化提取。"""
        client = self._router.get_client("intent_extractor")

        # 构建带上下文的 prompt
        context_hint = ""
        if context:
            session_info = {k: v for k, v in context.items() if k in ("session_id",)}
            if session_info:
                context_hint = f"\n当前上下文: {json.dumps(session_info, ensure_ascii=False)}"

        prompt = self._extraction_prompt + context_hint

        # 调用 LLM
        raw = client.chat(
            system_prompt=prompt,
            user_message=message,
            max_tokens=512,
            temperature=0.1,
        )

        text = raw.get("content", "") if isinstance(raw, dict) else str(raw)
        return self._parse_response(text, message)

    def _parse_response(
        self,
        text: str,
        raw_message: str,
    ) -> ExtractedIntent:
        """解析 LLM 返回的 JSON。"""
        # 提取 JSON（清理可能的 markdown 包裹）
        text = text.strip()
        if text.startswith("```"):
            # 去除 ```json ``` 包裹
            text = text.split("\n", 1)[-1]
            text = text.rsplit("\n```", 1)[0] if "```" in text else text

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("IntentExtractor: failed to parse LLM response: %s", text[:200])
            return self._fallback_extract(raw_message)

        # 构建 Intent
        auth_signal = AuthorizationSignal.NONE
        auth_str = data.get("implied_authorization", "none")
        try:
            auth_signal = AuthorizationSignal(auth_str)
        except ValueError:
            pass

        return ExtractedIntent(
            action=data.get("action", "chat"),
            target=data.get("target"),
            parameters=data.get("parameters", {}),
            task_mode=data.get("task_mode", "chat"),
            is_engineering=data.get("is_engineering", False),
            needs_background=data.get("needs_background", False),
            implied_authorization=auth_signal,
            confidence=data.get("confidence", 0.5),
            reasoning=data.get("reasoning", ""),
            raw_user_message=raw_message,
        )

    def _fallback_extract(self, message: str) -> ExtractedIntent:
        """基于关键词的 fallback 提取。

        注意：这是纯关键词匹配，用于无 LLM 时的兜底。
        LLM 提取会更准确。关键词策略：
        - 优先匹配长词组（避免单字误伤）
        - 授权信号和工程信号各自独立判断
        - "你可以改"→授权，而非工程
        """
        text = message.lower().strip()
        if not text:
            return ExtractedIntent(
                action="chat", task_mode="chat", confidence=1.0,
                reasoning="empty message fallback",
                raw_user_message=message,
            )

        # ─── 1. 授权信号（优先长词组匹配，避免单字误伤）───
        auth = AuthorizationSignal.NONE
        if any(kw in text for kw in (
            "全部授权给你", "你可以做任何修改", "完全授权给你",
            "你做任何修改", "全部授权", "完全授权",
        )):
            auth = AuthorizationSignal.EXPLICIT_FULL
        elif any(kw in text for kw in (
            "你继续跑", "你后台跑", "你后台继续", "后台跑一下",
            "你跑着", "断线续跑", "跑完了告诉我",
        )):
            auth = AuthorizationSignal.IMPLIED_BACKGROUND
        elif any(kw in text for kw in ("重启吧", "重启试试", "试一下")):
            auth = AuthorizationSignal.IMPLIED_RESTART
        elif any(kw in text for kw in (
            "你可以改", "允许修改", "你改吧", "你直接改",
            "你可以做", "你看着办",
        )):
            auth = AuthorizationSignal.IMPLIED_MODIFY
        elif "帮我改" in text:
            # "帮我改xxx" → 同时有授权信号 + 工程意图
            auth = AuthorizationSignal.IMPLIED_MODIFY

        # ─── 2. 是否工程任务 ───
        # 注意：不要在纯粹的授权语句中触发工程模式
        # "你可以改" / "你改吧" → 是授权，不是改代码
        pure_authorization = auth != AuthorizationSignal.NONE and not any(kw in text for kw in (
            "帮我改", "帮我优化", "帮我重构", "帮我升级",
            "帮我部署", "帮我安装", "帮我查", "帮我排查",
            "去改", "去修改", "去优化", "去重构",
            "改成", "改为", "改一下", "改改",
        ))

        if pure_authorization:
            is_eng = False
        else:
            is_eng = any(kw in text for kw in (
                "改", "修改", "配置", "代码", "重构", "优化", "升级",
                "部署", "安装", "调试", "排查", "诊断", "重构",
                "迁移", "脚本", "重写",
            ))

        # ─── 3. 是否后台任务 ───
        needs_bg = any(kw in text for kw in (
            "后台", "继续", "持续", "挂着", "跑着", "跑一下",
            "轮询", "定时", "每隔",
        ))

        # ─── 4. 任务模式 ───
        mode = "chat"
        if needs_bg:
            mode = "background"
        elif is_eng:
            mode = "engineering"

        # ─── 5. 操作类型 ───
        action = "chat"

        # 检测排除：纯授权语句通常不是操作指令
        if pure_authorization and not any(kw in text for kw in ("去", "把", "将", "帮我")):
            action = "chat"
        else:
            if any(kw in text for kw in ("创建", "新建", "生成", "做一个", "帮我做一个", "新建一个", "创建一个")):
                action = "create"
            elif any(kw in text for kw in ("修改", "改一下", "改改", "编辑", "更新", "调整", "改了", "改为", "改成")):
                action = "modify"
            elif any(kw in text for kw in ("重构", "重写", "重做")):
                action = "modify"
            elif any(kw in text for kw in ("优化", "升级", "部署", "安装")):
                action = "modify"
            elif any(kw in text for kw in ("删除", "删掉", "移除", "清空", "清除")):
                action = "delete"
            elif any(kw in text for kw in (
                "启动", "开启", "运行", "打开", "重启",
                "跑一下", "跑", "部署",
            )):
                action = "start"
            elif any(kw in text for kw in ("停止", "关闭", "关掉", "暂停", "停下")):
                action = "stop"
            elif any(kw in text for kw in (
                "查询", "查看", "状态", "看看", "检查",
                "查一下", "查查", "查",
                "搜索", "搜", "找一下", "找",
                "天气", "几点了", "什么",
            )):
                action = "query"

        return ExtractedIntent(
            action=action,
            task_mode=mode,
            is_engineering=is_eng,
            needs_background=needs_bg,
            implied_authorization=auth,
            confidence=0.6 if action != "chat" else 0.8,
            reasoning="keyword fallback",
            raw_user_message=message,
        )
