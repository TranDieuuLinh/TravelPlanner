import asyncio
import json

from app.modules.place_checker.adapters.gemini_subplace_note_generator import (
    GeminiSubplaceNoteGenerator,
)
from app.modules.place_checker.subplaces.contract import (
    SubplaceOfferItemContext,
    SubplaceGroup,
    SubplaceNoteRequest,
    SubplaceSummary,
)
from app.modules.place_checker.subplaces.service import SubplaceDisplayService


def _group(*, with_activity: bool = True) -> SubplaceGroup:
    return SubplaceGroup(
        parent_place_id="place:ba-dinh",
        parent_place_name="Quảng trường Ba Đình",
        total_count=1,
        items=[
            SubplaceSummary(
                place_id="subplace:fish-pond",
                name="Ao cá Bác Hồ",
                offer_items=(
                    [
                        SubplaceOfferItemContext(
                            activity_item_id="activity:fish-pond-visit",
                            activity_item_name="tham quan Ao cá Bác Hồ",
                            action="visit",
                            display_template="{action} {item} tại {subplace}",
                        )
                    ]
                    if with_activity
                    else []
                ),
            )
        ],
    )


class FakeCatalog:
    def __init__(self, group: SubplaceGroup) -> None:
        self.group = group

    async def list_subplaces(self, parent_place_ids, *, per_parent_limit=50):
        assert parent_place_ids == ["place:ba-dinh"]
        assert per_parent_limit == 50
        return [self.group]


class FakeGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_many(self, requests):
        self.calls += 1
        assert requests[0].parent_place_name == "Quảng trường Ba Đình"
        assert requests[0].offer_items[0].activity_item_id == "activity:fish-pond-visit"
        return {requests[0].request_id: "Bạn có thể tham quan Ao cá Bác Hồ."}


def test_service_only_exposes_gemini_note_grounded_in_activity_item() -> None:
    generator = FakeGenerator()
    service = SubplaceDisplayService(FakeCatalog(_group()), generator)

    first = asyncio.run(service.list_subplaces(["place:ba-dinh"]))
    second = asyncio.run(service.list_subplaces(["place:ba-dinh"]))

    item = first[0].items[0]
    assert item.note == "Bạn có thể tham quan Ao cá Bác Hồ."
    assert item.note_source == "gemini"
    assert item.note_activity_item_ids == ["activity:fish-pond-visit"]
    assert generator.calls == 1
    assert second[0].items[0].note == item.note

    public_payload = first[0].model_dump(by_alias=True)
    assert "parentPlaceName" not in public_payload
    assert "offerItems" not in public_payload["items"][0]


def test_service_does_not_fabricate_note_without_activity_or_gemini() -> None:
    without_activity = SubplaceDisplayService(FakeCatalog(_group(with_activity=False)), None)
    without_gemini = SubplaceDisplayService(FakeCatalog(_group()), None)

    no_activity_result = asyncio.run(
        without_activity.list_subplaces(["place:ba-dinh"])
    )
    no_gemini_result = asyncio.run(without_gemini.list_subplaces(["place:ba-dinh"]))

    assert no_activity_result[0].items[0].note is None
    assert no_gemini_result[0].items[0].note is None
    assert no_gemini_result[0].items[0].note_source is None


def test_service_hides_note_when_gemini_fails() -> None:
    class FailingGenerator:
        async def generate_many(self, requests):
            raise RuntimeError("provider unavailable")

    group = _group()
    group.items[0].note = "Ghi chú cũ không được tin cậy"
    group.items[0].note_source = "gemini"
    service = SubplaceDisplayService(FakeCatalog(group), FailingGenerator())

    result = asyncio.run(service.list_subplaces(["place:ba-dinh"]))

    assert result[0].items[0].note is None
    assert result[0].items[0].note_source is None
    assert result[0].items[0].note_activity_item_ids == []


def test_gemini_generator_sends_offer_item_activity_context() -> None:
    class FakeLlmClient:
        def __init__(self) -> None:
            self.payload = None
            self.options = None

        async def generate(self, user_prompt, **options):
            self.payload = json.loads(user_prompt)
            self.options = options
            request_id = self.payload["subplaces"][0]["requestId"]
            return json.dumps(
                {
                    "notes": [
                        {
                            "requestId": request_id,
                            "note": "Bạn có thể tham quan Ao cá Bác Hồ.",
                        }
                    ]
                },
                ensure_ascii=False,
            )

    client = FakeLlmClient()
    generator = GeminiSubplaceNoteGenerator(client)
    request = SubplaceNoteRequest(
        request_id="a" * 64,
        parent_place_name="Quảng trường Ba Đình",
        subplace_name="Ao cá Bác Hồ",
        offer_items=_group().items[0].offer_items,
    )

    notes = asyncio.run(generator.generate_many([request]))

    activity = client.payload["subplaces"][0]["offerItems"][0]
    assert activity == {
        "relationshipType": "Offer_Item",
        "activityItemId": "activity:fish-pond-visit",
        "activityItemName": "tham quan Ao cá Bác Hồ",
        "action": "visit",
        "displayTemplate": "{action} {item} tại {subplace}",
    }
    assert client.options["temperature"] == 0.0
    assert client.options["response_json_schema"] is not None
    assert notes == {"a" * 64: "Bạn có thể tham quan Ao cá Bác Hồ."}
