import re
from dataclasses import dataclass

from app.modules.explorer.public import (
    deduplicate_places,
    ExplorerOutput,
    place_name_key,
    TagCatalog,
    normalize_budget_per_person,
)
from app.modules.place_checker.contract import PlaceCheckerInput
from app.orchestration.memory_projection import memory_field, merge_memory_places
from app.shared.contracts.trip import TripIntent
from app.shared.tools.daily_budget import DestinationDailyBudgetEstimator


class ExplorerHandoffError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: str = "blocked",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class ExplorerHandoff:
    explorer_output: ExplorerOutput
    place_checker_input: PlaceCheckerInput


class ExplorerHandoffProjector:
    _DAYS = re.compile(r"\b\d{1,2}\s*(?:ngày|days?)\b", re.IGNORECASE)
    _PEOPLE = re.compile(
        r"\b\d{1,3}\s*(?:người|adults?|people|persons?)\b", re.IGNORECASE
    )

    def __init__(
        self,
        tag_catalog: TagCatalog,
        budget_estimator: DestinationDailyBudgetEstimator | None = None,
    ) -> None:
        self.tag_catalog = tag_catalog
        self.budget_estimator = budget_estimator or DestinationDailyBudgetEstimator()

    def project(
        self,
        output: ExplorerOutput,
        *,
        raw_prompt: str,
        memory=None,
        resolved_references: list | None = None,
        has_source_input: bool = False,
    ) -> ExplorerHandoff:
        if output.status == "error":
            error = output.error
            raise ExplorerHandoffError(
                error.code if error else "EXPLORER_FAILED",
                error.message if error else "Explorer không thể tạo trip intake.",
                status="error",
                retryable=error.retryable if error else False,
            )

        destination = output.input_adm or memory_field(memory, "destination")
        if not destination:
            raise ExplorerHandoffError(
                "PLACE_CHECKER_DESTINATION_REQUIRED",
                output.clarification_question or "Bạn muốn đi tỉnh hoặc thành phố nào?",
            )

        places = deduplicate_places(
            merge_memory_places(
                output.places or [],
                memory,
                resolved_references=resolved_references,
            )
        )
        days = self._days(output, raw_prompt, memory, has_source_input)
        people = self._people(output, raw_prompt, memory)
        budget = self._budget(output, memory)
        preferences = list(
            dict.fromkeys(
                [
                    *self.tag_catalog.filter_allowed(output.short_preferences),
                    *self.tag_catalog.resolve(
                        memory_field(memory, "preferences", []) or []
                    ),
                ]
            )
        )
        avoids = list(
            dict.fromkeys(
                [
                    *self.tag_catalog.filter_allowed(output.short_avoids),
                    *self.tag_catalog.resolve(memory_field(memory, "avoids", []) or []),
                ]
            )
        )
        status = "ready" if output.status == "clarification" else output.status
        canonical = ExplorerOutput.model_validate(
            {
                **output.model_dump(mode="python"),
                "status": status,
                "input_adm": destination,
                "places": places or None,
                "days": days,
                "budget": budget,
                "people": people,
                "short_preferences": preferences,
                "short_avoids": avoids,
                "clarification_question": None,
            }
        )
        payload = PlaceCheckerInput.model_validate(
            {
                "inputADM": canonical.input_adm,
                "places": self._places(
                    canonical.places or [], canonical.url_notes or []
                ),
                "inputItems": [
                    {
                        "name": item.name,
                        "itemType": item.item_type,
                        "relatedPlaceName": item.related_place_name,
                    }
                    for item in canonical.input_items or []
                ],
                "days": canonical.days,
                "budget": self._place_checker_budget(canonical),
                "people": canonical.people,
                "shortPreferences": canonical.short_preferences,
                "shortAvoids": canonical.short_avoids,
                "specialNotes": canonical.special_notes,
            }
        )
        return ExplorerHandoff(canonical, payload)

    @classmethod
    def _days(cls, output, raw_prompt, memory, has_source_input) -> int:
        remembered = memory_field(memory, "duration_days")
        has_new_intake = bool(has_source_input or output.places or output.input_items)
        if remembered and not cls._DAYS.search(raw_prompt) and not has_new_intake:
            return remembered
        return output.days

    @classmethod
    def _people(cls, output, raw_prompt, memory):
        remembered = memory_field(memory, "travelers")
        if remembered and not cls._PEOPLE.search(raw_prompt):
            return output.people.model_copy(
                update={"adults": remembered, "children": 0, "infants": 0}
            )
        return output.people

    @staticmethod
    def _budget(output, memory):
        remembered = memory_field(memory, "budget")
        if (
            output.budget.source == "default"
            and isinstance(remembered, str)
            and remembered in {"low", "medium", "high"}
        ):
            return output.budget.model_copy(update={"level": remembered})
        return output.budget

    def _place_checker_budget(self, output: ExplorerOutput) -> dict:
        amount = output.budget.target_amount
        currency = output.budget.currency
        if amount is not None and output.budget.basis == "group_total":
            amount = normalize_budget_per_person(
                output.budget, output.people
            ).target_amount
        if amount is None and output.input_adm:
            estimate = self.budget_estimator.estimate(
                destination=output.input_adm,
                level=output.budget.level,
                people=output.people.total,
                days=output.days,
            )
            if estimate is not None:
                amount = estimate.total_per_person
                currency = estimate.daily_cost.currency
        return {
            "amountPerPerson": amount,
            "currency": currency,
            "level": output.budget.level,
        }

    @classmethod
    def _places(cls, places, notes) -> list[dict]:
        return [
            {
                "name": place.name,
                "sourcePlaces": cls._source_places(place, notes),
                "latitude": None,
                "longitude": None,
            }
            for place in places
        ]

    @classmethod
    def _source_places(cls, place, notes) -> list[dict]:
        result: list[dict] = []
        positions: dict[tuple, int] = {}
        for source in place.source_places:
            evidence_type = "url" if source.origin == "url" else "raw_prompt"
            source_url = source.source_url if source.origin == "url" else None
            item = {
                "evidenceType": evidence_type,
                "sourceUrl": source_url,
                "sourceTimeHint": source.source_time_hint,
                "addressHint": source.address_hint or place.address_hint,
                "urlNotes": [
                    {"summary": note.summary}
                    for note in cls._notes_for_source(place, source, notes)
                ],
            }
            signature = (
                evidence_type,
                source_url,
                source.source_time_hint,
                item["addressHint"],
            )
            if signature not in positions:
                positions[signature] = len(result)
                result.append(item)
                continue
            stored = result[positions[signature]]
            stored["urlNotes"] = list(
                {
                    note["summary"]: note
                    for note in [*stored["urlNotes"], *item["urlNotes"]]
                }.values()
            )
        return result

    @staticmethod
    def _notes_for_source(place, source, notes) -> list:
        place_key = place_name_key(place.name)
        result = []
        seen = set()
        for note in notes:
            note_place = place_name_key(note.place_name or "")
            summary_key = place_name_key(note.summary)
            if note_place != place_key and place_key not in summary_key:
                continue
            source_is_url = source.origin == "url"
            if (note.source_url is not None) != source_is_url:
                continue
            if source_is_url and note.source_url != source.source_url:
                continue
            signature = (summary_key, note.source_url)
            if signature not in seen:
                result.append(note)
                seen.add(signature)
        return result


def explorer_output_to_intent(output: ExplorerOutput) -> TripIntent:
    return TripIntent(
        destination=output.input_adm,
        days=output.days,
        budget=(
            float(output.budget.target_amount) if output.budget.target_amount else None
        ),
        people=output.people.total,
        preferences=output.short_preferences,
        avoids=output.short_avoids,
    )
