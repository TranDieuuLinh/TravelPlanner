import asyncio
import json

from pydantic import BaseModel, Field, ValidationError

from app.shared.llm import LlmClient, LlmError


CONSOLIDATION_PROMPT = """You consolidate already extracted travel-place mentions.
Return every input index exactly once. Merge aliases/translations only when they clearly
identify the same physical place. Mark destinations, bare street addresses, generic
activities, and places outside the requested ADM as keep=false. Never invent places.
canonical_name must be a proper venue/place name, not an explanation."""


class PlaceGroup(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    member_indexes: list[int] = Field(min_length=1)
    keep: bool = True
    discard_reason: str | None = Field(default=None, max_length=120)


class PlaceConsolidation(BaseModel):
    groups: list[PlaceGroup] = Field(default_factory=list)


def _provider_schema(value):
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value


class GeminiPlaceConsolidator:
    def __init__(
        self,
        client: LlmClient,
        limiter: asyncio.Semaphore,
        *,
        max_output_tokens: int,
        provider: str,
    ) -> None:
        self.client = client
        self.limiter = limiter
        self.max_output_tokens = max_output_tokens
        self.provider = provider

    async def consolidate(self, places: list, input_adm: str | None) -> list:
        if len(places) < 2:
            return places
        places = self._dedupe_exact(places)
        if len(places) < 2:
            return places
        if self.provider == "rules":
            return places
        payload = {
            "inputADM": input_adm,
            "places": [
                {"index": index, "name": place.name, "addressHint": place.address_hint}
                for index, place in enumerate(places)
            ],
        }
        try:
            async with self.limiter:
                raw = await self.client.generate(
                    json.dumps(payload, ensure_ascii=False),
                    system_prompt=CONSOLIDATION_PROMPT,
                    temperature=0.0,
                    max_output_tokens=min(8000, max(4000, self.max_output_tokens)),
                    response_json_schema=_provider_schema(
                        PlaceConsolidation.model_json_schema()
                    ),
                )
            plan = PlaceConsolidation.model_validate(json.loads(raw))
        except (LlmError, json.JSONDecodeError, ValidationError):
            return self._dedupe_exact(places)
        indexes = [index for group in plan.groups for index in group.member_indexes]
        if sorted(indexes) != list(range(len(places))) or len(indexes) != len(set(indexes)):
            return self._dedupe_exact(places)
        consolidated = []
        for group in plan.groups:
            if not group.keep:
                continue
            members = [places[index] for index in group.member_indexes]
            base = max(members, key=lambda item: item.confidence)
            provenance = [source for item in members for source in item.source_places]
            address = next((item.address_hint for item in members if item.address_hint), None)
            consolidated.append(base.model_copy(update={
                "name": group.canonical_name,
                "address_hint": address,
                "source_places": provenance,
                "confidence": max(item.confidence for item in members),
            }))
        return consolidated

    @staticmethod
    def _dedupe_exact(places: list) -> list:
        selected = {}
        for place in places:
            key = " ".join(place.name.casefold().split())
            if key not in selected:
                selected[key] = place
            else:
                selected[key].source_places.extend(place.source_places)
        return list(selected.values())
