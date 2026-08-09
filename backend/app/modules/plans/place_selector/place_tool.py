from __future__ import annotations

import logging
import re
import unicodedata
from math import log10
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.modules.knowledge_graph.ontology import (
    KnowledgePlaceType,
    canonical_place_node_type,
)
from app.modules.plans.domain.entities import ExperienceCategory, PreferredTimeWindow
from app.modules.plans.domain.plan_notes import PlanNoteSource
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.trip_theme_planner.place_metadata import (
    GOOGLE_TYPES_CATEGORY,
    read_description,
    read_price_level,
    read_rating,
    read_review_count,
    read_tags,
)


DESCRIPTION_RETRIEVAL_MULTIPLIER = 10
MIN_DESCRIPTION_RETRIEVAL_LIMIT = 50
MAX_REPOSITORY_CANDIDATES = 10000

logger = logging.getLogger(__name__)

SEMANTIC_CATEGORY_TERMS: dict[str, set[str]] = {
    "accommodation": {
        "accommodation",
        "checkin",
        "homestay",
        "hostel",
        "hotel",
        "luu tru",
        "nghi dem",
        "khach san",
        "nha nghi",
        "resort",
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
        "chua",
        "den",
        "mieu",
        "dinh",
        "lang",
        "bao tang",
        "nha tu",
        "tuong",
        "quan the",
        "monument",
        "landmark",
        "di san",
        "co do",
        "thanh pho",
        "tham quan",
    },
    "entertainment": {
        "amusement",
        "cinema",
        "entertainment",
        "giai tri",
        "nightlife",
        "theatre",
        "giai tri",
        "rap phim",
        "rap",
        "karaoke",
        "vui choi",
        "giai tri",
        "khu vui choi",
        "bar",
        "pub",
        "club",
        "nightclub",
        "spa",
        "massage",
        "gym",
        "tap gym",
        "stadium",
        "san van dong",
        "casino",
        "golf",
        "san golf",
        "bowling",
    },
    "Restaurant": {
        "am thuc",
        "culinary",
        "cuisine",
        "food",
        "hai san",
        "restaurant",
        "seafood",
        "an",
        "an sang",
        "an trua",
        "an toi",
        "an vat",
        "do an",
        "thuc an",
        "mon an",
        "dac san",
        "dac san dia phuong",
        "mon dia phuong",
        "mon vung",
        "am thuc vung",
        "an sang",
        "an trua",
        "an toi",
        "nha hang",
        "quan an",
        "quan",
        "bep",
        "bep nha",
        "quan nho",
        "quan lon",
        "quan nhau",
        "pho",
        "bun",
        "com",
        "mien",
        "chao",
        "chao long",
        "chao ga",
        "mi quang",
        "hu tieu",
        "banh mi",
        "banh my",
        "banh xeo",
        "bun cha",
        "bun bo",
        "bun dau",
        "bun thang",
        "bun rieu",
        "bun oc",
        "oc",
        "com tam",
        "com ga",
        "com nieu",
        "banh cuon",
        "banh chung",
        "banh",
        "banh ngot",
        "tiem banh",
        "che",
        "che hat",
        "tra",
        "tra sua",
        "tra da",
        "nuoc",
        "nuoc uong",
        "do uong",
        "giai khat",
        "bia",
        "bia hoi",
        "ruou",
        "lau",
        "nuong",
        "do nuong",
        "thit nuong",
        "ga nuong",
        "hai san",
        "tom",
        "cua",
        "ca",
        "pho bo",
        "pho ga",
        "nem ran",
        "goi cuon",
        "nem",
        "nem chua",
        "dac san",
        "mon la",
        "mon noi tieng",
        "am thuc dan gian",
    },
    "DrinkDessert": {
        "cafe",
        "coffee",
        "coffee shop",
        "ca phe",
        "bakery",
        "cake",
        "dessert",
        "ice cream",
        "gelato",
        "bingsu",
        "che",
        "tea",
        "bubble tea",
        "juice",
        "snack",
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
        "nui",
        "hang dong",
        "thac",
        "ho",
        "song",
        "suoi",
        "bien",
        "bien dong",
        "bien viet",
        "bi",
        "canh",
        "canh dep",
        "phong canh",
        "canh quan",
        "cong vien",
        "vuon",
        "vuon hoa",
        "vuon bot",
        "thu vien",
        "thien nhien",
        "leo nui",
        "cay",
        "rung",
        "trai nghiem thien nhien",
    },
    "shopping": {
        "cho",
        "mall",
        "market",
        "marketplace",
        "mua sam",
        "shopping",
        "mua",
        "mua do",
        "sieu thi",
        "trung tam thuong mai",
        "tttm",
        "cua hang",
        "shop",
        "shop qu",
        "shop quan",
        "thoi trang",
        "quan ao",
        "giay",
        "dep",
        "phu kien",
        "trang suc",
        "do luu niem",
        "qua luu niem",
        "qua tang",
        "dac san",
        "do an vung",
        "mua sam",
        "shopping mall",
        "shopping center",
    },
}

