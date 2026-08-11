import re
import unicodedata
from datetime import UTC, datetime

from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerImageInput,
    ExplorerPeople,
    ExplorerPlace,
    PlaceSource,
    RequestedItem,
    SourceNote,
)
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import (
    AdmEvidence,
    BudgetSignal,
    ExplorerDraft,
    SourceExtractionResult,
)


_DESTINATION = re.compile(
    r"(?:ở|tại|đến|tới|du lịch(?:\s+ở|\s+đến)?|in|to|trip to)\s+"
    r"(?P<value>[\wÀ-ỹ][\wÀ-ỹ .'-]{1,80}?)"
    r"(?=\s+(?:trong|for|\d+\s*(?:ngày|days?))|[,.;!?]|$)",
    re.IGNORECASE,
)
_KNOWN_ADM = re.compile(
    r"\b(Hà Nội|Ha Noi|Hanoi|Đà Nẵng|Da Nang|Huế|Hue|"
    r"TP\.?\s*HCM|TP\.?\s*Hồ Chí Minh|Sài Gòn|Ho Chi Minh City)\b",
    re.IGNORECASE,
)
_DAY = re.compile(r"\b(?P<days>\d{1,2})\s*(?:ngày|days?)\b", re.IGNORECASE)
_PEOPLE = re.compile(
    r"\b(?P<count>\d{1,3})\s*(?:người|adults?|people|persons?)\b",
    re.IGNORECASE,
)
_AMOUNT = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>triệu|trieu|million|k|nghìn|nghin)?"
    r"\s*(?P<currency>vnd|đ|usd|\$)?",
    re.IGNORECASE,
)
_NAMED_ITEM = re.compile(
    r"\b(?P<action>ăn|uống|thử|eat|drink|try|ngắm|xem|watch|experience)\s+"
    r"(?P<item>.+?)\s+(?:ở|tại|at)\s+(?P<venue>.+?)"
    r"(?=\s+(?:ở|tại|in)\s+(?:Hà Nội|Ha Noi|Hanoi|Đà Nẵng|Da Nang|Huế|Hue|"
    r"TP\.?\s*HCM|TP\.?\s*Hồ Chí Minh|Sài Gòn|Ho Chi Minh City)|"
    r"\s+(?:trong|for)\s+\d+\s*(?:ngày|days?)|[,.;!?]|$)",
    re.IGNORECASE,
)
_VISIT = re.compile(
    r"\b(?:tham quan|ghé|visit|see)\s+(?P<venue>.+?)"
    r"(?=\s+(?:và|and)\s+(?:ăn|uống|thử|eat|drink|try|ngắm|xem|watch)|"
    r"\s+(?:trong|for)\s+\d+\s*(?:ngày|days?)|[,.;!?]|$)",
    re.IGNORECASE,
)
_GENERIC_ITEM = re.compile(
    r"\b(?P<action>ăn|uống|thử|eat|drink|try)\s+(?P<item>[^,.;!?]+)",
    re.IGNORECASE,
)


def _normalize_adm(value: str) -> str:
    key = _ascii(value)
    aliases = {
        "ha noi": "Hanoi",
        "hanoi": "Hanoi",
        "da nang": "Da Nang",
        "tp hcm": "Ho Chi Minh City",
        "tp ho chi minh": "Ho Chi Minh City",
        "sai gon": "Ho Chi Minh City",
        "ho chi minh city": "Ho Chi Minh City",
    }
    return aliases.get(key, value.strip())


def _ascii(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
        .replace("đ", "d")
        .split()
    )


def _item_type(action: str) -> str:
    key = _ascii(action)
    if key in {"uong", "drink"}:
        return "drink"
    if key in {"an", "thu", "eat", "try"}:
        return "food"
    return "activity"


def _action(action: str) -> str:
    return {"ăn": "eat", "uống": "drink", "thử": "try", "ngắm": "watch", "xem": "watch"}.get(
        action.casefold(), action.casefold()
    )


