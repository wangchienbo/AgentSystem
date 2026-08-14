"""每日饮水提醒助手 — Worker 注册入口

参照 novel_studio/bootstrap.py 的 _register_worker 链路：
从 runtime_services 取 master_control，调 master_control.register_app_worker 注册。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_water_reminder_worker(runtime_services: dict) -> None:
    """注册 WaterReminderWorker 到 MasterControl"""
    master_control = runtime_services.get("master_control")
    if not master_control:
        logger.warning("water_reminder: master_control not found in runtime_services, skip worker registration")
        return

    try:
        from app.water_reminder.worker import WaterReminderWorker

        worker = WaterReminderWorker()

        # 主键：blueprint_id（与 app_registry 中一致，LLM 调度时 app 参数常用此值）
        master_control.register_app_worker("bp.designed.daily-water-reminder", worker)
        # 别名：slug / App 名 / 中文显示名（LLM 调度时可能传这些值）
        master_control.register_app_worker("daily-water-reminder", worker)
        master_control.register_app_worker("daily_water_reminder", worker)
        master_control.register_app_worker("每日饮水提醒助手", worker)
        # 目录短名 slug（LLM 调度时 app 参数可能用此值）
        master_control.register_app_worker("water_reminder", worker)

        logger.info("✅ water_reminder Worker registered (keys: bp.designed.daily-water-reminder / daily-water-reminder / daily_water_reminder / 每日饮水提醒助手 / water_reminder)")
    except Exception as e:
        logger.warning("Failed to register water_reminder Worker: %s", e)
