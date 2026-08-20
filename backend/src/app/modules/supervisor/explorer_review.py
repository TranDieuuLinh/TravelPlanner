from __future__ import annotations

import re
import unicodedata

from app.modules.explorer.public import ExplorerReview, TripContextPatch


_ACCEPT = {
    "ok",
    "okay",
    "dong y",
    "dung nhu vay",
    "dung mac dinh",
    "giu nguyen",
    "khong",
    "khong can chinh",
    "tiep tuc",
    "chot",
}


def compose_explorer_review(review: ExplorerReview) -> tuple[str, str | None]:
    if review.kind == "missing_fields":
        question = "Bạn muốn đi tỉnh hoặc thành phố nào?"
        return question, question
    if review.kind == "error":
        message = (
            review.error.message
            if review.error is not None
            else "Explorer không thể xử lý yêu cầu này."
        )
        return message, None
    if review.kind != "defaults_proposed" or review.trip_context is None:
        return "Dữ liệu chuyến đi đã sẵn sàng.", None

    context = review.trip_context
    details: list[str] = []
    fields = set(review.defaulted_fields)
    if "days" in fields:
        details.append(f"{context.days} ngày")
    if "people" in fields:
        details.append(_people_label(context.people))
    if "budget" in fields:
        details.append(_budget_label(context.budget))
    if "shortPreferences" in fields and context.short_preferences:
        details.append("ưu tiên " + ", ".join(context.short_preferences))
    summary = "; ".join(details)
    response = (
        f"Với {context.input_adm}, Penguin đang tạm dùng các giá trị mặc định: "
        f"{summary}. Bạn muốn chỉnh gì không?"
    )
    return response, response


def parse_explorer_review_patch(
    message: str,
    review: ExplorerReview,
    *,
    tag_definitions: dict[str, list[str]],
) -> TripContextPatch | None:
    raw = " ".join(message.strip().split())
    normalized = _normalize(raw).strip(" .!?")
    if not raw:
        return None
    if normalized in _ACCEPT:
        return TripContextPatch()
    if review.kind == "missing_fields":
        destination = _destination(raw)
        if destination:
            payload = {
                "inputADM": {"operation": "set", "value": destination}
            }
            _parse_days(normalized, payload)
            _parse_people(normalized, payload)
            _parse_budget(normalized, payload)
            _parse_tags(normalized, payload, tag_definitions, current=[])
            return TripContextPatch.model_validate(payload)
        return None

    payload: dict = {}
    destination = _destination_change(raw)
    if destination:
        payload["inputADM"] = {"operation": "set", "value": destination}
    _parse_days(normalized, payload)
    _parse_people(normalized, payload)
    _parse_budget(normalized, payload)
    _parse_tags(
        normalized,
        payload,
        tag_definitions,
        current=(
            review.trip_context.short_preferences
            if review.trip_context is not None
            else []
        ),
    )
    _parse_items(raw, payload)
    _parse_places(raw, payload, tag_definitions)
    if "khong co luu y" in normalized:
        payload["specialNotes"] = {"operation": "clear"}
    elif note := re.search(r"(?:lưu ý|ghi chú)\s+(?P<value>[^.;!?]+)", raw, re.IGNORECASE):
        payload["specialNotes"] = {
            "operation": "add",
            "values": [note.group("value").strip()],
        }
    return TripContextPatch.model_validate(payload) if payload else None


def _people_label(people) -> str:
    parts = [f"{people.adults} người lớn"]
    if people.children:
        parts.append(f"{people.children} trẻ em")
    if people.infants:
        parts.append(f"{people.infants} em bé")
    return ", ".join(parts)


def _budget_label(budget) -> str:
    levels = {"low": "tiết kiệm", "medium": "trung bình", "high": "cao"}
    label = f"ngân sách {levels[budget.level]}"
    if budget.amount_per_person is not None:
        amount = f"{budget.amount_per_person:,}".replace(",", ".")
        label += f" khoảng {amount} {budget.currency}/người cho toàn chuyến"
    return label


