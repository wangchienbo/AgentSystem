"""个人财务记账助手 — Worker 注册入口

参照 novel_studio/bootstrap.py 的 _register_worker 链路：
从 runtime_services 取 master_control，调 master_control.register_app_worker 注册。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_expense_tracker_worker(runtime_services: dict) -> None:
    """注册 ExpenseTrackerWorker 到 MasterControl"""
    master_control = runtime_services.get("master_control")
    if not master_control:
        logger.warning("expense_tracker: master_control not found in runtime_services, skip worker registration")
        return

    try:
        from app.expense_tracker.worker import ExpenseTrackerWorker

        worker = ExpenseTrackerWorker()

        # 主键：blueprint_id（与 app_registry 中一致，LLM 调度时 app 参数常用此值）
        master_control.register_app_worker("bp.designed.personal-finance-tracker", worker)
        # 别名：slug / App 名 / 中文显示名 / 短名（LLM 调度时可能传这些值）
        master_control.register_app_worker("personal-finance-tracker", worker)
        master_control.register_app_worker("personal_finance_tracker", worker)
        master_control.register_app_worker("个人财务记账助手", worker)
        master_control.register_app_worker("expense_tracker", worker)
        master_control.register_app_worker("记账", worker)

        logger.info("✅ expense_tracker Worker registered (keys: bp.designed.personal-finance-tracker / personal-finance-tracker / personal_finance_tracker / 个人财务记账助手 / expense_tracker / 记账)")
    except Exception as e:
        logger.warning("Failed to register expense_tracker Worker: %s", e)
