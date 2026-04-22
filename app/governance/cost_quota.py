"""Cost Quota Manager - 成本配额模型
为 LLM 调用和 tool call 设置基础配额限制
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

QuotaType = Literal["llm_call", "tool_call", "app_create", "app_modify", "app_delete"]
QuotaPeriod = Literal["hourly", "daily", "monthly"]

class QuotaExceededError(Exception):
    """Raised when quota limit is exceeded."""
    
    def __init__(self, quota_type: QuotaType, current: int, limit: int, period: QuotaPeriod):
        self.quota_type = quota_type
        self.current = current
        self.limit = limit
        self.period = period
        super().__init__(f"Quota exceeded for {quota_type}: {current}/{limit} ({period})")

@dataclass
class QuotaBucket:
    """Single quota bucket."""
    quota_type: QuotaType
    limit: int
    period: QuotaPeriod
    current: int = 0
    reset_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            "quota_type": self.quota_type,
            "limit": self.limit,
            "period": self.period,
            "current": self.current,
            "reset_at": self.reset_at,
        }

@dataclass
class QuotaConfig:
    """Configuration for quota limits."""
    llm_call_hourly: int = 100
    llm_call_daily: int = 1000
    tool_call_hourly: int = 200
    tool_call_daily: int = 2000
    app_create_daily: int = 10
    app_modify_daily: int = 50
    app_delete_daily: int = 5

class CostQuotaManager:
    """Manage cost quotas for various operations."""
    
    def __init__(self, config: QuotaConfig | None = None) -> None:
        self._config = config or QuotaConfig()
        self._buckets: dict[str, QuotaBucket] = {}
        self._initialize_buckets()
    
    def _initialize_buckets(self) -> None:
        """Initialize quota buckets."""
        now = datetime.now(UTC)
        
        # Hourly buckets
        self._set_bucket("llm_call_hourly", QuotaBucket(
            quota_type="llm_call",
            limit=self._config.llm_call_hourly,
            period="hourly",
            current=0,
            reset_at="",
        ))
        self._set_bucket("tool_call_hourly", QuotaBucket(
            quota_type="tool_call",
            limit=self._config.tool_call_hourly,
            period="hourly",
            current=0,
            reset_at="",
        ))
        
        # Daily buckets
        self._set_bucket("llm_call_daily", QuotaBucket(
            quota_type="llm_call",
            limit=self._config.llm_call_daily,
            period="daily",
            current=0,
            reset_at="",
        ))
        self._set_bucket("tool_call_daily", QuotaBucket(
            quota_type="tool_call",
            limit=self._config.tool_call_daily,
            period="daily",
            current=0,
            reset_at="",
        ))
        self._set_bucket("app_create_daily", QuotaBucket(
            quota_type="app_create",
            limit=self._config.app_create_daily,
            period="daily",
            current=0,
            reset_at="",
        ))
        self._set_bucket("app_modify_daily", QuotaBucket(
            quota_type="app_modify",
            limit=self._config.app_modify_daily,
            period="daily",
            current=0,
            reset_at="",
        ))
        self._set_bucket("app_delete_daily", QuotaBucket(
            quota_type="app_delete",
            limit=self._config.app_delete_daily,
            period="daily",
            current=0,
            reset_at="",
        ))
    
    def _set_bucket(self, key: str, bucket: QuotaBucket) -> None:
        self._buckets[key] = bucket
    
    def _get_bucket_key(self, quota_type: QuotaType, period: QuotaPeriod) -> str:
        return f"{quota_type}_{period}"
    
    def consume(
        self,
        quota_type: QuotaType,
        amount: int = 1,
        period: QuotaPeriod = "hourly"
    ) -> tuple[bool, QuotaBucket]:
        """
        Consume quota.
        
        Returns (success, bucket).
        Raises QuotaExceededError if quota exceeded.
        """
        key = self._get_bucket_key(quota_type, period)
        bucket = self._buckets.get(key)
        
        if not bucket:
            # No quota limit for this type
            return True, QuotaBucket(quota_type=quota_type, limit=0, period=period, current=0)
        
        if bucket.current + amount > bucket.limit:
            raise QuotaExceededError(
                quota_type=quota_type,
                current=bucket.current,
                limit=bucket.limit,
                period=period,
            )
        
        bucket.current += amount
        return True, bucket
    
    def get_usage(self, quota_type: QuotaType | None = None) -> dict[str, QuotaBucket]:
        """Get current usage for all or specific quota type."""
        if quota_type:
            return {
                k: v for k, v in self._buckets.items()
                if v.quota_type == quota_type
            }
        return self._buckets
    
    def reset_bucket(self, quota_type: QuotaType, period: QuotaPeriod) -> None:
        """Reset a specific bucket."""
        key = self._get_bucket_key(quota_type, period)
        if key in self._buckets:
            self._buckets[key].current = 0
    
    def get_summary(self) -> dict:
        """Get quota usage summary."""
        summary = {}
        for key, bucket in self._buckets.items():
            summary[key] = {
                "current": bucket.current,
                "limit": bucket.limit,
                "period": bucket.period,
                "usage_percent": round(bucket.current / bucket.limit * 100, 2) if bucket.limit > 0 else 0,
            }
        return summary
