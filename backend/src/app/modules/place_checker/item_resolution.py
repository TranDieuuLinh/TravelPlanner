from __future__ import annotations

import asyncio

from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.contract import (
    AdmResolutionStatus,
    InputItem,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import ItemResolutionStatus
from app.modules.place_checker.errors import PlaceCatalogUnavailableError
from app.modules.place_checker.item_contract import (
    ItemPlaceOption,
    ItemResolutionBatch,
    ResolvedInputItem,
    SpecialExperience,
)
from app.modules.place_checker.item_option_enrichment import apply_metadata
from app.modules.place_checker.item_proximity import ItemProximityPolicy
from app.modules.place_checker.item_selection import (
    selected_confidence,
    selection_reason,
)
from app.modules.place_checker.ports import (
    NamedPlaceSearchTool,
    PlaceMetadataRepository,
)
from app.modules.place_checker.price_policy import has_usable_cost
from app.modules.place_checker.resolution_contract import (
    EnrichedIdentityPlace,
)
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceSearchMatch,
    PlaceSearchRequest,
    PlaceSearchResult,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.policy import PlaceSearchPolicy

ITEM_TYPE_HINTS = {
    "food": "restaurant",
    "meal": "restaurant",
    "drink": "cafe",
    "coffee": "cafe",
    "accommodation": "hotel",
    "activity": "travel_place",
    "experience": "travel_place",
    "attraction": "travel_place",
}
SPECIAL_EXPERIENCE_TYPES = {"activity", "experience"}
# Keep item pools compact: one selected venue plus three alternatives gives
# the downstream planner choice without flooding the place pool.
MAX_ALTERNATIVES = 3


class InputItemResolutionService:
    def __init__(
        self,
        search_tool: NamedPlaceSearchTool,
        *,
        metadata_repository: PlaceMetadataRepository | None = None,
        policy: PlaceSearchPolicy | None = None,
        max_concurrency: int = 10,
    ) -> None:
        self.search_tool = search_tool
        self.metadata_repository = metadata_repository
        self.policy = policy or PlaceSearchPolicy(requirement_acceptance_score=0.5)
        self.max_concurrency = max(1, max_concurrency)

    async def resolve_all(
        self,
        items: list[InputItem],
        context: TripEvaluationContext,
        related_places: list[EnrichedIdentityPlace] | None = None,
    ) -> ItemResolutionBatch:
        if context.destination.status != AdmResolutionStatus.resolved:
            warning = "Không thể phân giải item khi destination ADM chưa rõ."
            return ItemResolutionBatch(
                items=[self._unresolved(index, item, warning) for index, item in enumerate(items)],
                warnings=[warning],
            )
        places = related_places or []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(index, item):
            async with semaphore:
                return await self._resolve_one(index, item, context, places)

        results = await asyncio.gather(
            *(bounded(index, item) for index, item in enumerate(items))
        )
        warnings = list(
            dict.fromkeys(
                warning
                for result in results
                for warning in result.warnings
                if result.selection_reason in {
                    "knowledge_graph_provider_error",
                    "search_places_unexpected_error",
                }
            )
        )
        return ItemResolutionBatch(items=list(results), warnings=warnings)

    async def _resolve_one(
        self,
        index: int,
        item: InputItem,
        context: TripEvaluationContext,
        related_places: list[EnrichedIdentityPlace],
    ) -> ResolvedInputItem:
        related = ItemProximityPolicy.related_place(item, related_places)
        direct = ItemProximityPolicy.direct_option(item, related)
        if direct is not None and self._has_usable_cost(direct):
            return self._direct_result(index, item, direct)
        anchor = ItemProximityPolicy.anchor(related, related_places)
        anchor_place_id = (
            related.place_id
            if related is not None
            else next(
                (
                    place.place_id
                    for place in related_places
                    if place.place_id and place.metadata and place.metadata.coordinates
                ),
                None,
            )
        )
        try:
            result = await self.search_tool.search(
                self._request(item, context, anchor, anchor_place_id)
            )
        except Exception:  # noqa: BLE001 - provider boundary becomes unresolved
            return self._unresolved(
                index,
                item,
                "Công cụ search_places gặp lỗi không xác định.",
                reason="search_places_unexpected_error",
            )
        return await self._map_result(
            index,
            item,
            context,
            result,
            anchor=anchor,
            strict_proximity=related is not None,
        )

    @staticmethod
    def _request(
        item: InputItem,
        context: TripEvaluationContext,
        anchor: Coordinates | None = None,
        anchor_place_id: str | None = None,
    ) -> PlaceSearchRequest:
        destination = context.destination
        assert destination.adm_id is not None
        assert destination.canonical_name is not None
        assert destination.country_code is not None
        item_type = normalize_text(item.item_type)
        return PlaceSearchRequest(
            query=item.name,
            input_adm=AdministrativeArea(
                adm_id=destination.adm_id,
                name=destination.canonical_name,
                country_code=destination.country_code,
            ),
            search_mode="requirement",
            place_type_hint=ITEM_TYPE_HINTS.get(item_type),
            source_evidence=item.evidence[:500],
            previous_place=anchor,
            anchor_place_id=anchor_place_id,
            top_k=4,
            allow_external_fallback=False,
        )

    async def _map_result(
        self,
        index: int,
        item: InputItem,
        context: TripEvaluationContext,
        result: PlaceSearchResult,
        *,
        anchor: Coordinates | None,
        strict_proximity: bool,
    ) -> ResolvedInputItem:
        options = [
            option
            for match in result.top_matches
            if (option := self._option(match, anchor)) is not None
        ]
        metadata_warning = None
        try:
            options = await self._enrich_options(options)
        except PlaceCatalogUnavailableError:
            metadata_warning = "Place metadata catalog tạm thời không khả dụng."
        except Exception:  # noqa: BLE001 - metadata failure keeps partial result
            metadata_warning = "Không thể làm giàu metadata cho item venues."
        options = [
            ItemProximityPolicy.with_distance(option, anchor)
            for option in options
        ]
        eligible = [
            option
            for option in options
            if not option.rejection_reasons
            and self._has_usable_cost(option)
            and not has_avoid_conflict(
                context.avoids,
                [option.name, option.category or "", *option.tags],
            )
            and not self._people_conflict(option, context)
            and not ItemProximityPolicy.too_far(
                option,
                strict=strict_proximity,
            )
        ]
        eligible.sort(key=lambda option: ItemProximityPolicy.rank(option, context))
        selected = next(
            (
                option
                for option in eligible
                if option.score >= self.policy.requirement_acceptance_score
            ),
            None,
        )
        alternatives = [
            option for option in eligible if option != selected
        ][:MAX_ALTERNATIVES]
        if selected is not None:
            status = ItemResolutionStatus.resolved
        elif eligible:
            status = ItemResolutionStatus.partially_resolved
        else:
            status = ItemResolutionStatus.unresolved

        warnings: list[str] = []
        if metadata_warning:
            warnings.append(metadata_warning)
        if result.status == "provider_error":
            warnings.append("Knowledge Graph search tạm thời không khả dụng.")
        elif status == ItemResolutionStatus.partially_resolved:
            warnings.append("Có venue gần đúng nhưng chưa đủ điểm để tự chọn.")
        elif status == ItemResolutionStatus.unresolved:
            warnings.append("Không tìm thấy venue phù hợp cho requirement.")

        special = None
        if selected and normalize_text(item.item_type) in SPECIAL_EXPERIENCE_TYPES:
            special = SpecialExperience(
                requirement=normalize_text(item.name),
                action=normalize_text(item.action),
                anchor_place_id=selected.place_id,
                evidence=item.evidence,
            )
        return ResolvedInputItem(
            item_index=index,
            item=item,
            normalized_requirement=normalize_text(item.name),
            status=status,
            selected=selected,
            alternatives=alternatives,
            confidence=selected_confidence(item, selected, result),
            selection_reason=selection_reason(selected, result),
            evidence=item.evidence,
            special_experience=special,
            provider_attempts=result.provider_attempts,
            warnings=warnings,
        )

    async def _enrich_options(
        self,
        options: list[ItemPlaceOption],
    ) -> list[ItemPlaceOption]:
        if self.metadata_repository is None or not options:
            return options
        metadata = await self.metadata_repository.get_many(
            [option.place_id for option in options]
        )
        return [
            apply_metadata(option, metadata.get(option.place_id))
            for option in options
        ]

    @staticmethod
    def _option(
        match: PlaceSearchMatch,
        anchor: Coordinates | None,
    ) -> ItemPlaceOption | None:
        if match.place_id is None:
            return None
        option = ItemPlaceOption(
            place_id=match.place_id,
            name=match.name,
            provider=match.provider,
            provider_id=match.provider_id,
            category=match.canonical_type,
            address=match.address,
            coordinates=match.coordinates,
            tags=match.tags,
            rating=match.rating,
            review_count=match.review_count,
            score=match.score,
            rejection_reasons=[
                *match.rejection_reasons,
                *(
                    ["admin_review_required"]
                    if match.verification_status != "verified"
                    else []
                ),
            ],
            relationships=match.relationship_evidence,
        )
        return ItemProximityPolicy.with_distance(option, anchor)

    @staticmethod
    def _people_conflict(
        option: ItemPlaceOption,
        context: TripEvaluationContext,
    ) -> bool:
        return bool(
            (
                context.people.children > 0
                and option.children_suitable is False
            )
            or (
                context.people.infants > 0
                and option.infants_suitable is False
            )
        )

    @staticmethod
    def _has_usable_cost(option: ItemPlaceOption) -> bool:
        return has_usable_cost(
            minimum=option.minimum_cost,
            typical=option.typical_cost,
            maximum=option.maximum_cost,
            tier=option.cost_tier,
        )

    @staticmethod
    def _direct_result(
        index: int,
        item: InputItem,
        option: ItemPlaceOption,
    ) -> ResolvedInputItem:
        special = None
        if normalize_text(item.item_type) in SPECIAL_EXPERIENCE_TYPES:
            special = SpecialExperience(
                requirement=normalize_text(item.name),
                action=normalize_text(item.action),
                anchor_place_id=option.place_id,
                evidence=item.evidence,
            )
        return ResolvedInputItem(
            item_index=index,
            item=item,
            normalized_requirement=normalize_text(item.name),
            status=ItemResolutionStatus.resolved,
            selected=option,
            confidence=round(item.confidence * option.score, 6),
            selection_reason="related_place_direct_match",
            evidence=item.evidence,
            special_experience=special,
        )

    @staticmethod
    def _unresolved(
        index: int,
        item: InputItem,
        warning: str,
        *,
        reason: str = "destination_unresolved",
    ) -> ResolvedInputItem:
        return ResolvedInputItem(
            item_index=index,
            item=item,
            normalized_requirement=normalize_text(item.name),
            status=ItemResolutionStatus.unresolved,
            selection_reason=reason,
            evidence=item.evidence,
            warnings=[warning],
        )
