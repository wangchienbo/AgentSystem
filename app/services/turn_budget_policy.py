"""TurnBudgetPolicy — 统一 turn budget 决策。

三层结构：
1. 基础预算：按任务模式（CHAT 6/EXECUTION 15/ENGINEERING 30/BACKGROUND 50）
2. 授权加成：已授权 +20 轮
3. 硬上限：50 轮

用法：
    >>> TurnBudgetPolicy.decide(TaskModeBudget.ENGINEERING, authorized=True)
    50
"""
from __future__ import annotations

from enum import Enum


class TaskModeBudget(str, Enum):
    """任务模式枚举，用于预算决策。"""
    CHAT = "chat"
    EXECUTION = "execution"
    ENGINEERING = "engineering"
    BACKGROUND = "background"


class TurnBudgetPolicy:
    """统一 turn budget 策略。"""

    # 按任务模式的基础预算
    BASE: dict[TaskModeBudget, int] = {
        TaskModeBudget.CHAT: 50,
        TaskModeBudget.EXECUTION: 80,
        TaskModeBudget.ENGINEERING: 120,
        TaskModeBudget.BACKGROUND: 200,
    }

    # 授权加成（已授权时额外增加）
    AUTH_BONUS: int = 50

    # 硬上限（不允许超过）
    HARD_CAP: int = 200

    # 收敛提示阈值：超过此轮次时注入收敛引导
    CONVERGENCE_HINT_TURN: int = 50

    @classmethod
    def decide(cls, mode: TaskModeBudget, authorized: bool = False) -> int:
        """计算 turn budget。

        Args:
            mode: 当前任务模式
            authorized: 是否已获得授权

        Returns:
            允许的最大 turn 数
        """
        base = cls.BASE.get(mode, cls.BASE[TaskModeBudget.CHAT])
        if authorized:
            base = min(base + cls.AUTH_BONUS, cls.HARD_CAP)
        return min(base, cls.HARD_CAP)
