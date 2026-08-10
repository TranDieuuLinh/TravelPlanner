from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class FreshnessDecision:
    ttl: timedelta
    force_refresh: bool = False


class FreshnessPolicy:
    LIVE_TERMS = {
        "hôm nay",
        "hiện tại",
        "mới nhất",
        "latest",
        "today",
        "current",
        "thời tiết",
        "weather",
        "giá",
        "price",
    }
    EVENT_TERMS = {"sự kiện", "event", "lịch hoạt động", "schedule"}
    DAILY_TERMS = {
        "giờ mở cửa",
        "opening hours",
        "giá vé",
        "ticket price",
        "quy định",
        "regulation",
    }

    def for_query(self, query: str) -> FreshnessDecision:
        lowered = query.casefold()
        if any(term in lowered for term in self.LIVE_TERMS):
            return FreshnessDecision(timedelta(hours=1), force_refresh=True)
        if any(term in lowered for term in self.EVENT_TERMS):
            return FreshnessDecision(timedelta(hours=6))
        if any(term in lowered for term in self.DAILY_TERMS):
            return FreshnessDecision(timedelta(days=1))
        return FreshnessDecision(timedelta(days=21))

    @staticmethod
    def is_fresh(expires_at: datetime, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return expires_at > current

    @staticmethod
    def score(expires_at: datetime, now: datetime | None = None) -> float:
        current = now or datetime.now(timezone.utc)
        remaining_hours = (expires_at - current).total_seconds() / 3600
        return max(0.0, min(1.0, remaining_hours / (24 * 21)))
