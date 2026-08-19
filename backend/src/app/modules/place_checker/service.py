import re
import unicodedata

from app.modules.place_checker.contract import (
    BudgetMode,
    CapacityRange,
    PlaceCheckerInput,
    PlaceCheckerOutput,
    TravelPace,
    TripEvaluationContext,
)
from app.modules.place_checker.ports import AdmResolver, PlaceDiscovery, PlaceResolver
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace


class TripContextBuilder:
    _DAILY_CAPACITY = {
        TravelPace.slow: 360,
        TravelPace.balanced: 480,
        TravelPace.fast: 600,
    }

    def __init__(self, adm_resolver: AdmResolver) -> None:
        self.adm_resolver = adm_resolver

    async def build(
        self,
        payload: PlaceCheckerInput,
        *,
        pace: TravelPace = TravelPace.balanced,
    ) -> TripEvaluationContext:
        input_name = self._normalize_text(payload.input_adm)
        destination = await self.adm_resolver.resolve(input_name)
        if destination.input_name != input_name:
            destination = destination.model_copy(update={"input_name": input_name})

        minimum = self._DAILY_CAPACITY[TravelPace.slow] * payload.days
        typical = self._DAILY_CAPACITY[pace] * payload.days
        maximum = self._DAILY_CAPACITY[TravelPace.fast] * payload.days
        return TripEvaluationContext(
            destination=destination,
            days=payload.days,
            pace=pace,
            capacity=CapacityRange(
                minimum_minutes=minimum,
                typical_minutes=typical,
                maximum_minutes=maximum,
            ),
            budget_mode=(
                BudgetMode.target_amount
                if payload.budget.target_amount is not None
                else BudgetMode.relative_level
            ),
            budget=payload.budget,
            people=payload.people,
            preferences=self._normalize_labels(payload.short_preferences),
            avoids=self._normalize_labels(payload.short_avoids),
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _normalize_labels(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = cls._normalize_text(value).casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result


class PlaceCheckerService:
    def __init__(self, resolver: PlaceResolver, discovery: PlaceDiscovery) -> None:
        self.resolver = resolver
        self.discovery = discovery

    @staticmethod
    def required_count(days: int) -> int:
        return max(2, days * 2)

    async def check(self, payload: PlaceCheckerInput) -> PlaceCheckerOutput:
        intent = payload.intent
        resolved: list[VerifiedPlace] = []
        rejected: list[PlaceCandidate] = []
        seen: set[str] = set()

        for candidate in payload.candidates:
            place = await self.resolver.resolve(candidate, intent)
            if place is None:
                rejected.append(candidate)
                continue
            identity = place.place_id.casefold()
            if identity not in seen:
                seen.add(identity)
                resolved.append(place)

        required = self.required_count(intent.days)
        if len(resolved) < required:
            discovered = await self.discovery.discover(
                intent,
                required - len(resolved),
            )
            for place in discovered:
                if place.place_id.casefold() not in seen:
                    seen.add(place.place_id.casefold())
                    resolved.append(place)

        unverified_count = sum(not place.verified for place in resolved)
        warnings = []
        if unverified_count:
            warnings.append(
                f"{unverified_count} place(s) require verification by a real provider."
            )
        status = "sufficient" if len(resolved) >= required else "insufficient"
        return PlaceCheckerOutput(
            places=resolved,
            rejected_candidates=rejected,
            coverage_status=status,
            warnings=warnings,
        )