def _destination(raw: str) -> str | None:
    changed = _destination_change(raw)
    if changed:
        return changed
    candidate = re.split(
        r"[,.;!?]|\s+\d{1,3}\s*(?:ngày|days?|người|people)",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,.!?")
    if candidate and len(candidate) <= 200:
        return candidate
    return None


def _destination_change(raw: str) -> str | None:
    match = re.search(
        r"(?:đổi\s+sang|chuyển\s+sang|đi|đến|tới)\s+"
        r"(?P<value>[^,.;!?]+?)"
        r"(?=\s+(?:trong|cho|với|ngân sách|budget|\d+\s*ngày)|[,.;!?]|$)",
        raw,
        re.IGNORECASE,
    )
    return match.group("value").strip() if match else None


def _parse_days(message: str, payload: dict) -> None:
    if re.search(r"(?:dung|ve) mac dinh.{0,20}ngay", message):
        payload["days"] = {"operation": "reset_to_default"}
        return
    decrement = re.search(r"(?:bot|giam)\s+(\d+|mot)\s+ngay", message)
    increment = re.search(r"(?:them|tang)\s+(\d+|mot)\s+ngay", message)
    if decrement:
        payload["days"] = {
            "operation": "decrement",
            "value": _number(decrement.group(1)),
        }
    elif increment:
        payload["days"] = {
            "operation": "increment",
            "value": _number(increment.group(1)),
        }
    elif match := re.search(r"\b(\d{1,2})\s+ngay\b", message):
        payload["days"] = {"operation": "set", "value": int(match.group(1))}


def _parse_people(message: str, payload: dict) -> None:
    if re.search(r"(?:dung|ve) mac dinh.{0,20}nguoi", message):
        payload["people"] = {"operation": "reset_to_default"}
        return
    decrement = re.search(
        r"(?:bot|giam)\s+(\d+|mot)\s+"
        r"(?P<kind>nguoi(?:\s+lon)?|tre\s+em|em\s+be)",
        message,
    )
    increment = re.search(
        r"(?:them|tang)\s+(\d+|mot)\s+"
        r"(?P<kind>nguoi(?:\s+lon)?|tre\s+em|em\s+be)",
        message,
    )
    if decrement:
        payload["people"] = {
            "operation": "decrement",
            "value": _traveler_delta(
                decrement.group("kind"), _number(decrement.group(1))
            ),
        }
    elif increment:
        payload["people"] = {
            "operation": "increment",
            "value": _traveler_delta(
                increment.group("kind"), _number(increment.group(1))
            ),
        }
    elif breakdown := _traveler_breakdown(message):
        payload["people"] = {"operation": "set", "value": breakdown}
    elif match := re.search(r"\b(\d{1,3})\s+nguoi\b", message):
        payload["people"] = {
            "operation": "set",
            "value": {"adults": int(match.group(1))},
        }


def _traveler_delta(kind: str, amount: int) -> dict[str, int]:
    field = "children" if "tre" in kind else "infants" if "be" in kind else "adults"
    return {field: amount}


def _traveler_breakdown(message: str) -> dict[str, int]:
    patterns = {
        "adults": r"\b(\d{1,3})\s+nguoi\s+lon\b",
        "children": r"\b(\d{1,3})\s+tre\s+em\b",
        "infants": r"\b(\d{1,3})\s+em\s+be\b",
    }
    values = {
        field: int(match.group(1))
        for field, pattern in patterns.items()
        if (match := re.search(pattern, message)) is not None
    }
    if values and "adults" not in values:
        values["adults"] = 2
    return values


def _parse_budget(message: str, payload: dict) -> None:
    if re.search(r"(?:dung|ve) mac dinh.{0,24}ngan sach", message):
        payload["budget"] = {"operation": "reset_to_default"}
        return
    level = None
    if any(value in message for value in ("tiet kiem", "budget low", "ngan sach low")):
        level = "low"
    elif any(value in message for value in ("trung binh", "budget medium")):
        level = "medium"
    elif any(value in message for value in ("cao cap", "budget high", "ngan sach cao")):
        level = "high"
    amount = None
    amount_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|million|k|nghin)", message)
    if amount_match:
        value = float(amount_match.group(1).replace(",", "."))
        amount = round(
            value
            * (1_000_000 if amount_match.group(2) in {"trieu", "million"} else 1_000)
        )
    if level is not None or amount is not None:
        operation = "set"
        if amount is not None and re.search(r"(?:tang|them).{0,16}ngan sach", message):
            operation = "increment"
        elif amount is not None and re.search(r"(?:giam|bot).{0,16}ngan sach", message):
            operation = "decrement"
        payload["budget"] = {
            "operation": operation,
            "value": {
                "amountPerPerson": amount,
                "currency": "VND",
                "level": level,
            },
        }


