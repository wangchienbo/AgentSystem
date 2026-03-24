from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


OverviewT = TypeVar("OverviewT")
StatsT = TypeVar("StatsT")


class OperatorDashboardCore(BaseModel, Generic[OverviewT, StatsT]):
    overview: OverviewT
    stats: StatsT
