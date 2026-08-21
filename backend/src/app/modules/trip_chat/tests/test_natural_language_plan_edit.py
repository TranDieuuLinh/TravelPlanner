import asyncio

from app.modules.plan_editor.public import NaturalLanguagePlanEdit
from app.modules.supervisor.public import SupervisorDecision
from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository
from app.modules.trip_chat.service import TripChatService


class RecordingGraph:
    def __init__(self, edit: NaturalLanguagePlanEdit | None = None) -> None:
        self.edit = edit
        self.calls = []

    async def ainvoke(self, graph_input, config):
        self.calls.append((graph_input, config))
        route = "plan_editor" if self.edit is not None else "finish"
        return {
            "response": self.edit.response if self.edit else "Graph handled the request.",
            "decision": SupervisorDecision(
                route=route,
                confidence=0.99,
                reason="test",
                response=None if self.edit else "Graph handled the request.",
                plan_edit=self.edit,
            ),
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
            "days": [{"day": 1, "stops": [
                {"itemId": None, "placeId": "lake", "name": "Hồ Gươm"}
            ], "legs": []}],
        },
    )


def _run_edit(edit: NaturalLanguagePlanEdit, message: str):
    async def scenario():
        repository = InMemoryTripChatRepository()
        before = await _seed_chat(repository)
        graph = RecordingGraph(edit)
        updated = await TripChatService(repository, graph).send(
            7, before.id, message
        )
        return before, updated, graph

    return asyncio.run(scenario())


def test_delete_uses_manual_mutation_with_one_graph_call_and_one_revision() -> None:
    before, updated, graph = _run_edit(
        NaturalLanguagePlanEdit(
            action="delete", confidence=0.99, day=1, item_id="item-lake",
            response="Đã xóa Hồ Gươm khỏi ngày 1.",
        ),
        "Xóa Hồ Gươm khỏi ngày 1",
    )

    stops = updated.current_planner_output["days"][0]["stops"]
    assert [item["itemId"] for item in stops] == ["item-temple"]
    assert updated.revision == before.revision + 1
    assert updated.messages[-1].route == "plan_editor"
    assert len(graph.calls) == 1


def test_add_uses_manual_mutation() -> None:
    _before, updated, _graph = _run_edit(
        NaturalLanguagePlanEdit(
            action="add", confidence=0.99, day=1, position=1,
            item={"name": "Văn Miếu", "durationMinutes": 90},
            response="Đã thêm Văn Miếu vào ngày 1.",
        ),
        "Thêm Văn Miếu vào ngày 1",
    )
    stops = updated.current_planner_output["days"][0]["stops"]
    assert [item["name"] for item in stops] == ["Hồ Gươm", "Văn Miếu", "Đền Ngọc Sơn"]
    assert stops[1]["durationMinutes"] == 90


def test_update_uses_manual_mutation() -> None:
    _before, updated, _graph = _run_edit(
        NaturalLanguagePlanEdit(
            action="update", confidence=0.99, day=1, item_id="item-lake",
            item={"durationMinutes": 120, "personalNotes": "Đi sáng sớm"},
            response="Đã sửa thời lượng và ghi chú của Hồ Gươm.",
        ),
        "Cho Hồ Gươm 2 tiếng và ghi chú đi sáng sớm",
    )
    stop = updated.current_planner_output["days"][0]["stops"][0]
    assert stop["durationMinutes"] == 120
    assert stop["personalNotes"] == "Đi sáng sớm"


def test_reorder_uses_manual_mutation() -> None:
    _before, updated, _graph = _run_edit(
        NaturalLanguagePlanEdit(
            action="reorder", confidence=0.99, day=1,
            item_ids=["item-temple", "item-lake"],
            response="Đã đổi thứ tự ngày 1.",
        ),
        "Đi Đền Ngọc Sơn trước Hồ Gươm",
    )
    stops = updated.current_planner_output["days"][0]["stops"]
    assert [item["itemId"] for item in stops] == ["item-temple", "item-lake"]


def test_non_edit_message_uses_root_graph_once() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_chat(repository)
        graph = RecordingGraph()
        await TripChatService(repository, graph).send(7, chat.id, "Hà Nội có gì vui?")
        assert len(graph.calls) == 1

    asyncio.run(scenario())


def test_supervisor_receives_compatible_id_without_mutating_legacy_snapshot() -> None:
    async def scenario():
        repository = InMemoryTripChatRepository()
        chat = await _seed_legacy_chat(repository)
        graph = RecordingGraph()
        await TripChatService(repository, graph).send(7, chat.id, "Xóa Hồ Gươm")

        projected = graph.calls[0][0]["existing_planner_output"]
        assert projected["days"][0]["items"][0]["itemId"] == "planner-1-1-lake"
        stored = await repository.get_chat(7, chat.id)
        assert stored.current_planner_output["days"][0]["stops"][0]["itemId"] is None

    asyncio.run(scenario())
