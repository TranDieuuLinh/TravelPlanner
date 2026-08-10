import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import PlaceCandidateHint
from app.modules.plans.explorer.place_candidate_aggregator import (
    PlaceCandidateAggregator,
)
from app.modules.plans.explorer.place_policy import is_schedulable_place
from app.modules.plans.explorer.schema import (
    FullExploreRequest,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedPlace,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)


def test_place_candidate_serializes_category_in_api_shape() -> None:
    candidate = PlaceCandidateHint(name="Bánh mì Phượng", category="food")

    assert candidate.model_dump(mode="json", by_alias=True)["category"] == "food"


def test_place_candidate_defaults_unknown_category_to_other() -> None:
    candidate = PlaceCandidateHint(name="Địa điểm chưa rõ")

    assert candidate.model_dump(mode="json", by_alias=True)["category"] == "other"


def test_place_candidate_accepts_expanded_taxonomy_category() -> None:
    candidate = PlaceCandidateHint(name="Chợ Bến Thành", category="shopping")

    assert candidate.category.value == "shopping"


def test_place_candidate_rejects_category_outside_contract() -> None:
    with pytest.raises(ValidationError):
        PlaceCandidateHint(name="Địa điểm", category="casino")


def test_place_candidate_serializes_valid_coordinates() -> None:
    candidate = PlaceCandidateHint(
        name="Cầu Rồng",
        category="attraction",
        latitude=16.0611,
        longitude=108.2278,
    )

    payload = candidate.model_dump(mode="json", by_alias=True)

    assert payload["latitude"] == 16.0611
    assert payload["longitude"] == 108.2278


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", -90.1),
        ("latitude", 90.1),
        ("longitude", -180.1),
        ("longitude", 180.1),
    ],
)
def test_place_candidate_rejects_coordinates_outside_world_bounds(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        PlaceCandidateHint(name="Địa điểm", **{field: value})


@pytest.mark.parametrize("field", ["latitude", "longitude"])
def test_place_candidate_requires_coordinate_pair(field: str) -> None:
    with pytest.raises(ValidationError):
        PlaceCandidateHint(name="Địa điểm", **{field: 16.0611})


def test_explorer_input_accepts_user_travel_style() -> None:
    request = FullExploreRequest.model_validate(
        {
            "rawRequest": "Đà Nẵng 3 ngày",
            "destination": "Đà Nẵng",
            "userState": {
                "travelStyle": "adventure",
                "travelPreferences": ["local food"],
            },
        }
    )

    assert request.user_state.travel_style == "adventure"
    assert request.model_dump(mode="json", by_alias=True)["userState"][
        "travelStyle"
    ] == "adventure"


def test_url_company_record_is_not_schedulable_place() -> None:
    assert (
        is_schedulable_place(
            is_url_source=True,
            resolution_status="resolved",
            latitude=21.03,
            longitude=105.84,
            candidate_name="Công Ty TNHH Trung Tâm Văn Hoá Thể Thao Giải Trí Hà Nội",
            resolved_name="Công Ty TNHH Trung Tâm Văn Hoá Thể Thao Giải Trí Hà Nội",
            place_type="point_of_interest",
            city="Hà Nội",
            destination="Hà Nội",
            country="Việt Nam",
        )
        is False
    )


def test_url_non_tourism_place_type_is_not_schedulable_place() -> None:
    assert (
        is_schedulable_place(
            is_url_source=True,
            resolution_status="resolved",
            latitude=21.03,
            longitude=105.84,
            candidate_name="Example Office",
            resolved_name="Example Office",
            place_type="local_government_office",
            city="Hà Nội",
            destination="Hà Nội",
            country="Việt Nam",
        )
        is False
    )


def test_url_specific_attraction_remains_schedulable_place() -> None:
    assert (
        is_schedulable_place(
            is_url_source=True,
            resolution_status="resolved",
            latitude=21.0358,
            longitude=105.8336,
            candidate_name="Văn Miếu - Quốc Tử Giám",
            resolved_name="Văn Miếu - Quốc Tử Giám",
            place_type="tourist_attraction",
            city="Hà Nội",
            destination="Hà Nội",
            country="Việt Nam",
        )
        is True
    )


def test_explorer_aggregates_all_categories_into_one_candidate_array() -> None:
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hội An",
        generated=[
            UnifiedPlaceCandidate(
                name="Chùa Cầu",
                category="attraction",
                sources=[{"type": "user_prompt", "url": None}],
                confidence=1,
            ),
            UnifiedPlaceCandidate(
                name="Bánh mì Phượng",
                category="food",
                sources=[
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                confidence=0.8,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == [
        "Chùa Cầu",
        "Bánh mì Phượng",
    ]
    assert candidates[1].category.value == "food"
    assert candidates[1].sources[0].url == "https://example.com/reel"


def test_explorer_merges_duplicate_candidates_and_preserves_sources() -> None:
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Đà Nẵng",
        generated=[
            UnifiedPlaceCandidate(
                name="Bà Nà Hills",
                category="attraction",
                sources=[{"type": "ocr", "url": None}],
                confidence=0.7,
            ),
            UnifiedPlaceCandidate(
                name="Ba Na Hills",
                category="attraction",
                sources=[
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                confidence=0.9,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 1
    assert {source.type.value for source in candidates[0].sources} == {
        "ocr",
        "url",
    }


def test_explorer_merges_destination_suffix_variants_across_source_orders() -> None:
    source_url = "https://www.tiktok.com/@creator/video/42"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name="Phố đường tàu",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.8,
                sourceOrder=1,
            ),
            UnifiedPlaceCandidate(
                name="Phố đường tàu Hà Nội",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=2,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 1
    assert candidates[0].source_order == 1


def test_explorer_keeps_url_stops_omitted_by_formatter() -> None:
    url = "https://example.com/hanoi-reel"
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name="Xôi Yến",
                category="food",
                sources=[{"type": "url", "url": url}],
                confidence=0.8,
                sourceOrder=1,
            )
        ],
        explicit=[],
        url_results=[
            UrlReelExtractionResult(
                url=url,
                platform="tiktok",
                metadata=UrlMetadata(
                    originalUrl=url,
                    canonicalUrl=url,
                    platform="tiktok",
                ),
                artifacts=MediaArtifacts(),
                speechToText=SpeechToTextResult(
                    text="Xôi Yến, then Cafe Phố Cổ.",
                    durationSeconds=1,
                ),
                extractedContext=ExtractedContext(
                    extractedPlaces=["Xôi Yến", "Cafe Phố Cổ"],
                    extractedPlaceDetails=[
                        ExtractedPlace(
                            name="Xôi Yến",
                            category="food",
                            sourceOrder=1,
                        ),
                        ExtractedPlace(
                            name="Cafe Phố Cổ",
                            category="cafe",
                            sourceOrder=2,
                        ),
                    ],
                    confidence=0.9,
                ),
                timings={},
            )
        ],
    )

    assert [candidate.name for candidate in candidates] == [
        "Xôi Yến",
        "Cafe Phố Cổ",
    ]
    assert candidates[0].confidence == 0.9
    assert candidates[1].source_order == 2
    assert candidates[1].sources[0].url == url


def test_explorer_does_not_merge_localized_names_only_by_source_order() -> None:
    url = "https://example.com/hanoi-reel"
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name="Bảo tàng Dân tộc học Việt Nam",
                category="culture",
                sources=[{"type": "url", "url": url}],
                confidence=0.8,
                sourceOrder=2,
                sourceActivity="Khám phá nhà truyền thống và hiện vật.",
            )
        ],
        explicit=[],
        url_results=[
            UrlReelExtractionResult(
                url=url,
                platform="tiktok",
                metadata=UrlMetadata(
                    originalUrl=url,
                    canonicalUrl=url,
                    platform="tiktok",
                ),
                artifacts=MediaArtifacts(),
                speechToText=SpeechToTextResult(
                    text="Visit the Museum of Ethnology.",
                    durationSeconds=1,
                ),
                extractedContext=ExtractedContext(
                    extractedPlaces=["Museum of Ethnology"],
                    extractedPlaceDetails=[
                        ExtractedPlace(
                            name="Museum of Ethnology",
                            category="culture",
                            sourceOrder=2,
                        )
                    ],
                    confidence=0.95,
                ),
                timings={},
            )
        ],
    )

    assert len(candidates) == 2
    assert [candidate.name for candidate in candidates] == [
        "Bảo tàng Dân tộc học Việt Nam",
        "Museum of Ethnology",
    ]
    assert candidates[1].confidence == 0.95
    assert candidates[0].source_activity == (
        "Khám phá nhà truyền thống và hiện vật."
    )


def test_explorer_keeps_distinct_url_places_with_same_source_order() -> None:
    source_url = "https://www.tiktok.com/@creator/video/42"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name="Nhà thờ Lớn Hà Nội",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=1,
            ),
            UnifiedPlaceCandidate(
                name="Văn Miếu - Quốc Tử Giám",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=1,
            ),
            UnifiedPlaceCandidate(
                name="Hồ Hoàn Kiếm",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=1,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == [
        "Nhà thờ Lớn Hà Nội",
        "Văn Miếu - Quốc Tử Giám",
        "Hồ Hoàn Kiếm",
    ]
    assert {candidate.source_order for candidate in candidates} == {1}


def test_explorer_merges_minor_spelling_and_descriptive_place_variants() -> None:
    source_url = "https://www.tiktok.com/@creator/video/42"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name="Hoan Kim Lake",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.8,
                sourceOrder=1,
            ),
            UnifiedPlaceCandidate(
                name="Hoan Kiem Lake",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=2,
            ),
            UnifiedPlaceCandidate(
                name="train street",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.8,
                sourceOrder=3,
            ),
            UnifiedPlaceCandidate(
                name="a very famous train street",
                sources=[{"type": "url", "url": source_url}],
                confidence=0.9,
                sourceOrder=4,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 2
    assert [candidate.source_order for candidate in candidates] == [1, 3]


def test_explorer_rejects_caption_or_multi_place_list_as_one_url_candidate() -> None:
    url = "https://example.com/hanoi-reel"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hà Nội",
        generated=[
            UnifiedPlaceCandidate(
                name=(
                    "Hanoi 🇻🇳 📌 Cafe Pho Co ☕ 📌 Ethnology Museum "
                    "🛖 📌 Train Street Southern Entrance"
                ),
                sources=[{"type": "url", "url": url}],
                confidence=0.95,
                sourceOrder=1,
            ),
            UnifiedPlaceCandidate(
                name="Train Street",
                sources=[{"type": "url", "url": url}],
                confidence=0.9,
                sourceOrder=2,
                sourceActivity=(
                    "Don't skip these 4 spots in Hanoi. For our Train Street "
                    "guide, tap the link in bio and comment link."
                ),
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == ["Train Street"]
    assert candidates[0].source_activity is None


def test_explorer_rejects_itinerary_heading_as_url_place() -> None:
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hanoi",
        generated=[
            UnifiedPlaceCandidate(
                name="FULL DAY ITINERARY IN HANOI",
                sources=[
                    {"type": "url", "url": "https://example.com/hanoi-reel"}
                ],
                confidence=0.95,
            ),
            UnifiedPlaceCandidate(
                name="Cafe Giang",
                sources=[
                    {"type": "url", "url": "https://example.com/hanoi-reel"}
                ],
                confidence=0.9,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == ["Cafe Giang"]


def test_explorer_recovers_concise_place_name_from_evidence() -> None:
    source_url = "https://www.tiktok.com/@creator/video/imperial-citadel"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hanoi",
        generated=[
            UnifiedPlaceCandidate(
                name=(
                    "Imperial Citadel of Thang Long, a UNESCO World Heritage "
                    "site, but I still think it's underrated"
                ),
                category="culture",
                sources=[{"type": "url", "url": source_url}],
                sourceEvidence={
                    "ocr": "2. Imperial Citadel of Thang Long",
                    "stt": "Imperial Citadel of Thang Long",
                },
                confidence=0.95,
                sourceOrder=2,
            )
        ],
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 1
    assert candidates[0].name == "Imperial Citadel of Thang Long"
    assert candidates[0].source_evidence["ocr"] == (
        "2. Imperial Citadel of Thang Long"
    )


def test_explorer_removes_activity_prefix_only_when_activity_is_separate() -> None:
    source_url = "https://www.instagram.com/reel/example"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hanoi",
        generated=[
            UnifiedPlaceCandidate(
                name="Watch the train pass on Train Street",
                sources=[{"type": "url", "url": source_url}],
                sourceActivity="Watch the train pass",
                sourceEvidence={
                    "caption": "Watch the train pass on Train Street"
                },
                confidence=0.95,
            )
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == ["Train Street"]
    assert candidates[0].original_name == (
        "Watch the train pass on Train Street"
    )
    assert candidates[0].source_activity == "Watch the train pass"


def test_explorer_splits_two_concrete_places_from_composite_identity() -> None:
    source_url = "https://www.instagram.com/reel/example"
    composite = "Ho Chi Minh Mausoleum & One Pillar Pagoda"

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hanoi",
        generated=[
            UnifiedPlaceCandidate(
                name=composite,
                sources=[{"type": "url", "url": source_url}],
                sourceActivity="Visit the mausoleum and pagoda",
                sourceEvidence={"ocr": composite},
                alternateNames=["Combined stop"],
                confidence=0.95,
            ),
            UnifiedPlaceCandidate(
                name="Ho Chi Minh Museum",
                sources=[{"type": "url", "url": source_url}],
                sourceActivity="Visit the museum",
                sourceEvidence={"ocr": "Ho Chi Minh Museum"},
                confidence=0.95,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == [
        "Ho Chi Minh Mausoleum",
        "One Pillar Pagoda",
        "Ho Chi Minh Museum",
    ]
    assert [candidate.original_name for candidate in candidates] == [
        composite,
        composite,
        None,
    ]
    assert all(
        not candidate.alternate_names
        for candidate in candidates[:2]
    )


def test_brandneweats_hanoi_cache_aggregates_to_eight_places() -> None:
    source_url = (
        "https://www.tiktok.com/@brandneweats/video/7662905162960243989"
    )
    names = [
        "St Joseph's Cathedral",
        "Temple of Literature",
        "Hoan Kim Lake",
        "Coffee 74",
        "Hoan Kiem Lake",
        (
            "Imperial Citadel of Thang Long, a UNESCO World Heritage site, "
            "but I still think it's underrated"
        ),
        "Beer Street",
        "train street",
        "Hanoi Train Street",
        "a very famous train street",
        "Giao Mua",
    ]
    generated = [
        UnifiedPlaceCandidate(
            name=name,
            sources=[{"type": "url", "url": source_url}],
            sourceEvidence=(
                {
                    "ocr": "2. Imperial Citadel of Thang Long",
                    "stt": "Imperial Citadel of Thang Long",
                }
                if name.startswith("Imperial Citadel")
                else {}
            ),
            confidence=1.0,
        )
        for name in names
    ]

    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hanoi",
        generated=generated,
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 8
    assert "Imperial Citadel of Thang Long" in {
        candidate.name for candidate in candidates
    }
