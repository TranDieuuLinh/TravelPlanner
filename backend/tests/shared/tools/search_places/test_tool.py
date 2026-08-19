import asyncio

from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceProviderCandidate,
    PlaceSearchProviderTimeout,
    PlaceSearchRequest,
    SearchPlacesTool,
)
from app.shared.tools.search_places.adapters import InMemoryPlaceSearch
from app.shared.tools.search_places.policy import PlaceSearchPolicy


HANOI = AdministrativeArea(
    admId="adm1-vn-hanoi",
    name="Hà Nội",
    level="ADM1",
    countryCode="VN",
)


def _run(coro):
    return asyncio.run(coro)


def _candidate(
    name: str,
    identity: str,
    *,
    aliases: list[str] | None = None,
    adm_ids: list[str] | None = None,
    canonical_type: str = "travel_place",
    confidence: float = 0.95,
    provider: str = "knowledge_graph",
    address: str | None = "Ba Dinh, Hanoi",
    tags: list[str] | None = None,
    coordinates: Coordinates | None = None,
) -> PlaceProviderCandidate:
    return PlaceProviderCandidate(
        provider=provider,
        entityId=identity if provider == "knowledge_graph" else None,
        providerId=identity if provider != "knowledge_graph" else None,
        name=name,
        aliases=aliases or [],
        address=address,
        coordinates=coordinates
        or Coordinates(latitude=21.0368, longitude=105.8346),
        admIds=adm_ids or [HANOI.adm_id],
        admNames=[HANOI.name],
        canonicalType=canonical_type,
        dataConfidence=confidence,
        tags=tags or [],
    )


def test_resolves_a_high_confidence_knowledge_graph_identity() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate(
                "Ho Chi Minh Mausoleum",
                "kg-place-1",
                aliases=["Lăng Chủ tịch Hồ Chí Minh"],
            )
        ],
        provider_name="knowledge_graph",
    )
    request = PlaceSearchRequest(
        query="Lăng Chủ tịch Hồ Chí Minh",
        inputAdm=HANOI,
        placeTypeHint="travel_place",
    )

    result = _run(SearchPlacesTool(kg).search(request))

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "kg-place-1"
    assert result.selected.score > 0.82
    assert result.resolution_reason == "high_confidence_identity"


def test_diacritic_insensitive_alias_matching_is_supported() -> None:
    kg = InMemoryPlaceSearch(
        [_candidate("Café Giảng", "kg-cafe-1", aliases=["Cafe Giang"])],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(query="cafe giang", inputAdm=HANOI)
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.name == "Café Giảng"


def test_branch_without_address_hint_selects_first_kg_result() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate("Highlands Coffee", "branch-1", address="Hoan Kiem"),
            _candidate("Highlands Coffee", "branch-2", address="Tay Ho"),
        ],
        provider_name="knowledge_graph",
    )
    external = InMemoryPlaceSearch(
        [_candidate("Highlands Coffee", "google-1", provider="google_maps")],
        provider_name="google_maps_playwright",
    )

    result = _run(
        SearchPlacesTool(kg, external).search(
            PlaceSearchRequest(query="Highlands Coffee", inputAdm=HANOI)
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "branch-1"
    assert result.resolution_reason == "first_branch_without_address_hint"
    assert len(result.top_matches) == 2
    assert external.calls == []


def test_address_hint_disambiguates_two_strong_branches() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate("Café Giảng", "branch-1", address="57 Tràng Tiền, Hà Nội"),
            _candidate(
                "Café Giảng",
                "branch-2",
                address="39 Nguyễn Hữu Huân, Hoàn Kiếm, Hà Nội",
            ),
        ],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(
                query="Café Giảng",
                addressHint="39 Nguyễn Hữu Huân, Hoàn Kiếm, Hà Nội",
                inputAdm=HANOI,
            )
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "branch-2"
    assert result.resolution_reason == "address_hint_identity"


def test_distinctive_full_name_disambiguates_related_landmarks() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate("Ho Chi Minh's Mausoleum", "mausoleum"),
            _candidate("Ho Chi Minh Museum", "museum"),
        ],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(query="Ho Chi Minh Mausoleum", inputAdm=HANOI)
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "mausoleum"
    assert result.resolution_reason == "distinctive_name_identity"


def test_route_context_can_disambiguate_two_strong_branches() -> None:
    anchor = Coordinates(latitude=21.0368, longitude=105.8346)
    kg = InMemoryPlaceSearch(
        [
            _candidate(
                "Highlands Coffee",
                "near-branch",
                address="Ba Dinh",
                coordinates=Coordinates(latitude=21.0370, longitude=105.8350),
            ),
            _candidate(
                "Highlands Coffee",
                "far-branch",
                address="Tay Ho",
                coordinates=Coordinates(latitude=21.0900, longitude=105.8100),
            ),
        ],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(
                query="Highlands Coffee",
                inputAdm=HANOI,
                previousPlace=anchor,
            )
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "near-branch"
    assert result.resolution_reason == "route_context_identity"


def test_duplicate_kg_rows_within_two_hundred_metres_are_collapsed() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate("Museum", "duplicate-weak", confidence=0.8),
            _candidate(
                "Museum",
                "duplicate-complete",
                confidence=0.99,
                coordinates=Coordinates(latitude=21.0370, longitude=105.8348),
            ),
        ],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(query="Museum", inputAdm=HANOI)
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "duplicate-complete"
    assert len(result.top_matches) == 1


