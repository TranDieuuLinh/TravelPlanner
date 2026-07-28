import asyncio
from typing import Any

from app.modules.places.resolver import NominatimPlaceResolver
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


class FakeNominatimResolver(NominatimPlaceResolver):
    def __init__(self, results: list[dict[str, Any]]) -> None:
        super().__init__(
            base_url="https://example.invalid",
            user_agent="VSF-Travel-Test/1.0",
        )
        self.results = results

    async def _search(self, query: str) -> list[dict[str, Any]]:
        return self.results


def test_nominatim_resolver_maps_provider_result_to_place_contract() -> None:
    resolver = FakeNominatimResolver(
        [
            {
                "osm_type": "node",
                "osm_id": 123,
                "name": "Mì Quảng Bà Mua",
                "display_name": "Mì Quảng Bà Mua, Đà Nẵng, Việt Nam",
                "lat": "16.0592",
                "lon": "108.2131",
                "importance": 0.5,
                "address": {
                    "city": "Đà Nẵng",
                    "country": "Việt Nam",
                    "country_code": "vn",
                },
                "extratags": {
                    "description": "Nhà hàng chuyên món mì Quảng."
                },
                "licence": "Data © OpenStreetMap contributors",
            }
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Mì Quảng Bà Mua",
        category="food",
        sources=[{"type": "url", "url": "https://example.com/reel"}],
        confidence=0.8,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Đà Nẵng")
    )

    assert result.status == "resolved"
    assert result.external_id == "node:123"
    assert result.country_code == "VN"
    assert str(result.latitude) == "16.0592"
    assert result.data_confidence == "high"


def test_nominatim_resolver_keeps_unmatched_candidate_without_question() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Quán chưa xác định",
        category="food",
        sources=[{"type": "ocr", "url": None}],
        confidence=0.4,
    )

    result = asyncio.run(
        FakeNominatimResolver([]).resolve(
            candidate,
            destination="Đà Nẵng",
        )
    )

    assert result.status == "unresolved"
    assert result.name == "Quán chưa xác định"
    assert result.latitude is None
