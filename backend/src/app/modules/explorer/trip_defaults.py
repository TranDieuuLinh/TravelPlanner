from datetime import date, datetime, timedelta


def tomorrow() -> date:
    return datetime.now().astimezone().date() + timedelta(days=1)


def timezone_for_destination(_: str | None) -> str:
    # Current supported ADM catalog is Vietnam-first. Future global ADM
    # resolution should return an IANA timezone instead of guessing here.
    return "Asia/Ho_Chi_Minh"
