from datetime import date, datetime, timedelta
import re


_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_DMY_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")


def prompt_start_date(prompt: str | None) -> date | None:
    value = prompt or ""
    iso = _ISO_DATE.search(value)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    dmy = _DMY_DATE.search(value)
    if dmy:
        try:
            return date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
        except ValueError:
            return None
    return None


def tomorrow() -> date:
    return datetime.now().astimezone().date() + timedelta(days=1)


def timezone_for_destination(_: str | None) -> str:
    # Current supported ADM catalog is Vietnam-first. Future global ADM
    # resolution should return an IANA timezone instead of guessing here.
    return "Asia/Ho_Chi_Minh"