def test_weak_knowledge_graph_result_falls_back_to_external_provider() -> None:
    kg = InMemoryPlaceSearch(
        [_candidate("Unrelated Museum", "kg-weak")],
        provider_name="knowledge_graph",
    )
    external = InMemoryPlaceSearch(
        [
            _candidate(
                "Cafe Giang",
                "google-cafe-1",
                provider="google_maps",
                canonical_type="cafe",
            )
        ],
        provider_name="google_maps_playwright",
    )

    result = _run(
        SearchPlacesTool(kg, external).search(
            PlaceSearchRequest(
                query="Cafe Giang",
                inputAdm=HANOI,
                placeTypeHint="cafe",
            )
        )
    )

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.place_id == "google-cafe-1"
    assert result.resolution_reason == "external_high_confidence_identity"
    assert len(external.calls) == 1


def test_adm_mismatch_cannot_resolve_a_candidate() -> None:
    candidate = _candidate(
        "Ho Chi Minh Mausoleum",
        "wrong-region",
        adm_ids=["adm1-vn-ho-chi-minh-city"],
    ).model_copy(update={"adm_names": ["Ho Chi Minh City"]})
    kg = InMemoryPlaceSearch([candidate], provider_name="knowledge_graph")

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(
                query="Ho Chi Minh Mausoleum",
                inputAdm=HANOI,
                allowExternalFallback=False,
            )
        )
    )

    assert result.status == "unresolved"
    assert "adm_mismatch_or_missing" in result.top_matches[0].rejection_reasons


def test_requirement_search_can_match_a_verified_tagged_venue() -> None:
    kg = InMemoryPlaceSearch(
        [
            _candidate(
                "Phở Gia Truyền Bát Đàn",
                "restaurant-1",
                canonical_type="restaurant",
                tags=["pho", "local_food"],
            )
        ],
        provider_name="knowledge_graph",
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(
                query="pho",
                inputAdm=HANOI,
                searchMode="requirement",
                placeTypeHint="restaurant",
            )
        )
    )

    assert result.status == "resolved"
    assert result.resolution_reason == "requirement_match"
    assert result.selected is not None
    assert result.selected.place_id == "restaurant-1"


def test_provider_timeout_is_distinct_from_no_match() -> None:
    kg = InMemoryPlaceSearch(
        provider_name="knowledge_graph",
        error=PlaceSearchProviderTimeout("database timed out"),
    )

    result = _run(
        SearchPlacesTool(kg).search(
            PlaceSearchRequest(query="Museum", inputAdm=HANOI)
        )
    )

    assert result.status == "provider_error"
    assert result.retryable is True
    assert result.provider_attempts[0].outcome == "timeout"


def test_named_acceptance_threshold_is_strictly_greater_than_policy() -> None:
    kg = InMemoryPlaceSearch(
        [_candidate("Museum", "museum-1", confidence=1.0)],
        provider_name="knowledge_graph",
    )
    policy = PlaceSearchPolicy(named_acceptance_score=0.925)

    result = _run(
        SearchPlacesTool(kg, policy=policy).search(
            PlaceSearchRequest(query="Museum", inputAdm=HANOI)
        )
    )

    assert result.top_matches[0].score == 0.925
    assert result.status == "unresolved"


def test_contract_serializes_external_fields_as_camel_case() -> None:
    request = PlaceSearchRequest(
        query="Museum",
        inputAdm=HANOI,
        sourceTimeHint="morning",
        topK=3,
    )

    payload = request.model_dump(mode="json", by_alias=True)

    assert payload["inputAdm"]["admId"] == "adm1-vn-hanoi"
    assert payload["sourceTimeHint"] == "morning"
    assert payload["topK"] == 3
    assert "input_adm" not in payload


def test_external_scope_skips_knowledge_graph_and_preserves_review_status() -> None:
    kg = InMemoryPlaceSearch(
        [_candidate("Museum", "kg-museum")],
        provider_name="knowledge_graph",
    )
    external_candidate = _candidate(
        "Museum",
        "google-museum",
        provider="google_maps",
    ).model_copy(update={"verification_status": "not_verified"})
    external = InMemoryPlaceSearch(
        [external_candidate],
        provider_name="google_maps_playwright",
    )

    result = _run(
        SearchPlacesTool(kg, external).search(
            PlaceSearchRequest(
                query="Museum",
                inputAdm=HANOI,
                providerScope="external",
            )
        )
    )

    assert kg.calls == []
    assert len(external.calls) == 1
    assert result.selected is not None
    assert result.selected.verification_status == "not_verified"