PLACE_GROUP_CATEGORY: dict[str, str] = {
    "accommodation": "accommodation",
    "attraction": "attraction",
    "entertainment": "entertainment",
    "experience": "attraction",
    "shopping": "shopping",
    "wellness": "entertainment",
}

PLACE_TYPE_CATEGORY: dict[str, str] = {
    # OpenStreetMap / legacy place_type values that pre-date the Google CSV.
    "aerodrome": "transport",
    "apartment": "accommodation",
    "bakery": "DrinkDessert",
    "bar": "DrinkDessert",
    "beach": "nature",
    "biergarten": "DrinkDessert",
    "bus_station": "transport",
    "cafe": "DrinkDessert",
    "camp_site": "nature",
    "cave_entrance": "nature",
    "cinema": "entertainment",
    "coffee": "DrinkDessert",
    "fast_food": "Restaurant",
    "ferry_terminal": "transport",
    "food_court": "Restaurant",
    "garden": "nature",
    "guest_house": "accommodation",
    "hostel": "accommodation",
    "hotel": "accommodation",
    "ice_cream": "DrinkDessert",
    "marketplace": "shopping",
    "marina": "transport",
    "motel": "accommodation",
    "nature_reserve": "nature",
    "nightclub": "entertainment",
    "park": "nature",
    "peak": "nature",
    "pub": "DrinkDessert",
    "restaurant": "Restaurant",
    "station": "transport",
    "supermarket": "shopping",
    "theatre": "entertainment",
    "wetland": "nature",
    "wilderness_hut": "nature",
    "wood": "nature",
    # Google Maps Place "primary_type" / "types" values produced by the
    # csv_relational importer. Without this mapping
    # ``place_category(place)`` falls back to ``None`` and the candidate
    # is rejected by ``place_matches_categories`` whenever the meal/food
    # query mentions a Vietnam-localised term that does not appear in the
    # ``sorted[0]`` semantic_categories fallback.
    "amusement_park": "entertainment",
    "aquarium": "entertainment",
    "art_gallery": "attraction",
    "barbecue_area": "Restaurant",
    "bowling_alley": "entertainment",
    "book_store": "shopping",
    "bridge": "attraction",
    "cafe;bakery": "DrinkDessert",
    "campground": "nature",
    "casino": "entertainment",
    "cemetery": "attraction",
    "church": "attraction",
    "city_hall": "attraction",
    "clothing_store": "shopping",
    "coffee_shop": "DrinkDessert",
    "convenience_store": "shopping",
    "courthouse": "attraction",
    "cultural_center": "attraction",
    "department_store": "shopping",
    "embassy": "attraction",
    "establishment": "attraction",
    "fire_station": "transport",
    "fountain": "attraction",
    "gym": "entertainment",
    "hindu_temple": "attraction",
    "historical_landmark": "attraction",
    "historical_place": "attraction",
    "hospital": "transport",
    "library": "attraction",
    "local_government_office": "attraction",
    "lodging": "accommodation",
    "meal_takeaway": "Restaurant",
    "memorial": "attraction",
    "monument": "attraction",
    "mosque": "attraction",
    "museum": "attraction",
    "national_park": "nature",
    "natural_feature": "nature",
    "night_club": "entertainment",
    "observation_deck": "attraction",
    "park;natural_feature": "nature",
    "pharmacy": "shopping",
    "place_of_worship": "attraction",
    "plaza": "attraction",
    "point_of_interest": "attraction",
    "police": "transport",
    "post_office": "transport",
    "restaurant;cafe": "Restaurant",
    "rv_park": "accommodation",
    "school": "attraction",
    "scenic_spot": "nature",
    "shopping_mall": "shopping",
    "spa": "entertainment",
    "square": "attraction",
    "stadium": "entertainment",
    "store": "shopping",
    "subway_station": "transport",
    "synagogue": "attraction",
    "tourist_attraction": "attraction",
    "train_station": "transport",
    "transit_station": "transport",
    "university": "attraction",
    "zoo": "entertainment",
    # Common Vietnamese-language category strings produced by the
    # ``auto-crawl`` pipeline (CSV ``places.csv`` ``category`` column).
    "nha_hang": "Restaurant",
    "quan_an": "Restaurant",
    "quan_nhau": "Restaurant",
    "quan_cafe": "DrinkDessert",
    "quan_coffee": "DrinkDessert",
    "quan_tra": "DrinkDessert",
    "tiem_banh": "DrinkDessert",
    "tiem_an_vat": "DrinkDessert",
    "an_vat": "DrinkDessert",
    "do_an_vat": "DrinkDessert",
    "o_an_vat": "DrinkDessert",
    "hai_san": "Restaurant",
    "lau": "Restaurant",
    "bingsu": "DrinkDessert",
    "che": "DrinkDessert",
    "pho": "Restaurant",
    "bun": "Restaurant",
    "com": "Restaurant",
    "mien": "Restaurant",
    "banh_mi": "Restaurant",
    "banh": "DrinkDessert",
    "banh_xeo": "Restaurant",
    "bun_cha": "Restaurant",
    "bun_bo": "Restaurant",
    "bun_dau": "Restaurant",
    "bun_thang": "Restaurant",
    "bun_rieu": "Restaurant",
    "com_tam": "Restaurant",
    "com_ga": "Restaurant",
    "com_nieu": "Restaurant",
    "nem_ran": "Restaurant",
    "chao": "Restaurant",
    "chao_long": "Restaurant",
    "mien_ga": "Restaurant",
    "hu_tieu": "Restaurant",
    "mi_quang": "Restaurant",
    "pho_bo": "Restaurant",
    "pho_ga": "Restaurant",
    "banh_cuon": "Restaurant",
    "banh_chung": "Restaurant",
    "banh_my": "Restaurant",
    "banh_xeo": "Restaurant",
    "bun_oc": "Restaurant",
    "oc": "Restaurant",
    "oc_bu": "Restaurant",
    "an_sang": "Restaurant",
    "an_trua": "Restaurant",
    "an_toi": "Restaurant",
    "di_tich": "attraction",
    "den_chua": "attraction",
    "chua": "attraction",
    "dinh": "attraction",
    "mieu": "attraction",
    "lang": "attraction",
    "lang_nghe": "attraction",
    "bao_tang": "attraction",
    "nha_tu": "attraction",
    "cho": "shopping",
    "cho_dem": "shopping",
    "cho_hoa": "shopping",
    "trung_tam_thuong_mai": "shopping",
    "sieu_thi": "shopping",
    "tttm": "shopping",
    "cong_vien": "nature",
    "vuon_quoc_gia": "nature",
    "vuon_thu": "attraction",
    "vuon_hoa": "nature",
    "bai_bien": "nature",
    "bien": "nature",
    "dao": "nature",
    "nui": "nature",
    "hang_dong": "nature",
    "thac": "nature",
    "ho": "nature",
    "song": "nature",
    "rap_phim": "entertainment",
    "rap_hai": "entertainment",
    "karaoke": "entertainment",
    "khu_vui_choi": "entertainment",
    "san_golf": "entertainment",
    "nha_hang_khach_san": "accommodation",
    "khach_san": "accommodation",
    "nha_nghi": "accommodation",
    "homestay": "accommodation",
    "resort": "accommodation",
}


