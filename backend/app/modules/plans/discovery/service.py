from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict
from statistics import median
from typing import Protocol

from app.modules.places.model import Place
from app.modules.plans.discovery.schema import (
    DestinationDiscoveryRequest,
    DestinationDiscoveryResponse,
    DestinationProposal,
)
from app.modules.plans.knowledge_graph import (
    TravelKnowledgeSearchTool,
    get_default_travel_knowledge_tool,
)
from app.modules.plans.planner.place_metadata import (
    read_daily_cost,
    read_place_group,
    read_tags,
)


PACE_ACTIVITY_COUNT = {
    "relaxed": 2,
    "balanced": 3,
    "packed": 5,
}

INTEREST_TERMS = {
    "am thuc": {"food", "food drink", "restaurant", "street food", "local food"},
    "food": {"food", "food drink", "restaurant", "street food", "local food"},
    "ca phe": {"cafe", "coffee", "coffee shop"},
    "coffee": {"cafe", "coffee", "coffee shop"},
    "van hoa": {"culture", "heritage", "museum", "temple", "attraction"},
    "culture": {"culture", "heritage", "museum", "temple", "attraction"},
    "lich su": {"history", "historic", "heritage", "museum", "monument"},
    "thien nhien": {"nature", "park", "garden", "mountain", "waterfall"},
    "nature": {"nature", "park", "garden", "mountain", "waterfall"},
    "bien": {"beach", "coast", "seaside"},
    "beach": {"beach", "coast", "seaside"},
    "mua sam": {"shopping", "market", "mall"},
    "shopping": {"shopping", "market", "mall"},
    "nightlife": {"nightlife", "bar", "pub", "nightclub"},
    "thu gian": {"wellness", "spa", "park", "garden", "relaxation"},
    "adventure": {"adventure", "hiking", "trekking", "camping"},
}


class DestinationDiscoveryPlaceRepository(Protocol):
    def list_active_for_destination_discovery(
        self,
        *,
        limit: int = 50_000,
    ) -> list[Place]: ...


