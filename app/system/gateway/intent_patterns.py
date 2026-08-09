"""Intent Match Patterns — 意图识别规则定义。

从 LightBrainInterpreter 抽离的**规则数据**（正则模式），与匹配逻辑分离：
- 新增意图只需在此模块添加规则，无需改动解释器逻辑（符合可扩展原则）。
- 所有模式为类级常量，供 LightBrainInterpreter 绑定为类属性引用。
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

# ---- FUZZY MATCH PATTERNS (routed through LLM when fuzzy_regex_match=False) ----
# All other intents are fuzzy-matched via regex; LLM fallback is available when confidence is low.
FUZZY_MATCH_PATTERNS: list[tuple[str, Pattern, str]] = [
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
    ("call_asset_method", re.compile(r"(调用|执行|运行).*(资产|服务).*(方法|能力)", re.IGNORECASE), "Call runtime asset method"),
    ("call_asset_method", re.compile(r"调用\s*资产[^\n]*方法\s*$", re.IGNORECASE), "Call runtime asset method missing method name"),
    ("call_asset_method", re.compile(r"调用\s*资产[^\n]*的方法\s*[a-zA-Z_][a-zA-Z0-9_]*", re.IGNORECASE), "Call runtime asset method missing asset id or partial call"),
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