class SelectablePlace(BaseModel):
    place_id: str | None = Field(default=None, alias="placeId")
    name: str
    address: str | None = None
    place_type: str = Field(alias="placeType")
    region_key: str = Field(alias="regionKey")
    description: str | None = None
    notes: str | None = None
    note_sources: list[PlanNoteSource] = Field(
        default_factory=list,
        alias="noteSources",
    )
    context_places: list[str] = Field(default_factory=list, alias="contextPlaces")
    personal_notes: str | None = Field(default=None, alias="personalNotes")
    place_group: str | None = Field(default=None, alias="placeGroup")
    tags: list[str] = Field(default_factory=list)
    ontology_type: KnowledgePlaceType | None = Field(
        default=None, alias="ontologyType"
    )
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
    claim_ids: list[str] = Field(default_factory=list, alias="claimIds")
    activity_id: str | None = Field(default=None, alias="activityId")
    experience_category: ExperienceCategory | None = Field(
        default=None, alias="experienceCategory"
    )
    source_provider: str | None = Field(
        default=None,
        alias="sourceProvider",
    )
    source_import_node_id: int | None = Field(
        default=None, alias="sourceImportNodeId"
    )
    candidate_entity_ids: list[str] = Field(
        default_factory=list, alias="candidateEntityIds"
    )
    selection_method: str | None = Field(default=None, alias="selectionMethod")
    route_score: float | None = Field(default=None, alias="routeScore")
    identity_confidence: str | None = Field(
        default=None, alias="identityConfidence"
    )
    accessibility_features: list[str] = Field(
        default_factory=list,
        alias="accessibilityFeatures",
    )
    opening_hours: list[dict] = Field(default_factory=list, alias="openingHours")
    weather_sensitivity: str | None = Field(default=None, alias="weatherSensitivity")
    price_level: str | None = Field(default=None, alias="priceLevel")
    rating: float | None = None
    review_count: int = Field(default=0, alias="reviewCount")
    image_urls: list[str] = Field(default_factory=list, alias="imageUrls")
    data_confidence: str = Field(default="low", alias="dataConfidence")
    source_link: str | None = Field(default=None, alias="sourceLink")
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
    preferred_time_windows: list[PreferredTimeWindow] = Field(
        default_factory=list,
        alias="preferredTimeWindows",
    )

    model_config = {"populate_by_name": True}

    @property
    def stable_ref(self) -> str:
        return self.place_id or self.name


