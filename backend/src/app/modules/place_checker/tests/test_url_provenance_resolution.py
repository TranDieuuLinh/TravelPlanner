import asyncio

from app.modules.place_checker.contract import SourcePlaceEvidence
from app.modules.place_checker.enums import IdentityResolutionStatus, SimilarityMethod
from app.modules.place_checker.tests.test_resolution import (
    explorer_candidate,
    hanoi_context,
    provider_candidate,
    service_with,
)


def test_url_place_cannot_resolve_to_unrelated_catalog_name() -> None:
    service, _ = service_with(
        [
            provider_candidate(
                place_id="kg_west_lake",
                name="West Lake",
                aliases=["Hồ Tây", "Ho Tay"],
                address="Tay Ho, Hanoi",
            )
        ]
    )
    candidate = explorer_candidate("Phố đi bộ Hồ Gươm", origin="url")
    candidate = candidate.model_copy(
        update={
            "source_places": [
                candidate.source_places[0].model_copy(
                    update={
                        "source_url": "https://www.tiktok.com/@creator/video/1",
                        "platform": "tiktok",
                    }
                )
            ]
        }
    )

    result = asyncio.run(
        service.resolve_all([candidate], hanoi_context())
    ).candidates[0]

    assert result.status in {
        IdentityResolutionStatus.needs_review,
        IdentityResolutionStatus.unresolved,
    }
    assert result.selected_place is None
    assert (
        "source_name_not_verified_by_catalog"
        in result.match_options[0].identity_conflicts
    )


def test_url_place_resolves_verified_catalog_alias() -> None:
    service, _ = service_with(
        [
            provider_candidate(
                place_id="kg_west_lake",
                name="West Lake",
                aliases=["Hồ Tây", "Ho Tay"],
                address="Tay Ho, Hanoi",
            )
        ]
    )
    candidate = explorer_candidate("Hồ Tây", origin="url").model_copy(
        update={
            "source_places": [
                SourcePlaceEvidence(
                    origin="url",
                    evidence_type="transcript",
                    evidence="18h00: Ngắm hoàng hôn Hồ Tây",
                    source_url="https://www.tiktok.com/@creator/video/2",
                    platform="tiktok",
                )
            ]
        }
    )

    result = asyncio.run(
        service.resolve_all([candidate], hanoi_context())
    ).candidates[0]

    assert result.status == IdentityResolutionStatus.resolved
    assert result.selected_place is not None
    assert result.selected_place.canonical_name == "West Lake"
    assert result.resolution_method == SimilarityMethod.alias
