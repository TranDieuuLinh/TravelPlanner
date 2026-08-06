from __future__ import annotations

import asyncio

from app.integrations.llm.base import (
    GroundedStructuredResult,
    GroundingSource,
)
from app.modules.knowledge_graph.price_research import (
    PriceResearchStatus,
    TravelPlacePriceCandidate,
    research_travel_place_price,
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
    assert outcome.sources[0].uri == "https://official.example/tickets"
    assert "TravelPlace canonical" in client.system_prompt
    assert "property admission_price" in client.system_prompt


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
