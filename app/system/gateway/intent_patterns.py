"""Intent Match Patterns — 意图识别规则定义。

从 LightBrainInterpreter 抽离的**规则数据**（正则模式），与匹配逻辑分离：
- 新增意图只需在此模块添加规则，无需改动解释器逻辑（符合可扩展原则）。
- 所有模式为类级常量，供 LightBrainInterpreter 绑定为类属性引用。

设计原则（2026-08-16）：**关键词匹配全量移除，仅保留全匹配命中（EXACT）**。
- EXACT_MATCH_PATTERNS：无歧义的完整匹配（纯问候/帮助/状态查询），零成本直通。
- 其余意图一律走 LLM 意图解析，不再使用模糊关键词匹配（FUZZY 层已删除）。
"""
from __future__ import annotations

import re
from typing import Pattern


# ---- EXACT MATCH PATTERNS (always bypass LLM, zero cost) ----
# These are 100% unambiguous — pure greetings, help requests, status queries
EXACT_MATCH_PATTERNS: list[tuple[str, Pattern, str]] = [
    ("greet", re.compile(r"^(你好|嗨|hi|hello|hey|哈喽)$", re.IGNORECASE), "Pure greeting"),
    ("query_help", re.compile(r"^(帮助|help|教教我|怎么用)$", re.IGNORECASE), "Pure help request"),
    ("query_status", re.compile(r"^(系统状态|状态|运行情况)$", re.IGNORECASE), "Pure status query"),
]

# -- known app name patterns ---------------------------------------------

# Extract app names from common patterns like "启动XX" "看看XX"
APP_EXTRACT_PATTERNS: list[Pattern] = [
    re.compile(r"(启动|停止|暂停|恢复|查看|看看|修改|删除|删除|关闭|开启|关掉|打开|运行).{0,3}?([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})(的|这|个|一下|吗|吧|呗|！|!|\s|$)"),
    re.compile(r"把.([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})\s*(改成|改为|改成|设置成|设置|调整为|调整为)"),
    # Extract app name from "把 XXX 打开/关掉/启动/停止"
    re.compile(r"把\s*([\u4e00-\u9fa5a-zA-Z0-9_\-]{2,20})\s*(打开|关掉|启动|停止|暂停|恢复|删除|运行|关闭)"),
    # Extract app name from create patterns like "帮我建一个XX App" "创建一个XX应用"
    re.compile(r"(?:帮我)?(?:创建|新建|建立|生成|做一个|搞一个|建)(?:一个|个)?.{0,3}?([\u4e00-\u9fa5a-zA-Z]{2,15})\s*(?:app|应用|程序|模块|工具)", re.IGNORECASE),
]