def _parse_tags(
    message: str,
    payload: dict,
    definitions: dict[str, list[str]],
    *,
    current: list[str],
) -> None:
    positive: list[str] = []
    removed: list[str] = []
    avoided: list[str] = []
    for tag, aliases in definitions.items():
        candidates = [tag, *aliases]
        matched = next(
            (
                alias
                for alias in candidates
                if _contains_phrase(message, _normalize(alias))
            ),
            None,
        )
        if matched is None:
            continue
        alias = _normalize(matched)
        if re.search(rf"(?:khong thich|tranh)\s+{re.escape(alias)}\b", message):
            removed.append(tag)
            avoided.append(tag)
        elif re.search(rf"bo\s+{re.escape(alias)}\b", message):
            removed.append(tag)
        elif any(cue in message for cue in ("thich", "uu tien", "chi muon")):
            positive.append(tag)
    if positive and removed:
        values = [value for value in current if value not in removed]
        values.extend(value for value in positive if value not in values)
        payload["shortPreferences"] = {
            "operation": "replace",
            "values": values,
        }
    elif positive:
        payload["shortPreferences"] = {
            "operation": "replace" if "chi muon" in message else "add",
            "values": positive,
        }
    if removed and not positive:
        payload["shortPreferences"] = {
            "operation": "remove",
            "values": removed,
        }
    if avoided:
        payload["shortAvoids"] = {"operation": "add", "values": avoided}


def _parse_items(raw: str, payload: dict) -> None:
    clear = re.search(r"(?:xóa|bỏ)\s+(?:hết|toàn bộ)\s+(?:món|đồ ăn|đồ uống)", raw, re.IGNORECASE)
    if clear:
        payload["inputItems"] = {"operation": "clear"}
        return
    match = re.search(
        r"(?P<remove>bỏ\s+)?(?:muốn\s+|thêm\s+)?"
        r"(?P<action>ăn|uống|thử)\s+(?P<name>[^,.;!?]+)",
        raw,
        re.IGNORECASE,
    )
    if not match:
        return
    operation = "remove" if match.group("remove") else "add"
    action = _normalize(match.group("action"))
    item_type = "drink" if action == "uong" else "food"
    value = {"name": match.group("name").strip()}
    if operation == "add":
        value["itemType"] = item_type
    payload["inputItems"] = {"operation": operation, "values": [value]}


def _parse_places(
    raw: str,
    payload: dict,
    definitions: dict[str, list[str]],
) -> None:
    if re.search(r"(?:xóa|bỏ)\s+(?:hết|toàn bộ)\s+địa điểm", raw, re.IGNORECASE):
        payload["places"] = {"operation": "clear"}
        return
    match = re.search(
        r"(?P<cue>thêm|bỏ|chỉ\s+(?:đi|muốn\s+đi))\s+"
        r"(?P<name>[^,.;!?]+)",
        raw,
        re.IGNORECASE,
    )
    if not match:
        return
    name = match.group("name").strip()
    normalized_name = _normalize(name)
    if (
        re.fullmatch(r"(?:\d+|một)\s+(?:ngày|người)", name, re.IGNORECASE)
        or _is_taxonomy_phrase(normalized_name, definitions)
        or re.match(r"(?:ăn|uống|thử)\b", name, re.IGNORECASE)
    ):
        return
    cue = _normalize(match.group("cue"))
    operation = "add" if cue == "them" else "remove" if cue == "bo" else "replace"
    payload["places"] = {
        "operation": operation,
        "values": [{"name": name}],
    }


def _is_taxonomy_phrase(
    value: str,
    definitions: dict[str, list[str]],
) -> bool:
    return any(
        value == _normalize(candidate)
        for tag, aliases in definitions.items()
        for candidate in (tag, *aliases)
    )


def _contains_phrase(message: str, phrase: str) -> bool:
    return bool(phrase and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", message))


def _number(value: str) -> int:
    return 1 if value == "mot" else int(value)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .replace("đ", "d")
        .split()
    )