class PlaceSelectionTool(Protocol):
    def get(self, place_id: str) -> SelectablePlace | None: ...

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[SelectablePlace]: ...


class PlaceSelectionRepository(Protocol):
    def get(self, place_id: str) -> Any | None: ...

    def list_for_place_selection(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Any]: ...


class EmptyPlaceSelectionTool:
    def get(self, place_id: str) -> SelectablePlace | None:
        return None

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[SelectablePlace]:
        return []


def _inside_bbox(
    place: SelectablePlace,
    bbox: tuple[float, float, float, float],
) -> bool:
    """Return True iff place coordinates fall inside the bbox.

    ``bbox`` is ``(min_lat, min_lon, max_lat, max_lon)``. Places without
    coordinates are kept because the catalogue may still contain them.
    """

    if place.latitude is None or place.longitude is None:
        return True
    min_lat, min_lon, max_lat, max_lon = bbox
    return min_lat <= place.latitude <= max_lat and min_lon <= place.longitude <= max_lon


class RepositoryPlaceSelectionTool:
    def __init__(self, repository: PlaceSelectionRepository, *, graph_repository=None) -> None:
        self.repository = repository
        self.graph_repository = graph_repository
        self._scope_cache: dict[str, list[SelectablePlace]] = {}
        self._graph_activity_cache: dict[
            tuple[str, tuple[str, ...], int],
            list[SelectablePlace],
        ] = {}

    def get(self, place_id: str) -> SelectablePlace | None:
        place = self.repository.get(place_id)
        if place is None or place.deleted_at is not None:
            return None
        return self._to_selectable_place(place)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[SelectablePlace]:
        places = self._load_scoped_candidates(region_key, excluded_place_ids)
        places = [
            place
            for place in places
            if _matches_target_locality(place, region_key)
        ]
        graph_places = self._load_graph_activity_candidates(
            region_key=region_key,
            target_tags=target_tags,
            excluded_place_ids=excluded_place_ids,
            limit=max(MIN_DESCRIPTION_RETRIEVAL_LIMIT, limit * 10),
        )
        if graph_places:
            by_ref = {place.stable_ref: place for place in places}
            for place in graph_places:
                # Prefer the graph-enriched copy so activityId and provenance
                # survive into CandidateSelector and the final PlanItem.
                by_ref[place.stable_ref] = place
            places = list(by_ref.values())
        if bbox_filter is not None:
            places = [place for place in places if _inside_bbox(place, bbox_filter)]
        if not places:
            return []

        query_terms = _normalized_terms(target_tags)
        query_categories = semantic_categories(query_terms)
        coffee_requested = any(
            marker in f" {_normalize_text(term)} "
            for term in target_tags
            for marker in (
                " cafe ",
                " coffee ",
                " ca phe ",
                " cafe hopping ",
                " coffee hopping ",
            )
        )
        non_food_activity_query = bool(
            query_categories.intersection(
                {"attraction", "entertainment", "nature", "shopping"}
            )
        ) and not query_categories.intersection(
            {"Restaurant", "DrinkDessert"}
        ) and not coffee_requested
        if non_food_activity_query:
            places = [
                place
                for place in places
                if place_category(place) not in {"Restaurant", "DrinkDessert"}
                and not is_coffee_place(place)
            ]
        if query_categories == {"Restaurant"}:
            # Food-related provider catalogs also contain ingredient shops,
            # packaging vendors and cooking schools. They are relevant to the
            # word "food", but cannot serve as a travel meal stop.
            places = [place for place in places if is_dine_in_meal_venue(place)]
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
            or self._graph_activity_matches(place, query_terms)
        ]
        if len(eligible_shortlist) < limit:
            shortlisted_refs = {
                place.stable_ref for place in eligible_shortlist
            }
            eligible_shortlist.extend(
                place
                for place in places
                if (
                    place_matches_categories(place, query_categories)
                    or self._graph_activity_matches(place, query_terms)
                )
                and place.stable_ref not in shortlisted_refs
            )
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

    def _load_graph_activity_candidates(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[SelectablePlace]:
        if self.graph_repository is None or not target_tags:
            return []
        if "Restaurant" in semantic_categories(set(target_tags)):
            return []
        cache_key = (
            region_key,
            tuple(sorted(_normalized_terms(target_tags))),
            limit,
        )
        cached = self._graph_activity_cache.get(cache_key)
        if cached is not None:
            return [
                place
                for place in cached
                if place.stable_ref not in excluded_place_ids
            ]
        loader = getattr(self.graph_repository, "list_activity_place_candidates", None)
        if not callable(loader):
            return []
        try:
            rows = loader(
                region_key,
                activity_terms=target_tags,
                limit=max(limit, 100),
            )
        except TypeError:
            # Compatibility for lightweight test doubles and older adapters.
            rows = loader(region_key, limit=max(limit, 100))
        query_terms = _normalized_terms(target_tags)
        best_by_place: dict[str, tuple[int, object]] = {}
        for row in rows:
            activity_terms = _normalized_terms([row.activityName])
            score = len(query_terms.intersection(activity_terms))
            normalized_activity = _normalize_text(row.activityName)
            score += sum(
                2
                for term in query_terms
                if term and term in normalized_activity
            )
            current = best_by_place.get(row.placeId)
            if current is None or score > current[0]:
                best_by_place[row.placeId] = (score, row)

        result: list[SelectablePlace] = []
        ordered = sorted(
            best_by_place.values(),
            key=lambda value: (-value[0], value[1].activityName.casefold()),
        )
        for _, row in ordered[:limit]:
            place = self.get(row.placeId)
            if place is None:
                continue
            result.append(
                place.model_copy(
                    update={
                        "activity_id": row.activityId,
                        "source_activity": row.activityName,
                        "candidate_entity_ids": list(
                            dict.fromkeys(
                                [*place.candidate_entity_ids, row.activityId]
                            )
                        ),
                        "selection_method": "offers_activity_graph",
                        "tags": list(
                            dict.fromkeys([*place.tags, row.activityName])
                        ),
                    }
                )
            )
        self._graph_activity_cache[cache_key] = result
        return [
            place
            for place in result
            if place.stable_ref not in excluded_place_ids
        ]

    @staticmethod
    def _graph_activity_matches(
        place: SelectablePlace,
        query_terms: set[str],
    ) -> bool:
        if place.selection_method != "offers_activity_graph" or not place.activity_id:
            return False
        if not query_terms:
            return True
        activity = _normalize_text(place.source_activity or "")
        return any(term and term in activity for term in query_terms)

    def _load_scoped_candidates(
        self,
        region_key: str,
        excluded_place_ids: set[str],
    ) -> list[SelectablePlace]:
        candidates: list[SelectablePlace] = []
        seen: set[str] = set()
        scopes = _region_scopes(region_key)
        for scope in scopes:
            if scope not in self._scope_cache:
                raw = self.repository.list_for_place_selection(
                    scope,
                    limit=MAX_REPOSITORY_CANDIDATES,
                )
                self._scope_cache[scope] = [
                    self._to_selectable_place(place) for place in raw
                ]
            for place in self._scope_cache[scope]:
                if (
                    place.place_id in excluded_place_ids
                    or place.stable_ref in seen
                ):
                    continue
                seen.add(place.stable_ref)
                candidates.append(place)
        if not candidates:
            logger.warning(
                "PlaceSelector: empty candidate set for region '%s' across scopes %s.",
                region_key,
                scopes,
            )
        return candidates

    def _to_selectable_place(self, place: Any) -> SelectablePlace:
        metadata = place.metadata_json or {}
        tags = read_tags(place)
        image_urls = list(
            dict.fromkeys(
                [
                    str(image.image_url)
                    for image in (getattr(place, "images", None) or [])
                    if getattr(image, "image_url", None)
                ]
                + [
                    str(image_url)
                    for image_url in (metadata.get("imageUrls", []) or [])
                    if image_url
                ]
            )
        )
        minimum_duration = _minimum_duration_minutes(metadata)
        if minimum_duration is None and place.typical_duration_minutes:
            minimum_duration = max(15, place.typical_duration_minutes // 2)

        return SelectablePlace(
            placeId=place.id,
            name=place.name,
            address=place.address,
            placeType=place.place_type,
            regionKey=place.region_key,
            description=read_description(place),
            placeGroup=(
                str(metadata.get("placeGroup"))
                if metadata.get("placeGroup") is not None
                else None
            ),
            tags=[str(tag) for tag in tags if isinstance(tag, str)],
            ontologyType=canonical_place_node_type(
                metadata.get("ontologyType")
                or metadata.get("ontology_type")
                or place.place_type
            ),
            sourceRefs=(
                [
                    str(ref)
                    for ref in (
                        metadata.get("sourceRefs", metadata.get("source_refs", []))
                        or []
                    )
                    if ref
                ]
                or ([place.source_link] if place.source_link else [])
            ),
            claimIds=[
                str(claim)
                for claim in (
                    metadata.get("claimIds", metadata.get("claim_ids", [])) or []
                )
                if claim
            ],
            activityId=metadata.get("activityId", metadata.get("activity_id")),
            experienceCategory=metadata.get(
                "experienceCategory", metadata.get("experience_category")
            ),
            latitude=(
                float(place.latitude) if place.latitude is not None else None
            ),
            longitude=(
                float(place.longitude) if place.longitude is not None else None
            ),
            typicalDurationMinutes=place.typical_duration_minutes,
            minimumDurationMinutes=minimum_duration,
            activityIntensity=(
                metadata.get("activityIntensity")
                or metadata.get("activity_intensity")
            ),
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
            priceLevel=read_price_level(place),
            rating=read_rating(place),
            reviewCount=read_review_count(place),
            imageUrls=image_urls,
            dataConfidence=place.data_confidence,
            sourceProvider=place.source_platform,
            sourceLink=place.source_link,
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


def place_category(place: SelectablePlace) -> str | None:
    if place.ontology_type in {"Restaurant", "DrinkDessert"}:
        return place.ontology_type
    normalized_name = _normalize_text(place.name)
    place_type = _normalize_text(place.place_type).replace(" ", "_")
    padded_place_type = f"_{place_type}_"
    if any(
        marker in padded_place_type
        for marker in (
            "_hotel_",
            "_homestay_",
            "_hostel_",
            "_motel_",
            "_resort_",
            "_apartment_",
            "_lodging_",
            "_guest_house_",
        )
    ):
        return "accommodation"
    if any(
        marker in padded_place_type
        for marker in (
            "_bakery_",
            "_ice_cream_",
            "_dessert_",
            "_juice_",
            "_tea_",
            "_bingsu_",
            "_snack_",
            "_confectionery_",
            "_bar_",
            "_pub_",
        )
    ):
        return "DrinkDessert"
    if any(
        marker in padded_place_type
        for marker in ("_restaurant_", "_fast_food_", "_food_court_")
    ):
        return "Restaurant"
    if re.search(
        r"(^| )(ga|station|terminal|ben pha)( |$)",
        normalized_name,
    ):
        return "transport"
    if any(
        marker in f" {normalized_name} "
        for marker in (
            " cafe ",
            " coffee ",
            " coffee shop ",
        )
    ):
        return "DrinkDessert"
    if any(
        marker in f" {normalized_name} "
        for marker in (
            " train street ",
            " cathedral ",
            " church ",
            " nha tho ",
            " lake ",
            " ho hoan kiem ",
        )
    ):
        return "attraction"
    if place_type in PLACE_TYPE_CATEGORY:
        return PLACE_TYPE_CATEGORY[place_type]
    group = _normalize_text(place.place_group or "")
    if group in PLACE_GROUP_CATEGORY:
        return PLACE_GROUP_CATEGORY[group]
    values = _normalized_terms([place.place_type, *place.tags])
    categories = semantic_categories(values)
    return sorted(categories)[0] if categories else None


def is_coffee_place(place: Any) -> bool:
    """Return whether a venue represents a coffee/cafe stop.

    Cafe remains a valid itinerary activity.  This predicate is deliberately
    separate from ``place_category`` so the selector can limit only Finder
    repetition without reclassifying URL-backed cafe experiences as meals.
    """

    values = _normalize_text(
        " ".join(
            str(value)
            for value in (
                getattr(place, "name", ""),
                getattr(place, "place_type", ""),
                *list(getattr(place, "tags", []) or []),
            )
            if value
        )
    )
    padded = f" {values} "
    return any(
        marker in padded
        for marker in (
            " cafe ",
            " coffee ",
            " coffee shop ",
            " ca phe ",
            " quan cafe ",
            " quan ca phe ",
        )
    )


def is_dine_in_meal_venue(place: Any) -> bool:
    """Return whether a venue can serve a main meal, not dessert or drinks."""

    place_type = f" {_normalize_text(getattr(place, 'place_type', ''))} "
    rejected_markers = (
        " supplier ",
        " supply ",
        " store ",
        " supermarket ",
        " grocery ",
        " school ",
        " package ",
        " manufacturer ",
        " wholesaler ",
        " distributor ",
        " soup kitchen ",
    )
    if any(marker in place_type for marker in rejected_markers):
        return False
    return is_meal_place(
        tags=[
            str(getattr(place, "place_type", "")),
            *[str(tag) for tag in (getattr(place, "tags", []) or [])],
        ],
        source_activity=str(getattr(place, "name", "")),
        ontology_type=getattr(place, "ontology_type", None),
    )


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
    place: SelectablePlace,
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
        "Restaurant": 0,
        "DrinkDessert": 0,
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
    popularity_score = min(
        48,
        round(log10(max(0, place.review_count) + 1) * 12),
    )
    rating_score = (
        round((place.rating - 3.5) * 12)
        if place.rating is not None
        else 0
    )
    normalized_name = _normalize_text(place.name)
    name_quality_penalty = 0
    if len(normalized_name) <= 3:
        name_quality_penalty -= 25
    if re.fullmatch(r"\d+(?:\s+\w+){0,3}", normalized_name):
        name_quality_penalty -= 30
    return (
        _description_relevance(place.description, query_terms) * 18
        + category_score
        + tag_overlap * 12
        + region_score
        + confidence_score
        + coordinate_score
        + popularity_score
        + rating_score
        + name_quality_penalty
    )


def selection_relevance_score(
    place: SelectablePlace,
    *,
    region_key: str,
    target_tags: list[str],
) -> int:
    """Return the semantic/quality score used before route proximity.

    Candidate discovery and route optimization are deliberately separate
    concerns.  Callers may use distance to break equal relevance scores, but
    a shorter route must not promote a less relevant Place above a stronger
    match for the user's requested experience.
    """

    query_terms = _normalized_terms(target_tags)
    return _structured_rerank_score(
        place,
        region_key=region_key,
        query_terms=query_terms,
        query_categories=semantic_categories(query_terms),
    )


def place_matches_categories(
    place: SelectablePlace,
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
    place: SelectablePlace,
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
