from __future__ import annotations

import re
import unicodedata
from typing import Protocol

from pydantic import BaseModel, Field

from app.modules.places.model import Place


DESCRIPTION_RETRIEVAL_MULTIPLIER = 10
MIN_DESCRIPTION_RETRIEVAL_LIMIT = 50
MAX_REPOSITORY_CANDIDATES = 10000

SEMANTIC_CATEGORY_TERMS: dict[str, set[str]] = {
    "accommodation": {
        "accommodation",
        "checkin",
        "homestay",
        "hostel",
        "hotel",
        "luu tru",
        "nghi dem",
    },
    "attraction": {
        "architecture",
        "attraction",
        "culture",
        "di tich",
        "heritage",
        "historic",
        "history",
        "museum",
        "sightseeing",
        "temple",
        "van hoa",
    },
    "entertainment": {
        "amusement",
        "cinema",
        "entertainment",
        "giai tri",
        "nightlife",
        "theatre",
    },
    "food_drink": {
        "am thuc",
        "cafe",
        "coffee",
        "culinary",
        "cuisine",
        "food",
        "hai san",
        "restaurant",
        "seafood",
    },
    "nature": {
        "beach",
        "bien",
        "coast",
        "dao",
        "forest",
        "garden",
        "hiking",
        "island",
        "mountain",
        "nature",
        "park",
        "peak",
        "trekking",
        "thien nhien",
        "ven bien",
        "vuon quoc gia",
    },
    "shopping": {
        "cho",
        "mall",
        "market",
        "marketplace",
        "mua sam",
        "shopping",
    },
}

PLACE_GROUP_CATEGORY: dict[str, str] = {
    "accommodation": "accommodation",
    "attraction": "attraction",
    "entertainment": "entertainment",
    "experience": "attraction",
    "food_drink": "food_drink",
    "shopping": "shopping",
    "wellness": "entertainment",
}

PLACE_TYPE_CATEGORY: dict[str, str] = {
    "aerodrome": "transport",
    "apartment": "accommodation",
    "bakery": "food_drink",
    "bar": "food_drink",
    "beach": "nature",
    "biergarten": "food_drink",
    "bus_station": "transport",
    "cafe": "food_drink",
    "camp_site": "nature",
    "cave_entrance": "nature",
    "cinema": "entertainment",
    "coffee": "food_drink",
    "fast_food": "food_drink",
    "ferry_terminal": "transport",
    "food_court": "food_drink",
    "garden": "nature",
    "guest_house": "accommodation",
    "hostel": "accommodation",
    "hotel": "accommodation",
    "ice_cream": "food_drink",
    "marketplace": "shopping",
    "marina": "transport",
    "motel": "accommodation",
    "nature_reserve": "nature",
    "nightclub": "entertainment",
    "park": "nature",
    "peak": "nature",
    "pub": "food_drink",
    "restaurant": "food_drink",
    "station": "transport",
    "supermarket": "shopping",
    "theatre": "entertainment",
    "wetland": "nature",
    "wilderness_hut": "nature",
    "wood": "nature",
}


class FinderPlace(BaseModel):
    place_id: str | None = Field(default=None, alias="placeId")
    name: str
    address: str | None = None
    place_type: str = Field(alias="placeType")
    region_key: str = Field(alias="regionKey")
    description: str | None = None
    place_group: str | None = Field(default=None, alias="placeGroup")
    tags: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    typical_duration_minutes: int | None = Field(
        default=None,
        alias="typicalDurationMinutes",
    )
    minimum_duration_minutes: int | None = Field(
        default=None,
        alias="minimumDurationMinutes",
    )
    activity_intensity: str | None = Field(
        default=None,
        alias="activityIntensity",
    )
    must_visit: bool = Field(default=False, alias="mustVisit")
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")
    accessibility_features: list[str] = Field(
        default_factory=list,
        alias="accessibilityFeatures",
    )
    opening_hours: list[dict] = Field(default_factory=list, alias="openingHours")
    weather_sensitivity: str | None = Field(default=None, alias="weatherSensitivity")
    price_level: str | None = Field(default=None, alias="priceLevel")
    data_confidence: str = Field(default="low", alias="dataConfidence")
    source_order: int | None = Field(default=None, ge=1, alias="sourceOrder")
    source_day: int | None = Field(default=None, ge=1, le=30, alias="sourceDay")
    source_time_hint: str | None = Field(default=None, alias="sourceTimeHint")
    source_activity: str | None = Field(default=None, alias="sourceActivity")
    source_duration_minutes: int | None = Field(
        default=None,
        ge=15,
        le=720,
        alias="sourceDurationMinutes",
    )

    model_config = {"populate_by_name": True}

    @property
    def stable_ref(self) -> str:
        return self.place_id or self.name


