from datetime import date, datetime, time
from zoneinfo import ZoneInfo


ROUTING_TIMEZONE_NAME = "Asia/Ho_Chi_Minh"
ROUTING_TIMEZONE = ZoneInfo(ROUTING_TIMEZONE_NAME)


def normalize_routing_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ROUTING_TIMEZONE)
    return value.astimezone(ROUTING_TIMEZONE)


def routing_today() -> date:
    return datetime.now(ROUTING_TIMEZONE).date()


def combine_routing_datetime(
    departure_date: date,
    departure_time: time,
) -> datetime:
    return datetime.combine(
        departure_date,
        departure_time,
        tzinfo=ROUTING_TIMEZONE,
    )