def _is_named_venue(value: str) -> bool:
    normalized = _ascii(value).strip(" -")
    generic = {
        "mot quan dep",
        "mot quan ngon",
        "quan dep",
        "quan ngon",
        "a nice cafe",
        "a restaurant",
        "a cafe",
    }
    return bool(normalized and normalized not in generic and len(normalized.split()) >= 2)


class RuleBasedExplorerDraftGenerator:
    """Honest offline baseline; production semantic extraction is injectable."""

    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft:
        return self._parse_prompt(raw_prompt)

    async def from_sources(
        self,
        *,
        raw_prompt: str | None,
        sources: list[SourceExtractionResult],
    ) -> ExplorerDraft:
        draft = self._parse_prompt(raw_prompt) if raw_prompt else ExplorerDraft()
        source_budgets = []
        for source in sources:
            draft.adm_candidates.extend(source.adm_candidates)
            draft.places.extend(source.places)
            draft.url_notes.extend(source.notes)
            draft.short_preferences.extend(source.short_preferences)
            draft.short_avoids.extend(source.short_avoids)
            source_budgets.extend(source.budget_signals)
        if draft.budget.source == "default" and source_budgets:
            rank = {"image": 2, "url": 1, "default": 0, "raw_prompt": 3}
            draft.budget = max(
                source_budgets,
                key=lambda signal: (rank[signal.budget.source], signal.confidence),
            ).budget
        return draft

    def _parse_prompt(self, prompt: str) -> ExplorerDraft:
        known_destinations = list(_KNOWN_ADM.finditer(prompt))
        destination = known_destinations[-1] if known_destinations else _DESTINATION.search(prompt)
        adm_candidates: list[AdmEvidence] = []
        input_adm = None
        if destination:
            observed = (
                destination.group("value").strip()
                if "value" in destination.groupdict()
                else destination.group(0).strip()
            )
            input_adm = _normalize_adm(observed)
            adm_candidates.append(
                AdmEvidence(
                    value=input_adm,
                    evidence=destination.group(0)[:500],
                    source_type="raw_prompt",
                    confidence=0.99,
                )
            )
        places, items = self._prompt_places_and_items(prompt)
        return ExplorerDraft(
            input_adm=input_adm,
            adm_candidates=adm_candidates,
            places=places,
            input_items=items,
            budget=self._prompt_budget(prompt),
            people=self._prompt_people(prompt),
            short_preferences=self._preferences(prompt),
            short_avoids=self._avoids(prompt),
        )

    def _prompt_places_and_items(
        self, prompt: str
    ) -> tuple[list[ExplorerPlace], list[RequestedItem]]:
        places: list[ExplorerPlace] = []
        items: list[RequestedItem] = []
        occupied: list[tuple[int, int]] = []
        for match in _NAMED_ITEM.finditer(prompt):
            venue = match.group("venue").strip()
            item = match.group("item").strip()
            if not _is_named_venue(venue):
                continue
            occupied.append(match.span())
            source = PlaceSource(
                origin="input",
                evidenceType="raw_prompt",
                evidence=match.group(0)[:500],
            )
            places.append(
                ExplorerPlace(name=venue, confidence=0.95, sourcePlaces=[source])
            )
            items.append(
                RequestedItem(
                    name=item,
                    itemType=_item_type(match.group("action")),
                    action=_action(match.group("action")),
                    relatedPlaceName=venue,
                    evidence=match.group(0)[:500],
                    confidence=0.95,
                )
            )
        for match in _VISIT.finditer(prompt):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            venue = match.group("venue").strip()
            if _is_named_venue(venue):
                places.append(
                    ExplorerPlace(
                        name=venue,
                        confidence=0.9,
                        sourcePlaces=[
                            PlaceSource(
                                origin="input",
                                evidenceType="raw_prompt",
                                evidence=match.group(0)[:500],
                            )
                        ],
                    )
                )
        for match in _GENERIC_ITEM.finditer(prompt):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            item = match.group("item").strip()
            items.append(
                RequestedItem(
                    name=item,
                    itemType=_item_type(match.group("action")),
                    action=_action(match.group("action")),
                    evidence=match.group(0)[:500],
                    confidence=0.85,
                )
            )
        return places, items

    @staticmethod
    def _prompt_budget(prompt: str) -> ExplorerBudget:
        normalized = _ascii(prompt)
        level = "low" if any(word in normalized for word in ("tiet kiem", "cheap", "low budget")) else "medium"
        amount = None
        currency = "VND"
        for match in _AMOUNT.finditer(prompt):
            if not match.group("unit") and not match.group("currency"):
                continue
            value = float(match.group("amount").replace(",", "."))
            unit = _ascii(match.group("unit") or "")
            multiplier = 1_000_000 if unit in {"trieu", "million"} else 1_000 if unit in {"k", "nghin"} else 1
            amount = round(value * multiplier)
            currency = "USD" if (match.group("currency") or "").casefold() in {"usd", "$"} else "VND"
            break
        return ExplorerBudget(level=level, targetAmount=amount, currency=currency, source="raw_prompt" if amount is not None or level == "low" else "default")

    @staticmethod
    def _prompt_people(prompt: str) -> ExplorerPeople:
        match = _PEOPLE.search(prompt)
        return ExplorerPeople(adults=int(match.group("count")) if match else 1)

    @staticmethod
    def _preferences(prompt: str) -> list[str]:
        normalized = _ascii(prompt)
        values = []
        for marker, value in (("yen tinh", "quiet_places"), ("chup anh", "photography"), ("dia phuong", "local_experience")):
            if marker in normalized:
                values.append(value)
        return values

    @staticmethod
    def _avoids(prompt: str) -> list[str]:
        normalized = _ascii(prompt)
        values = []
        for marker, value in (("tranh dong", "crowded_places"), ("khong nightlife", "nightlife"), ("avoid nightlife", "nightlife")):
            if marker in normalized:
                values.append(value)
        return values


