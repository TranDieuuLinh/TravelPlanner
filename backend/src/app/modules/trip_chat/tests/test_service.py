import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

from app.modules.trip_chat.contract import TripChat
from app.modules.trip_chat.service import TripChatService


def _chat() -> TripChat:
    now = datetime.now(timezone.utc)
    return TripChat(
        id="chat-1",
        title="Hà Nội",
        revision=1,
        has_itinerary=True,
        created_at=now,
        updated_at=now,
        thread_id="thread-1",
        current_itinerary={"itineraryId": "legacy-1"},
        current_planner_output={"destination": "Hà Nội", "days": []},
    )


class FakeRepository:
    def __init__(self) -> None:
        self.chat = _chat()
        self.appended = None

    async def get_chat(self, user_id: int, chat_id: str):
        return self.chat

    async def append_exchange(self, *args):
        self.appended = args
        return self.chat


class FakeGraph:
    def __init__(self, result) -> None:
        self.result = result
        self.input = None

    async def ainvoke(self, graph_input, config):
        self.input = graph_input
        return self.result


class AliasedPlannerOutput(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda value: (
            "plannerOutput" if value == "planner_output" else value
        )
    )

    planner_output: str


def test_send_persists_planner_output_without_overwriting_legacy_contract() -> None:
    planner_output = {"destination": "Hà Nội", "days": [{"day": 1, "stops": []}]}
    repository = FakeRepository()
    graph = FakeGraph(
        {
            "response": "Đã tạo lịch trình.",
            "decision": SimpleNamespace(route="plan_trip"),
            "itinerary": None,
            "planner_output": planner_output,
        }
    )

    result = asyncio.run(TripChatService(repository, graph).send(7, "chat-1", "Đi Hà Nội"))

    assert result is repository.chat
    assert graph.input["existing_itinerary"] == {"itineraryId": "legacy-1"}
    assert repository.appended[-2] is None
    assert repository.appended[-1] == planner_output


def test_send_keeps_new_and_legacy_outputs_in_separate_arguments() -> None:
    legacy = {"itineraryId": "legacy-2"}
    planner_output = {"destination": "Huế", "days": []}
    repository = FakeRepository()
    graph = FakeGraph(
        {
            "response": "Đã cập nhật.",
            "decision": SimpleNamespace(route="edit_plan"),
            "itinerary": legacy,
            "planner_output": planner_output,
        }
    )

    asyncio.run(TripChatService(repository, graph).send(7, "chat-1", "Đổi lịch"))

    assert repository.appended[-2] == legacy
    assert repository.appended[-1] == planner_output


def test_send_serializes_planner_output_with_api_aliases() -> None:
    repository = FakeRepository()
    graph = FakeGraph(
        {
            "response": "Đã tạo.",
            "decision": SimpleNamespace(route="plan_trip"),
            "planner_output": AliasedPlannerOutput(planner_output="value"),
        }
    )

    asyncio.run(TripChatService(repository, graph).send(7, "chat-1", "Tạo lịch"))

    assert repository.appended[-1] == {"plannerOutput": "value"}
