import asyncio

from app.modules.place_checker.contract import (
    PlaceCandidateInput,
    SourcePlaceEvidence,
    UrlNote,
)
from app.modules.place_checker.enums import (
    EvidenceOrigin,
    IdentityResolutionStatus,
    SimilarityMethod,
    SourceTier,
)
from app.modules.place_checker.evidence import EvidenceEnrichmentService
from app.modules.place_checker.errors import PlaceCatalogUnavailableError
from app.modules.place_checker.resolution_contract import (
    CatalogPlace,
    IdentityResolutionBatch,
    PlaceMatchOption,
    PlaceMetadata,
    ResolvedPlaceCandidate,
    SimilarityComponents,
)
from app.shared.contracts.place import Coordinates


class FakeMetadataRepository:
    def __init__(self, metadata: dict[str, PlaceMetadata]) -> None:
        self.metadata = metadata
        self.calls: list[list[str]] = []
        self.unavailable = False

    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]:
        self.calls.append(place_ids)
        if self.unavailable:
            raise PlaceCatalogUnavailableError
        return self.metadata


def catalog_place() -> CatalogPlace:
    return CatalogPlace(
        place_id="kg_train_street",
        canonical_name="Hanoi Train Street",
        aliases=["Phố đường tàu Hà Nội"],
        adm_id="adm1_vn_ha_noi",
        region_key="vn,ha_noi",
        country_code="VN",
        address="Tran Phu, Hoan Kiem, Hanoi",
        category="urban_experience",
    )


def resolved_candidate(index: int, origin: EvidenceOrigin) -> ResolvedPlaceCandidate:
    place = catalog_place()
    evidence = SourcePlaceEvidence(
        origin=origin,
        evidence_type="raw_prompt" if origin == EvidenceOrigin.input else "stt",
        source_url="https://example.com/video" if origin == EvidenceOrigin.url else None,
        evidence=(
            "I want to visit Hanoi Train Street"
            if origin == EvidenceOrigin.input
            else "Visit Hanoi Train Street in the afternoon"
        ),
        source_time_hint="afternoon" if origin == EvidenceOrigin.url else None,
    )
    candidate = PlaceCandidateInput(
        name=("Hanoi Train Street" if index == 0 else "Phố đường tàu Hà Nội"),
        confidence=0.95,
        source_places=[evidence],
    )
    option = PlaceMatchOption(
        place=place,
        method=SimilarityMethod.exact,
        components=SimilarityComponents(
            lexical_score=1,
            destination_score=1,
            combined_score=1,
        ),
        rank=1,
        eligible_destination=True,
    )
    return ResolvedPlaceCandidate(
        candidate_index=index,
        candidate=candidate,
        status=IdentityResolutionStatus.resolved,
        selected_place=place,
        match_options=[option],
        selected_score=1,
        score_margin=1,
        resolution_method=SimilarityMethod.exact,
    )


def test_merges_duplicate_identity_and_preserves_all_evidence() -> None:
    metadata = PlaceMetadata(
        place_id="kg_train_street",
        coordinates=Coordinates(latitude=21.029, longitude=105.842),
        category="urban_experience",
        typical_duration_minutes=60,
        source="knowledge_graph",
    )
    repository = FakeMetadataRepository({metadata.place_id: metadata})
    note = UrlNote(
        summary="Visit in the afternoon and arrive early.",
        place_name="Hanoi Train Street",
        evidence_type="stt",
        source_url="https://example.com/video",
    )

    output = asyncio.run(
        EvidenceEnrichmentService(repository).merge_and_enrich(
            IdentityResolutionBatch(
                candidates=[
                    resolved_candidate(0, EvidenceOrigin.input),
                    resolved_candidate(1, EvidenceOrigin.url),
                ]
            ),
            [note],
        )
    )

    assert len(output.places) == 1
    assert output.duplicate_count == 1
    place = output.places[0]
    assert place.place_id == "kg_train_street"
    assert place.source_tier == SourceTier.direct_user
    assert place.mandatory is True
    assert place.removable is False
    assert len(place.source_places) == 2
    assert place.url_notes == [note]
    assert place.metadata.coordinates.latitude == 21.029
    assert repository.calls == [["kg_train_street"]]


def test_missing_metadata_remains_unknown() -> None:
    output = asyncio.run(
        EvidenceEnrichmentService().merge_and_enrich(
            IdentityResolutionBatch(
                candidates=[resolved_candidate(0, EvidenceOrigin.url)]
            ),
            [],
        )
    )

    place = output.places[0]
    assert place.metadata.coordinates is None
    assert place.metadata.opening_hours is None
    assert "coordinates" in place.missing_fields
    assert "opening_hours" in place.missing_fields
    assert place.source_tier == SourceTier.url


def test_unmatched_url_note_is_preserved() -> None:
    note = UrlNote(
        summary="Unrelated note",
        place_name="Another Place",
        evidence_type="stt",
        source_url="https://example.com/video",
    )

    output = asyncio.run(
        EvidenceEnrichmentService().merge_and_enrich(
            IdentityResolutionBatch(
                candidates=[resolved_candidate(0, EvidenceOrigin.url)]
            ),
            [note],
        )
    )

    assert output.unattached_url_notes == [note]
    assert output.places[0].url_notes == []


def test_metadata_failure_returns_partial_place_with_warning() -> None:
    repository = FakeMetadataRepository({})
    repository.unavailable = True

    output = asyncio.run(
        EvidenceEnrichmentService(repository).merge_and_enrich(
            IdentityResolutionBatch(
                candidates=[resolved_candidate(0, EvidenceOrigin.input)]
            ),
            [],
        )
    )

    assert len(output.places) == 1
    assert output.places[0].place_id == "kg_train_street"
    assert output.places[0].metadata.cost_tier.value == "unknown"
    assert any("metadata catalog" in warning for warning in output.warnings)


def test_conflicting_source_time_hints_are_exposed() -> None:
    morning = resolved_candidate(0, EvidenceOrigin.url)
    afternoon = resolved_candidate(1, EvidenceOrigin.url)
    morning_source = morning.candidate.source_places[0].model_copy(
        update={"source_time_hint": "morning"}
    )
    morning = morning.model_copy(
        update={
            "candidate": morning.candidate.model_copy(
                update={"source_places": [morning_source]}
            )
        }
    )

    output = asyncio.run(
        EvidenceEnrichmentService().merge_and_enrich(
            IdentityResolutionBatch(candidates=[morning, afternoon]),
            [],
        )
    )

    assert output.places[0].evidence_conflicts == ["source_time_hint_conflict"]