class DestinationDiscoveryService:
    """Rank destination regions before the user enters the Planner pipeline.

    Cost is intentionally limited to catalog activities. Transport and lodging
    need dedicated providers and are never silently presented as verified here.
    """

    def __init__(
        self,
        repository: DestinationDiscoveryPlaceRepository,
        *,
        knowledge_tool: TravelKnowledgeSearchTool | None = None,
        min_catalog_places: int = 5,
    ) -> None:
        self.repository = repository
        self.knowledge_tool = knowledge_tool or get_default_travel_knowledge_tool()
        self.min_catalog_places = min_catalog_places

    def discover(
        self,
        request: DestinationDiscoveryRequest,
    ) -> DestinationDiscoveryResponse:
        places = self.repository.list_active_for_destination_discovery()
        grouped: dict[str, list[Place]] = defaultdict(list)
        for place in places:
            root = _destination_region_key(place.region_key)
            if root is not None:
                grouped[root].append(place)

        eligible = {
            region_key: region_places
            for region_key, region_places in grouped.items()
            if len(region_places) >= self.min_catalog_places
        }
        if not eligible:
            return DestinationDiscoveryResponse(
                warnings=["Catalog chưa có khu vực đủ dữ liệu để đề xuất điểm đến."],
            )

        max_count = max(len(region_places) for region_places in eligible.values())
        proposals = [
            self._proposal(
                request,
                region_key,
                region_places,
                max_catalog_count=max_count,
            )
            for region_key, region_places in eligible.items()
        ]
        proposals.sort(
            key=lambda proposal: (
                -proposal.score,
                -proposal.matching_place_count,
                -proposal.catalog_place_count,
                proposal.region_key,
            )
        )

        assumptions = [
            "Ước tính hiện chỉ bao gồm chi phí activity suy ra từ Place catalog.",
        ]
        if request.origin_region_key is None:
            assumptions.append(
                "Chưa có nơi xuất phát nên chưa tính chi phí và thời gian di chuyển đến điểm đến."
            )
        else:
            assumptions.append(
                "Đã nhận nơi xuất phát nhưng chưa dùng để chấm khoảng cách khi chưa có travel-cost provider."
            )
        if not request.interests:
            assumptions.append(
                "Chưa có sở thích cụ thể nên đề xuất ưu tiên độ phủ và chất lượng catalog."
            )
        warnings = []
        if request.budget_includes_transport:
            warnings.append(
                "Ngân sách có gồm di chuyển nhưng chưa có transport-cost provider để kiểm chứng."
            )
        if request.budget_includes_accommodation:
            warnings.append(
                "Ngân sách có gồm lưu trú nhưng chưa có accommodation-cost provider để kiểm chứng."
            )
        return DestinationDiscoveryResponse(
            proposals=proposals[: request.limit],
            assumptions=assumptions,
            warnings=warnings,
        )

    def _proposal(
        self,
        request: DestinationDiscoveryRequest,
        region_key: str,
        places: list[Place],
        *,
        max_catalog_count: int,
    ) -> DestinationProposal:
        matched_by_interest = {
            interest: [place for place in places if _matches_interest(place, interest)]
            for interest in request.interests
        }
        matched_interests = [
            interest for interest, matches in matched_by_interest.items() if matches
        ]
        matching_places = list(
            {
                place.id: place
                for matches in matched_by_interest.values()
                for place in matches
            }.values()
        )
        cost_basis = matching_places or places
        costs = [
            cost
            for place in cost_basis
            if (cost := read_daily_cost(place)) is not None
        ]
        estimated_cost = None
        if costs:
            activity_count = PACE_ACTIVITY_COUNT[request.pace.value]
            estimated_cost = int(median(costs) * activity_count * request.days)

        budget_amount = request.budget.target_amount or 0
        if estimated_cost is None:
            budget_fit = "uncertain"
            budget_score = 0.5
        elif estimated_cost <= budget_amount:
            budget_fit = "fits"
            budget_score = 1.0
        else:
            budget_fit = "exceeds"
            budget_score = max(0.0, min(1.0, budget_amount / estimated_cost))

        coverage_score = math.log1p(len(places)) / math.log1p(max_catalog_count)
        interest_score = (
            len(matched_interests) / len(request.interests)
            if request.interests
            else 0.75
        )
        score = round(
            min(1.0, 0.4 * coverage_score + 0.35 * interest_score + 0.25 * budget_score),
            4,
        )
        price_coverage = len(costs) / len(cost_basis) if cost_basis else 0.0
        confidence = (
            "high"
            if len(places) >= 20 and price_coverage >= 0.5
            else "medium"
            if len(places) >= 10 and price_coverage >= 0.2
            else "low"
        )
        graph_available = self.knowledge_tool.supports_region(region_key)
        warnings = []
        if estimated_cost is None:
            warnings.append("Catalog chưa đủ price evidence để ước tính activity cost.")
        if not graph_available:
            warnings.append(
                "Knowledge Graph chưa phủ khu vực này; macro planning sẽ chỉ có catalog fallback."
            )

        reasons = [f"Catalog có {len(places)} Place active."]
        if matched_interests:
            reasons.append(
                "Có dữ liệu phù hợp với: " + ", ".join(matched_interests) + "."
            )
        if budget_fit == "fits":
            reasons.append("Activity cost ước tính nằm trong ngân sách đã khai báo.")

        return DestinationProposal(
            regionKey=region_key,
            destination=_destination_name(places, region_key),
            score=score,
            catalogPlaceCount=len(places),
            matchingPlaceCount=len(matching_places),
            matchedInterests=matched_interests,
            estimatedCatalogActivityCost=estimated_cost,
            budgetFit=budget_fit,
            dataConfidence=confidence,
            knowledgeGraphAvailable=graph_available,
            reasons=reasons,
            warnings=warnings,
        )


def _destination_region_key(region_key: str) -> str | None:
    parts = [part for part in region_key.split(",") if part]
    if len(parts) < 2 or parts[0] != "vn" or parts[1] == "unmapped":
        return None
    return ",".join(parts[:2])


def _destination_name(places: list[Place], region_key: str) -> str:
    names = Counter(
        place.city.strip()
        for place in places
        if isinstance(place.city, str) and place.city.strip()
    )
    if names:
        return names.most_common(1)[0][0]
    return region_key.split(",")[-1].replace("-", " ").title()


def _matches_interest(place: Place, interest: str) -> bool:
    needle = _normalize(interest)
    if not needle:
        return False
    needles = {needle, *INTEREST_TERMS.get(needle, set())}
    values = [
        place.name,
        place.place_type,
        read_place_group(place) or "",
        *read_tags(place),
    ]
    normalized_values = [_normalize(str(value)) for value in values if value]
    return any(
        candidate in value or value in candidate
        for candidate in needles
        for value in normalized_values
    )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return " ".join(
        "".join(character if character.isalnum() else " " for character in without_marks).split()
    )
