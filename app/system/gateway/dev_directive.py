"""开发指令识别（P0-2 意图区分）。

开发指令 = 引导系统用工具读写代码库的元指令（read_file / exec_shell /
write_file / edit_file 等），不是用户对 App 的操作请求。

orchestrator（interaction_orchestrator）与 interpreter（light_brain_interpreter）
共用此判定：命中开发指令时，两层都应放行到 LLM 工具链，避免宽泛的
资产路由关键词 / App 生命周期意图正则把开发指令误判成资产操作或
App 创建/查询/修改等操作。
"""

from __future__ import annotations

# 开发指令元标记：命中任一即视为开发指令
_DEV_DIRECTIVE_MARKERS = (
    "read_file", "exec_shell", "write_file", "edit_file",
    "代码开发任务", "开发执行助手", "开发任务",
    "用工具读取", "用工具写", "使用工具",
    "使用 read_file", "使用 exec_shell", "使用 write_file", "使用 edit_file",
    "读写代码库", "操作代码库", "写代码",
)


def is_dev_directive(message: str) -> bool:
    """检测消息是否为『引导系统用工具读写代码库』的开发指令元指令。"""
    low = (message or "").lower()
    return any(m in low for m in _DEV_DIRECTIVE_MARKERS)
