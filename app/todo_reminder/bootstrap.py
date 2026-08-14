"""待办事项提醒 — Worker 注册入口

参照 novel_studio/bootstrap.py 的 _register_worker 链路：
从 runtime_services 取 master_control，调 master_control.register_app_worker 注册。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_todo_reminder_worker(runtime_services: dict) -> None:
    """注册 TodoReminderWorker 到 MasterControl"""
    master_control = runtime_services.get("master_control")
    if not master_control:
        logger.warning("todo_reminder: master_control not found in runtime_services, skip worker registration")
        return

    try:
        from app.todo_reminder.worker import TodoReminderWorker

        worker = TodoReminderWorker()

        # 主键：blueprint_id（与 app_registry 中一致，LLM 调度时 app 参数常用此值）
        master_control.register_app_worker("bp.designed.todo-reminder", worker)
        # 别名：App 名 / 中文显示名（LLM 调度时可能传这些值）
        master_control.register_app_worker("todo-reminder", worker)
        master_control.register_app_worker("todo_reminder", worker)
        master_control.register_app_worker("待办事项提醒", worker)

        logger.info("✅ todo_reminder Worker registered (keys: bp.designed.todo-reminder / todo-reminder / todo_reminder / 待办事项提醒)")
    except Exception as e:
        logger.warning("Failed to register todo_reminder Worker: %s", e)
