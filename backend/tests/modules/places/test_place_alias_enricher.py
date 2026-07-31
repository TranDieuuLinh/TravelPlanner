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
    assert enriched[0].alternate_names == ["Ethnology Museum"]
    assert enriched[0].search_names == [
        "Vietnam Museum of Ethnology",
        "Bảo tàng Dân tộc học Việt Nam",
    ]
    assert llm.payload is not None
    assert llm.payload["places"][0]["searchRegion"] == "Hanoi"


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
