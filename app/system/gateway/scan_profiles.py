from __future__ import annotations

from typing import Any


SCAN_PROFILES: list[dict[str, Any]] = [
    {
        "name": "persistence",
        "triggers": ["persistence", "persist", "持久化", "存储"],
        "regex": r"(persistence|persist|sqlite|json|mysql|postgres|storage|backend)",
        "summary_focus": "存储后端、序列化格式、写入路径、是否出现数据库或文件系统持久化迹象",
        "output_template": "按 4 段输出: 1) 存储后端/介质 2) 序列化或数据格式 3) 写入/读取路径与方法 4) 未发现与未证实点",
    },
    {
        "name": "router",
        "triggers": ["router", "route", "路由", "接口"],
        "regex": r"(router|route|endpoint|api|path|fastapi|flask)",
        "summary_focus": "接口定义、路径注册、路由装饰器、endpoint/path 相关实现",
        "output_template": "按 4 段输出: 1) 路由/接口文件 2) 路径或装饰器证据 3) endpoint/handler 线索 4) 未发现与未证实点",
    },
    {
        "name": "config",
        "triggers": ["config", "配置", "env", "环境变量", "yaml"],
        "regex": r"(config|setting|env|yaml|yml|toml|ini|os\.getenv)",
        "summary_focus": "配置来源、默认值、环境变量覆盖、配置文件格式与加载位置",
        "output_template": "按 4 段输出: 1) 配置来源 2) 默认值/覆盖机制 3) 配置文件或环境变量位置 4) 未证实点",
    },
    {
        "name": "schema",
        "triggers": ["schema", "model", "字段", "表结构", "数据模型"],
        "regex": r"(schema|model|field|column|pydantic|basemodel|dataclass)",
        "summary_focus": "数据模型、字段定义、schema 结构、类型声明与默认值线索",
        "output_template": "按 4 段输出: 1) 模型/实体 2) 字段与默认值 3) 序列化/schema 线索 4) 未证实点",
    },
    {
        "name": "runtime",
        "triggers": ["runtime", "process", "进程", "运行时", "worker"],
        "regex": r"(runtime|process|worker|startup|shutdown|heartbeat|uvicorn)",
        "summary_focus": "运行时组件、进程/worker 管理、启动关闭逻辑、心跳或服务生命周期",
        "output_template": "按 4 段输出: 1) 核心组件 2) 生命周期阶段 3) 关键方法/入口 4) 边界与未证实点",
    },
    {
        "name": "validation",
        "triggers": ["validation", "validator", "校验", "校验器", "guard"],
        "regex": r"(validat|validator|guard|check|required|constraint|risk)",
        "summary_focus": "校验规则、约束条件、失败路径、必填项或风险检查",
        "output_template": "按 4 段输出: 1) 校验组件 2) 校验条件 3) 失败/异常路径 4) 未覆盖点",
    },
    {
        "name": "telemetry",
        "triggers": ["telemetry", "logging", "日志", "埋点", "观测"],
        "regex": r"(telemetry|logging|logger|observability|trace|metric|record_step)",
        "summary_focus": "日志、埋点、观测记录、指标或 trace 采集路径",
        "output_template": "按 4 段输出: 1) 观测组件 2) 记录内容 3) 调用链位置 4) 未证实点",
    },
    {
        "name": "api",
        "triggers": ["api", "handler", "接口处理", "endpoint", "路由处理"],
        "regex": r"(api|handler|endpoint|request|response|fastapi|router)",
        "summary_focus": "API 入口、handler 实现、request/response 处理与路径注册线索",
        "output_template": "按 4 段输出: 1) API/handler 文件 2) 请求入口或路径证据 3) request/response 处理线索 4) 未证实点",
    },
    {
        "name": "storage",
        "triggers": ["storage", "backend", "对象存储", "文件存储", "数据库"],
        "regex": r"(storage|backend|sqlite|mysql|postgres|redis|s3|bucket|write_text|read_text)",
        "summary_focus": "存储介质、后端类型、读写方法、是否存在数据库/对象存储/文件存储证据",
        "output_template": "按 4 段输出: 1) 存储类型/后端 2) 读写方法 3) 关键文件或调用点 4) 未证实点",
    },
]


def derive_scan_profile(message: str) -> dict[str, Any] | None:
    text = (message or "").lower()
    for profile in SCAN_PROFILES:
        if any(trigger in text for trigger in profile["triggers"]):
            return profile
    return None