class InlineImageSourceExtractor:
    def __init__(self, drafts: RuleBasedExplorerDraftGenerator | None = None) -> None:
        self._drafts = drafts or RuleBasedExplorerDraftGenerator()

    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult:
        if not image.ocr_text:
            raise ExplorerOperationError(
                "IMAGE_OCR_FAILED",
                "OCR ảnh chưa được cấu hình cho dữ liệu ảnh thô.",
            )
        draft = self._drafts._parse_prompt(image.ocr_text)
        places = []
        notes = [
            SourceNote(
                summary=" ".join(image.ocr_text.split())[:500],
                evidenceType="image_ocr",
                observedAt=datetime.now(UTC),
            )
        ]
        for place in draft.places:
            sources = [
                source.model_copy(
                    update={
                        "origin": "input",
                        "evidence_type": "image_ocr",
                        "observed_at": datetime.now(UTC),
                    }
                )
                for source in place.source_places
            ]
            places.append(place.model_copy(update={"source_places": sources}))
        for item in draft.input_items:
            notes.append(
                SourceNote(
                    summary=item.evidence,
                    placeName=item.related_place_name,
                    evidenceType="image_ocr",
                    observedAt=datetime.now(UTC),
                )
            )
        budget_signals = (
            [BudgetSignal(
                budget=draft.budget.model_copy(update={"source": "image"}),
                confidence=0.8,
            )]
            if draft.budget.source != "default"
            else []
        )
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="image",
            sourceRef=image.file_name,
            status="succeeded",
            admCandidates=[
                candidate.model_copy(update={"source_type": "image_ocr"})
                for candidate in draft.adm_candidates
            ],
            places=places,
            notes=notes,
            budgetSignals=budget_signals,
            extractedPlaceCount=len(places),
        )


class UnconfiguredUrlSourceExtractor:
    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        raise ExplorerOperationError(
            "SOURCE_UNAVAILABLE",
            "URL importer chưa được cấu hình trong backend scaffold.",
        )


class InMemoryExplorerSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, tuple[str, dict]] = {}

    async def save(self, intake_id: str, snapshot_kind: str, payload: dict) -> None:
        self.snapshots[intake_id] = (snapshot_kind, payload)
