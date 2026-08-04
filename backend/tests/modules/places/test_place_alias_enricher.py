import asyncio
import json

from app.integrations.llm.base import LLMClient
from app.modules.places.alias_enricher import LLMPlaceAliasEnricher
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


class FakeAliasLLM(LLMClient):
    def __init__(self, response: str) -> None:
        self.response = response
        self.payload: dict | None = None

    async def generate_profile_plan(self, prompt: str) -> str:
        raise NotImplementedError

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        return self.response

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        self.payload = json.loads(user_payload)
        return self.response


def test_alias_enricher_preserves_original_and_adds_bilingual_names() -> None:
    llm = FakeAliasLLM(
        json.dumps(
            {
                "aliasSets": [
                    {
                        "index": 0,
                        "originalName": "Ethnology Museum",
                        "englishNames": [
                            "Vietnam Museum of Ethnology",
                        ],
                        "vietnameseNames": [
                            "Bảo tàng Dân tộc học Việt Nam",
                        ],
                        "alternateNames": [
                            "Ethnology Museum",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
    candidate = UnifiedPlaceCandidate(
        name="Ethnology Museum",
        category="culture",
        searchRegion="Hanoi",
    )

    enriched = asyncio.run(
        LLMPlaceAliasEnricher(llm).enrich(
            [candidate],
            destination="Hanoi",
        )
    )

    assert enriched[0].name == "Ethnology Museum"
    assert enriched[0].original_name == "Ethnology Museum"
    assert enriched[0].english_names == [
        "Vietnam Museum of Ethnology"
    ]
    assert enriched[0].vietnamese_names == [
        "Bảo tàng Dân tộc học Việt Nam"
    ]
    assert enriched[0].alternate_names == []
    assert enriched[0].search_names == [
        "Bảo tàng Dân tộc học Việt Nam",
        "Vietnam Museum of Ethnology",
    ]
    assert llm.payload is not None
    assert llm.payload["places"][0]["searchRegion"] == "Hanoi"


def test_alias_enricher_keeps_only_one_official_name_per_language() -> None:
    llm = FakeAliasLLM(
        json.dumps(
            {
                "aliasSets": [
                    {
                        "index": 0,
                        "originalName": "Dong Xuan Market",
                        "englishNames": [
                            "Dong Xuan Market",
                            "Dong Xuan Night Bazaar",
                        ],
                        "vietnameseNames": [
                            "Chợ Đồng Xuân",
                            "Chợ đêm Đồng Xuân",
                        ],
                        "alternateNames": ["Cho Dong Xuan"],
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    enriched = asyncio.run(
        LLMPlaceAliasEnricher(llm).enrich(
            [UnifiedPlaceCandidate(name="Dong Xuan Market")],
            destination="Hanoi",
        )
    )

    assert enriched[0].vietnamese_names == ["Chợ Đồng Xuân"]
    assert enriched[0].english_names == ["Dong Xuan Market"]
    assert enriched[0].alternate_names == []
    assert enriched[0].search_names == [
        "Chợ Đồng Xuân",
        "Dong Xuan Market",
    ]


def test_alias_enricher_fails_open_when_llm_is_unavailable() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Dong Xuan St",
        searchNames=["Phố Đồng Xuân"],
    )

    enriched = asyncio.run(
        LLMPlaceAliasEnricher(
            FakeAliasLLM("not-json")
        ).enrich([candidate], destination="Hà Nội")
    )

    assert enriched == [candidate]


def test_alias_enricher_rejects_specific_venue_alias_for_generic_activity() -> None:
    llm = FakeAliasLLM(
        json.dumps(
            {
                "aliasSets": [
                    {
                        "index": 0,
                        "originalName": "dessert",
                        "englishNames": ["Four Seasons Sweet Soup"],
                        "vietnameseNames": ["Chè 4 Mùa"],
                        "alternateNames": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    enriched = asyncio.run(
        LLMPlaceAliasEnricher(llm).enrich(
            [UnifiedPlaceCandidate(name="dessert")],
            destination="Hanoi",
        )
    )

    assert enriched[0].name == "dessert"
    assert enriched[0].vietnamese_names == []
    assert enriched[0].english_names == []
    assert enriched[0].search_names == ["dessert"]
    assert enriched[0].generated_lookup_aliases == []
