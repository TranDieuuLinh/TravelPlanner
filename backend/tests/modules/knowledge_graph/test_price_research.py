from __future__ import annotations

import asyncio
import json

from app.integrations.llm.base import (
    GroundedStructuredResult,
    GroundingSource,
)
from app.integrations.search.base import WebSearchResult
from app.modules.knowledge_graph.price_research import (
    PriceResearchStatus,
    TravelPlacePriceCandidate,
    TravelPlacePriceOutcome,
    research_travel_place_price,
    research_travel_place_price_from_sources,
    research_travel_place_price_with_web_search,
)


class FakeGroundedClient:
    def __init__(self, text: str, *, with_source: bool = True) -> None:
        self.text = text
        self.with_source = with_source
        self.system_prompt = ""

    async def generate_grounded_structured_json(self, *args, **kwargs):
        self.system_prompt = args[0]
        del kwargs
        sources = (
            GroundingSource(
                title="Official tickets",
                uri="https://official.example/tickets",
            ),
        ) if self.with_source else ()
        return GroundedStructuredResult(
            text=self.text,
            sources=sources,
            search_queries=("Văn Miếu giá vé",),
        )


def _candidate() -> TravelPlacePriceCandidate:
    return TravelPlacePriceCandidate(
        entityId="travel_place_1",
        canonicalName="Văn Miếu - Quốc Tử Giám",
        address="58 Quốc Tử Giám, Hà Nội",
        city="Hà Nội",
        country="Vietnam",
        placeType="Tourist attraction",
        reviewCount=1000,
    )


