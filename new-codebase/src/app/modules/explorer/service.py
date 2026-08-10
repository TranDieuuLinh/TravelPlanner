import re

from app.modules.explorer.contract import ExplorerInput, ExplorerOutput
from app.shared.contracts.trip import TripIntent


class ExplorerService:
    _DAY_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:ngày|days?)\b", re.IGNORECASE)
    _DESTINATION_PATTERN = re.compile(
        r"(?:ở|tại|đến|tới|in|to)\s+([\wÀ-ỹ][\wÀ-ỹ .'-]{1,80}?)(?=\s+(?:trong|for|\d+\s*(?:ngày|days?))|[,.;!?]|$)",
        re.IGNORECASE,
    )

    def explore(self, payload: ExplorerInput) -> ExplorerOutput:
        destination_match = self._DESTINATION_PATTERN.search(payload.message)
        if destination_match is None:
            return ExplorerOutput(
                candidates=payload.supplied_candidates,
                missing_fields=["destination"],
                clarification_question="Bạn muốn đi đến đâu?",
            )

        day_match = self._DAY_PATTERN.search(payload.message)
        intent = TripIntent(
            destination=destination_match.group(1).strip(),
            days=int(day_match.group(1)) if day_match else 1,
        )
        return ExplorerOutput(intent=intent, candidates=payload.supplied_candidates)

