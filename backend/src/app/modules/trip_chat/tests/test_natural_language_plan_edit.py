import asyncio

from app.modules.plan_editor.public import NaturalLanguagePlanEdit
from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository
from app.modules.trip_chat.service import TripChatService


class FakePlanEditor:
    def __init__(self, edit: NaturalLanguagePlanEdit) -> None:
        self.edit = edit
        self.calls = []

    async def interpret(self, message: str, planner_output: dict, **kwargs):
        self.calls.append((message, planner_output, kwargs))
        return self.edit


class RecordingGraph:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, graph_input, config):
        self.calls.append((graph_input, config))
        return {
            "response": "Graph handled the request.",
            "decision": type("Decision", (), {"route": "finish"})(),
        }


async def _seed_chat(repository: InMemoryTripChatRepository):
    chat = await repository.create_chat(7, "Hà Nội")
    return await repository.append_exchange(
        7,
        chat.id,
        "Tạo lịch",
        {"content": "Đã tạo lịch.", "route": "itinerary_planner"},
        None,
        {
            "destination": "Hà Nội",
            "days": [
                {
                    "day": 1,
                    "stops": [
                        {"itemId": "item-lake", "placeId": "lake", "name": "Hồ Gươm"},
                        {"itemId": "item-temple", "placeId": "temple", "name": "Đền Ngọc Sơn"},
                    ],
                    "legs": [],
                }
            ],
        },
    )


async def _seed_legacy_chat(repository: InMemoryTripChatRepository):
    chat = await repository.create_chat(7, "Hà Nội legacy")
    return await repository.append_exchange(
        7,
        chat.id,
        "Tạo lịch cũ",
        {"content": "Đã tạo lịch.", "route": "itinerary_planner"},
        None,
        {
            "destination": "Hà Nội",
            "days": [
                {
                    "day": 1,
                    "stops": [{"itemId": None, "placeId": "lake", "name": "Hồ Gươm"}],
                    "legs": [],
                }
            ],
        },
    )


def test_chat_edit_uses_existing_delete_mutation_and_skips_root_graph() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_chat(repository)
        graph = RecordingGraph()
        editor = FakePlanEditor(
            NaturalLanguagePlanEdit(
                action="delete",
                confidence=0.99,
                day=1,
                item_id="item-lake",
                response="Đã xóa Hồ Gươm khỏi ngày 1.",
            )
        )
        service = TripChatService(repository, graph, plan_editor=editor)

        updated = await service.send(7, chat.id, "Xóa Hồ Gươm khỏi ngày 1")

        assert [item["itemId"] for item in updated.current_planner_output["days"][0]["stops"]] == ["item-temple"]
        assert updated.messages[-1].route == "plan_editor"
        assert updated.messages[-1].content == "Đã xóa Hồ Gươm khỏi ngày 1."
        assert graph.calls == []

    asyncio.run(scenario())


def test_chat_edit_uses_existing_add_mutation() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_chat(repository)
        editor = FakePlanEditor(
            NaturalLanguagePlanEdit(
                action="add",
                confidence=0.99,
                day=1,
                position=1,
                item={"name": "Văn Miếu", "durationMinutes": 90},
                response="Đã thêm Văn Miếu vào ngày 1.",
            )
        )
        service = TripChatService(repository, RecordingGraph(), plan_editor=editor)

        updated = await service.send(7, chat.id, "Thêm Văn Miếu vào ngày 1")

        stops = updated.current_planner_output["days"][0]["stops"]
        assert [item["name"] for item in stops] == ["Hồ Gươm", "Văn Miếu", "Đền Ngọc Sơn"]
        assert stops[1]["durationMinutes"] == 90

    asyncio.run(scenario())


def test_chat_edit_uses_existing_update_mutation() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_chat(repository)
        editor = FakePlanEditor(
            NaturalLanguagePlanEdit(
                action="update",
                confidence=0.99,
                day=1,
                item_id="item-lake",
                item={"durationMinutes": 120, "personalNotes": "Đi sáng sớm"},
                response="Đã sửa thời lượng và ghi chú của Hồ Gươm.",
            )
        )
        service = TripChatService(repository, RecordingGraph(), plan_editor=editor)

        updated = await service.send(
            7,
            chat.id,
            "Cho Hồ Gươm 2 tiếng và ghi chú đi sáng sớm",
        )

        stop = updated.current_planner_output["days"][0]["stops"][0]
        assert stop["durationMinutes"] == 120
        assert stop["personalNotes"] == "Đi sáng sớm"

    asyncio.run(scenario())


def test_non_edit_message_continues_to_root_graph() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_chat(repository)
        graph = RecordingGraph()
        editor = FakePlanEditor(NaturalLanguagePlanEdit(action="none", confidence=0.99))
        service = TripChatService(repository, graph, plan_editor=editor)

        await service.send(7, chat.id, "Hà Nội có gì vui?")

        assert len(graph.calls) == 1

    asyncio.run(scenario())


def test_chat_editor_receives_compatible_id_for_legacy_stop() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_legacy_chat(repository)
        graph = RecordingGraph()
        editor = FakePlanEditor(NaturalLanguagePlanEdit(action="none", confidence=0.99))
        service = TripChatService(repository, graph, plan_editor=editor)

        await service.send(7, chat.id, "Xóa Hồ Gươm")

        projected_stop = editor.calls[0][1]["days"][0]["stops"][0]
        assert projected_stop["itemId"] == "planner-1-1-lake"
        stored = await repository.get_chat(7, chat.id)
        assert stored.current_planner_output["days"][0]["stops"][0]["itemId"] is None

    asyncio.run(scenario())
