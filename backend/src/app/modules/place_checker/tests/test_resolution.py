import asyncio

from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    BudgetInput,
    CapacityRange,
    PeopleInput,
    PlaceCandidateInput,
    SourcePlaceEvidence,
    TravelPace,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    BudgetMode,
    IdentityResolutionStatus,
    SimilarityMethod,
)
from app.modules.place_checker.resolution.service import EntityResolutionService
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import (
    PlaceProviderCandidate,
    PlaceSearchProviderTimeout,
    SearchPlacesTool,
)
from app.shared.tools.search_places.adapters import InMemoryPlaceSearch


HANOI_ADM_ID = "adm1_vn_ha_noi"


def hanoi_context() -> TripEvaluationContext:
    return TripEvaluationContext(
        destination=AdmResolution(
            input_name="Hanoi",
            status=AdmResolutionStatus.resolved,
            adm_id=HANOI_ADM_ID,
            canonical_name="Hà Nội",
            country_code="VN",
            region_key="vn,ha_noi",
        ),
        days=4,
        pace=TravelPace.balanced,
        capacity=CapacityRange(
            minimum_minutes=1440,
            typical_minutes=1920,
            maximum_minutes=2400,
        ),
        budget_mode=BudgetMode.relative_level,
        budget=BudgetInput(
            level="low",
            target_amount=None,
            currency="VND",
            source="raw_prompt",
        ),
        people=PeopleInput(adults=1, children=0, infants=0),
        preferences=[],
        avoids=["nightlife"],
    )


def explorer_candidate(
    name: str,
    *,
    origin: str = "input",
    address_hint: str | None = None,
) -> PlaceCandidateInput:
    return PlaceCandidateInput(
        name=name,
        address_hint=address_hint,
        confidence=0.98,
        source_places=[
            SourcePlaceEvidence(
                origin=origin,
                evidence_type="raw_prompt",
                evidence=f"I want to visit {name}",
            )
        ],
    )


def provider_candidate(
    place_id: str = "kg_ho_chi_minh_mausoleum",
    *,
    name: str = "Ho Chi Minh Mausoleum",
    aliases: list[str] | None = None,
    adm_ids: list[str] | None = None,
    adm_names: list[str] | None = None,
    address: str = "Ba Dinh, Hanoi",
    coordinates: Coordinates | None = None,
) -> PlaceProviderCandidate:
    return PlaceProviderCandidate(
        provider="knowledge_graph",
        entity_id=place_id,
        name=name,
        aliases=aliases or ["Lăng Chủ tịch Hồ Chí Minh"],
        adm_ids=adm_ids or [HANOI_ADM_ID],
        adm_names=adm_names or ["Hà Nội"],
        address=address,
        canonical_type="landmark",
        coordinates=coordinates or Coordinates(latitude=21.0368, longitude=105.8346),
        data_confidence=0.98,
    )


def service_with(
    candidates: list[PlaceProviderCandidate],
    *,
    external: InMemoryPlaceSearch | None = None,
) -> tuple[EntityResolutionService, InMemoryPlaceSearch]:
    kg = InMemoryPlaceSearch(candidates, provider_name="knowledge_graph")
    return EntityResolutionService(SearchPlacesTool(kg, external)), kg


def test_exact_match_uses_shared_search_tool() -> None:
    service, kg = service_with([provider_candidate()])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place.place_id == "kg_ho_chi_minh_mausoleum"
    assert result.resolution_method == SimilarityMethod.exact
    assert result.resolution_reason == "unified_catalog_top_1"
    assert result.provider_attempts[0].provider == "knowledge_graph"
    assert kg.calls == [["Ho Chi Minh Mausoleum"]]


def test_verified_alias_resolves_through_shared_scoring() -> None:
    service, _ = service_with([provider_candidate()])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Lăng Chủ tịch Hồ Chí Minh")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.resolution_method == SimilarityMethod.alias


def test_shared_lexical_similarity_handles_typo() -> None:
    service, _ = service_with([provider_candidate()])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Min Mausoleum")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.resolution_method == SimilarityMethod.lexical_only
    assert result.match_options[0].components.lexical_score > 0.9


def test_top_one_branch_without_address_hint_is_forwarded() -> None:
    first = provider_candidate(
        "kg_1",
        address="Hoan Kiem, Hanoi",
        coordinates=Coordinates(latitude=21.03, longitude=105.85),
    )
    second = provider_candidate(
        "kg_2",
        address="Tay Ho, Hanoi",
        coordinates=Coordinates(latitude=21.07, longitude=105.82),
    )
    service, _ = service_with([first, second])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place is not None
    assert result.selected_place.place_id == "kg_1"
    assert result.score_margin == 1
    assert result.resolution_reason == "unified_catalog_top_1"