class FinderPlaceTool(Protocol):
    def get(self, place_id: str) -> FinderPlace | None: ...

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]: ...


class FinderPlaceRepository(Protocol):
    def get(self, place_id: str) -> Place | None: ...

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]: ...


class EmptyFinderPlaceTool:
    def get(self, place_id: str) -> FinderPlace | None:
        return None

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        return []


class RepositoryFinderPlaceTool:
    def __init__(self, repository: FinderPlaceRepository) -> None:
        self.repository = repository
        self._scope_cache: dict[str, list[FinderPlace]] = {}

    def get(self, place_id: str) -> FinderPlace | None:
        place = self.repository.get(place_id)
        if place is None or place.deleted_at is not None:
            return None
        return self._to_finder_place(place)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        places = self._load_scoped_candidates(region_key, excluded_place_ids)
        places = [
            place
            for place in places
            if _matches_target_locality(place, region_key)
        ]
        if not places:
            return []

        query_terms = _normalized_terms(target_tags)
        query_categories = semantic_categories(query_terms)
        description_ranked = sorted(
            places,
            key=lambda place: (
                -_description_relevance(place.description, query_terms),
                place.name.casefold(),
            ),
        )
        retrieval_limit = max(
            MIN_DESCRIPTION_RETRIEVAL_LIMIT,
            limit * DESCRIPTION_RETRIEVAL_MULTIPLIER,
        )
        if any(
            _description_relevance(place.description, query_terms) > 0
            for place in description_ranked
        ):
            shortlisted = description_ranked[:retrieval_limit]
        else:
            shortlisted = places

        eligible_shortlist = [
            place
            for place in shortlisted
            if place_matches_categories(place, query_categories)
        ]
        if not eligible_shortlist:
            eligible_shortlist = [
                place
                for place in places
                if place_matches_categories(place, query_categories)
            ]
        shortlisted = eligible_shortlist
        shortlisted.sort(
            key=lambda place: (
                -_structured_rerank_score(
                    place,
                    region_key=region_key,
                    query_terms=query_terms,
                    query_categories=query_categories,
                ),
                -_description_relevance(place.description, query_terms),
                place.name.casefold(),
            )
        )
        return shortlisted[:limit]

    def _load_scoped_candidates(
        self,
        region_key: str,
        excluded_place_ids: set[str],
    ) -> list[FinderPlace]:
        candidates: list[FinderPlace] = []
        seen: set[str] = set()
        for scope in _region_scopes(region_key):
            if scope not in self._scope_cache:
                self._scope_cache[scope] = [
                    self._to_finder_place(place)
                    for place in self.repository.list_for_finder(
                        scope,
                        limit=MAX_REPOSITORY_CANDIDATES,
                    )
                ]
            for place in self._scope_cache[scope]:
                if (
                    place.place_id in excluded_place_ids
                    or place.stable_ref in seen
                ):
                    continue
                seen.add(place.stable_ref)
                candidates.append(place)
        return candidates

    def _to_finder_place(self, place: Place) -> FinderPlace:
        metadata = place.metadata_json or {}
        tags = metadata.get("tags", [])
        return FinderPlace(
            placeId=place.id,
            name=place.name,
            address=place.address,
            placeType=place.place_type,
            regionKey=place.region_key,
            description=(
                str(metadata.get("description"))
                if metadata.get("description") is not None
                else None
            ),
            placeGroup=(
                str(metadata.get("placeGroup"))
                if metadata.get("placeGroup") is not None
                else None
            ),
            tags=[
                str(tag)
                for tag in tags
                if isinstance(tag, str)
            ],
            latitude=(
                float(place.latitude) if place.latitude is not None else None
            ),
            longitude=(
                float(place.longitude) if place.longitude is not None else None
            ),
            typicalDurationMinutes=place.typical_duration_minutes,
            minimumDurationMinutes=_minimum_duration_minutes(metadata),
            activityIntensity=metadata.get("activityIntensity"),
            accessibilityFeatures=[
                str(feature)
                for feature in metadata.get("accessibilityFeatures", [])
                if isinstance(feature, str)
            ],
            openingHours=list(place.opening_hours or []),
            weatherSensitivity=(
                str(metadata.get("weatherSensitivity"))
                if metadata.get("weatherSensitivity") is not None
                else None
            ),
            priceLevel=(
                str(metadata.get("priceLevel"))
                if metadata.get("priceLevel") is not None
                else None
            ),
            dataConfidence=place.data_confidence,
        )


def semantic_categories(terms: set[str]) -> set[str]:
    normalized_terms = _normalized_terms(list(terms))
    joined = " ".join(sorted(normalized_terms))
    return {
        category
        for category, markers in SEMANTIC_CATEGORY_TERMS.items()
        if any(
            marker in normalized_terms
            or f" {marker} " in f" {joined} "
            for marker in markers
        )
    }


