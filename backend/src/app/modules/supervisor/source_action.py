from __future__ import annotations

import re
import unicodedata

from app.modules.explorer.public import ExplorerOutput
from app.modules.supervisor.contract import SourceAction, SupervisorDecision


_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_SUMMARY_CUES = (
    "tom tat",
    "summarize",
    "summary",
)


def has_source_input(message: str, *, attached: bool) -> bool:
    return attached or bool(_URL.search(message))


def infer_source_action(message: str, *, attached: bool) -> SourceAction | None:
    if not has_source_input(message, attached=attached):
        return None
    normalized = _normalize(message)
    if any(cue in normalized for cue in _SUMMARY_CUES):
        return "summarize_source"
    return "plan_from_source"


def source_action_decision(action: SourceAction) -> SupervisorDecision:
    return SupervisorDecision(
        route="explorer",
        confidence=1.0,
        reason=(
            "Source summary request selected Explorer extraction."
            if action == "summarize_source"
            else "Source planning request selected Explorer extraction."
        ),
        source_action=action,
    )


def compose_source_summary(output: ExplorerOutput) -> str:
    if output.status == "error":
        return (
            output.error.message
            if output.error is not None
            else "Explorer không thể đọc nguồn này."
        )

    parts: list[str] = []
    if output.input_adm:
        parts.append(f"Nguồn nói về {output.input_adm}.")
    places = [place.name for place in (output.places or [])]
    if places:
        parts.append("Các địa điểm được nhắc đến: " + ", ".join(places[:12]) + ".")
    notes = list(dict.fromkeys(note.summary for note in (output.url_notes or [])))
    if notes:
        parts.append(" ".join(notes[:6]))
    if not parts:
        return "Penguin đã đọc nguồn nhưng chưa trích xuất được nội dung đủ rõ để tóm tắt."
    return "\n\n".join(parts)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .replace("đ", "d")
        .split()
    )