def test_close_system_branches_without_address_hint_select_first_result() -> None:
    first = provider_candidate(
        "kg_1",
        coordinates=Coordinates(latitude=21.03, longitude=105.85),
    )
    second = provider_candidate(
        "kg_2",
        coordinates=Coordinates(latitude=21.07, longitude=105.82),
    )
    service, _ = service_with([first, second])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum", origin="system")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place is not None
    assert result.selected_place.place_id == "kg_1"


def test_lexical_containment_auto_selects_the_best_candidate() -> None:
    service, _ = service_with(
        [provider_candidate(name="BBQ Independence Road Restaurant", aliases=[])]
    )

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Independence Road")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place is not None
    assert result.resolution_reason == "unified_catalog_top_1"


def test_catalog_top_one_prevents_google_maps_call() -> None:
    external = InMemoryPlaceSearch(
        [provider_candidate("external")],
        provider_name="external",
    )
    service, _ = service_with(
        [provider_candidate("kg-top-one", name="Different Branch")],
        external=external,
    )

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Requested Branch")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.selected_place is not None
    assert result.selected_place.place_id == "kg-top-one"
    assert external.calls == []


def test_wrong_adm_cannot_resolve() -> None:
    wrong_adm = provider_candidate(
        adm_ids=["adm1_vn_ho_chi_minh"],
        adm_names=["Hồ Chí Minh City"],
    )
    service, _ = service_with([wrong_adm])

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.unresolved
    assert result.selected_place is None
    assert result.match_options[0].eligible_destination is False
    assert "adm_mismatch_or_missing" in result.match_options[0].identity_conflicts


def test_exact_name_with_conflicting_address_requires_review() -> None:
    service, _ = service_with([provider_candidate()])

    result = asyncio.run(
        service.resolve_all(
            [
                explorer_candidate(
                    "Ho Chi Minh Mausoleum",
                    address_hint="Paris, France",
                )
            ],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.needs_review
    assert result.selected_place is None
    assert "address_conflict" in result.match_options[0].identity_conflicts


def test_compact_destination_spelling_is_not_an_address_conflict() -> None:
    assert not EntityResolutionService._has_address_conflict(
        "Hanoi",
        "Thanh Niên, Tây Hồ, Hà Nội, Vietnam",
    )


def test_unresolved_adm_prevents_shared_tool_call() -> None:
    service, kg = service_with([provider_candidate()])
    context = hanoi_context().model_copy(
        update={
            "destination": AdmResolution(
                input_name="Unknown destination",
                status=AdmResolutionStatus.unresolved,
            )
        }
    )

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            context,
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.unresolved
    assert kg.calls == []


def test_provider_timeout_returns_partial_result() -> None:
    kg = InMemoryPlaceSearch(
        provider_name="knowledge_graph",
        error=PlaceSearchProviderTimeout("database timed out"),
    )
    service = EntityResolutionService(SearchPlacesTool(kg))

    batch = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            hanoi_context(),
        )
    )

    result = batch.candidates[0]
    assert result.status == IdentityResolutionStatus.unresolved
    assert result.resolution_reason == "knowledge_graph_provider_error"
    assert result.provider_attempts[0].outcome == "timeout"
    assert batch.warnings


def test_external_search_runs_only_when_catalog_has_no_top_one() -> None:
    external = InMemoryPlaceSearch(
        [provider_candidate("external_1")],
        provider_name="external",
    )
    service, _ = service_with([], external=external)

    result = asyncio.run(
        service.resolve_all(
            [explorer_candidate("Ho Chi Minh Mausoleum")],
            hanoi_context(),
        )
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place is not None
    assert result.selected_place.place_id == "external_1"
    assert result.resolution_reason == "external_unified_catalog_top_1"
    assert external.calls == [["Ho Chi Minh Mausoleum"]]


def test_unresolved_direct_user_candidate_is_preserved() -> None:
    service, _ = service_with([])
    original = explorer_candidate("Unknown Place")

    result = asyncio.run(service.resolve_all([original], hanoi_context())).candidates[0]

    assert result.status == IdentityResolutionStatus.unresolved
    assert result.candidate == original
    assert result.candidate.source_tier.value == "direct_user"