def place_category(place: FinderPlace) -> str | None:
    normalized_name = _normalize_text(place.name)
    if re.search(
        r"(^| )(ga|station|terminal|ben pha)( |$)",
        normalized_name,
    ):
        return "transport"
    place_type = _normalize_text(place.place_type).replace(" ", "_")
    if place_type in PLACE_TYPE_CATEGORY:
        return PLACE_TYPE_CATEGORY[place_type]
    group = _normalize_text(place.place_group or "")
    if group in PLACE_GROUP_CATEGORY:
        return PLACE_GROUP_CATEGORY[group]
    values = _normalized_terms([place.place_type, *place.tags])
    categories = semantic_categories(values)
    return sorted(categories)[0] if categories else None


def _description_relevance(
    description: str | None,
    query_terms: set[str],
) -> int:
    if not description or not query_terms:
        return 0
    description_text = _normalize_text(description)
    description_terms = set(description_text.split())
    token_overlap = len(query_terms.intersection(description_terms))
    phrase_overlap = sum(
        1
        for term in query_terms
        if " " in term and term in description_text
    )
    return token_overlap + (phrase_overlap * 2)


def _structured_rerank_score(
    place: FinderPlace,
    *,
    region_key: str,
    query_terms: set[str],
    query_categories: set[str],
) -> int:
    place_terms = _normalized_terms(
        [place.name, place.place_type, place.place_group or "", *place.tags]
    )
    tag_overlap = len(query_terms.intersection(place_terms))
    category = place_category(place)
    category_score = {
        "accommodation": -60,
        "attraction": 40,
        "entertainment": 30,
        "food_drink": 0,
        "nature": 40,
        "shopping": 20,
    }.get(category or "", 0)
    if query_categories:
        category_score = 60 if category in query_categories else -35
    region_score = (
        25
        if place.region_key == region_key
        else 20
        if place.region_key.startswith(f"{region_key},")
        else 5
    )
    confidence_score = {
        "high": 10,
        "medium": 5,
        "low": 0,
    }.get(place.data_confidence.casefold(), 0)
    coordinate_score = (
        3
        if place.latitude is not None and place.longitude is not None
        else 0
    )
    return (
        _description_relevance(place.description, query_terms) * 18
        + category_score
        + tag_overlap * 12
        + region_score
        + confidence_score
        + coordinate_score
    )


def place_matches_categories(
    place: FinderPlace,
    query_categories: set[str],
) -> bool:
    category = place_category(place)
    if category == "accommodation" and "accommodation" not in query_categories:
        return False
    if not query_categories:
        return True
    if category is None:
        return False
    if category in query_categories:
        return True
    if category != "attraction":
        return False
    evidence_categories = semantic_categories(
        _normalized_terms(
            [
                place.name,
                place.description or "",
                place.place_type,
                *place.tags,
            ]
        )
    )
    return bool(
        evidence_categories.intersection(
            query_categories.intersection({"entertainment", "nature"})
        )
    )


def _matches_target_locality(
    place: FinderPlace,
    target_region_key: str,
) -> bool:
    if (
        place.region_key == target_region_key
        or place.region_key.startswith(f"{target_region_key},")
    ):
        return True
    parts = target_region_key.split(",")
    if len(parts) <= 2:
        return True
    locality = _normalize_text(parts[-1])
    locality_tokens = [
        token
        for token in locality.split()
        if token not in {"district", "town", "ward"}
    ]
    locality_phrase = " ".join(locality_tokens)
    if not locality_phrase:
        return True
    searchable = _normalize_text(
        f"{place.name} {place.description or ''}"
    )
    if locality_phrase in searchable:
        return True
    city_tokens = set(_normalize_text(parts[1]).split())
    distinctive_tokens = {
        token
        for token in locality_tokens
        if len(token) >= 3 and token not in city_tokens
    }
    return bool(distinctive_tokens.intersection(searchable.split()))


def _minimum_duration_minutes(metadata: dict) -> int | None:
    duration_range = metadata.get("recommendedDurationRange")
    if not isinstance(duration_range, dict):
        return None
    value = duration_range.get("minMinutes")
    if isinstance(value, int) and value > 0:
        return value
    return None


def _normalized_terms(values: list[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        if not normalized:
            continue
        terms.add(normalized)
        terms.update(
            token
            for token in normalized.split()
            if len(token) > 2
        )
    return terms


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _region_scopes(region_key: str) -> list[str]:
    parts = region_key.split(",")
    return [
        ",".join(parts[:length])
        for length in range(len(parts), 1, -1)
    ]