def test_grounded_price_with_citation_is_verified() -> None:
    client = FakeGroundedClient(
        """{
          "identityMatched": true,
          "status": "priced",
          "currency": "VND",
          "minAmount": 70000,
          "maxAmount": 70000,
          "representativeAmount": 70000,
          "pricingUnit": "per_adult",
          "sourceAuthority": "official",
          "sourceIndexes": [0],
          "confidence": 0.95
        }"""
    )
    outcome = asyncio.run(
        research_travel_place_price(
            _candidate(),
            llm_client=client,
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.verified_price
    assert outcome.representative_amount == 70_000
    assert outcome.min_amount == 70_000
    assert outcome.max_amount == 70_000
    assert outcome.pricing_unit == "per_adult"
    assert outcome.price_label == "Vé tiêu chuẩn người lớn: 70.000 VND"
    assert outcome.sources[0].uri == "https://official.example/tickets"
    assert "TravelPlace canonical" in client.system_prompt
    assert "property admission_price" in client.system_prompt
    assert "Chỉ lấy giá vé vào cửa tiêu chuẩn" in client.system_prompt


def test_verified_price_is_normalized_to_one_standard_adult_price() -> None:
    client = FakeGroundedClient(
        """{
          "identityMatched": true,
          "status": "priced",
          "currency": "VND",
          "minAmount": 35000,
          "maxAmount": 70000,
          "representativeAmount": 70000,
          "pricingUnit": "per_person",
          "priceLabel": "Người lớn 70.000; vé ưu tiên 35.000",
          "sourceAuthority": "official",
          "sourceIndexes": [0],
          "confidence": 0.95
        }"""
    )

    outcome = asyncio.run(
        research_travel_place_price(
            _candidate(),
            llm_client=client,
            model_name="test-model",
        )
    )

    assert outcome.min_amount == 70_000
    assert outcome.max_amount == 70_000
    assert outcome.representative_amount == 70_000
    assert outcome.pricing_unit == "per_adult"
    assert outcome.price_label == "Vé tiêu chuẩn người lớn: 70.000 VND"


def test_price_without_grounding_source_is_not_verified() -> None:
    outcome = asyncio.run(
        research_travel_place_price(
            _candidate(),
            llm_client=FakeGroundedClient(
                """{
                  "identityMatched": true,
                  "status": "priced",
                  "currency": "VND",
                  "representativeAmount": 70000,
                  "sourceIndexes": [0],
                  "confidence": 0.9
                }""",
                with_source=False,
            ),
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.ambiguous
    assert outcome.error == "missing_grounding_source"
    assert outcome.can_apply is False


def test_mismatched_place_identity_is_not_verified() -> None:
    outcome = asyncio.run(
        research_travel_place_price(
            _candidate(),
            llm_client=FakeGroundedClient(
                """{
                  "identityMatched": false,
                  "status": "priced",
                  "currency": "VND",
                  "representativeAmount": 70000,
                  "sourceIndexes": [0],
                  "confidence": 0.3
                }"""
            ),
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.ambiguous
    assert outcome.can_apply is False


def test_verified_status_without_public_grounded_source_cannot_apply() -> None:
    outcome = TravelPlacePriceOutcome(
        entityId="travel_place_1",
        status="verified_price",
        fetchedAt="2026-08-06T00:00:00Z",
        model="test-model",
        currency="VND",
        representativeAmount=70_000,
        sources=[{"title": "Invalid source", "uri": "not-a-public-url"}],
    )

    assert outcome.has_grounded_source is False
    assert outcome.can_apply is False


class FakeWebSearchProvider:
    async def search(self, query: str, *, limit: int):
        assert "Văn Miếu" in query
        assert limit == 8
        return [
            WebSearchResult(
                title="Official tickets",
                uri="https://official.example/tickets",
                snippet="Giá vé người lớn hiện tại là 70.000 VND.",
            )
        ]


class FakeStructuredClient:
    async def generate_structured_json(self, *args, **kwargs):
        assert "Playwright" in args[0]
        payload = json.loads(args[1])
        assert payload["searchResults"][0]["uri"] == (
            "https://official.example/tickets"
        )
        assert kwargs["response_schema"]
        return """{
          "identityMatched": true,
          "status": "priced",
          "currency": "VND",
          "representativeAmount": 70000,
          "sourceIndexes": [0],
          "confidence": 0.9
        }"""


def test_playwright_search_results_are_validated_as_price_sources() -> None:
    outcome = asyncio.run(
        research_travel_place_price_with_web_search(
            _candidate(),
            search_provider=FakeWebSearchProvider(),
            llm_client=FakeStructuredClient(),
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.verified_price
    assert outcome.representative_amount == 70_000
    assert outcome.sources[0].uri == "https://official.example/tickets"
    assert outcome.can_apply is True


class FakeSourceExtractionClient:
    async def generate_structured_json(self, *args, **kwargs):
        assert "nguồn web do application cung cấp" in args[0]
        payload = json.loads(args[1])
        assert payload["sources"][0]["uri"] == "https://official.example/tickets"
        assert kwargs["response_schema"]
        return """{
          "identityMatched": true,
          "status": "priced",
          "currency": "VND",
          "representativeAmount": 70000,
          "sourceIndexes": [0],
          "confidence": 0.9
        }"""


def test_provided_sources_are_validated_as_price_sources() -> None:
    outcome = asyncio.run(
        research_travel_place_price_from_sources(
            _candidate(),
            sources=[
                {
                    "title": "Official tickets",
                    "uri": "https://official.example/tickets",
                    "snippet": "Giá vé người lớn hiện tại là 70.000 VND.",
                }
            ],
            llm_client=FakeSourceExtractionClient(),
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.verified_price
    assert outcome.representative_amount == 70_000
    assert outcome.sources[0].uri == "https://official.example/tickets"
    assert outcome.can_apply is True


def test_provided_sources_require_valid_http_sources() -> None:
    outcome = asyncio.run(
        research_travel_place_price_from_sources(
            _candidate(),
            sources=[
                {
                    "title": "Bad source",
                    "uri": "not-a-public-url",
                    "snippet": "Giá vé người lớn hiện tại là 70.000 VND.",
                }
            ],
            llm_client=FakeSourceExtractionClient(),
            model_name="test-model",
        )
    )

    assert outcome.status == PriceResearchStatus.not_found
    assert outcome.error == "missing_input_sources"
    assert outcome.can_apply is False
