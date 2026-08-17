import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

from app.modules.conversation_memory.adapters.in_memory import InMemoryMemoryRepository
from app.modules.conversation_memory.service import ConversationMemoryService
from app.modules.trip_chat.contract import TripChat, TripChatMessage
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

    async def list_chats(self, user_id: int, *, limit: int = 30, offset: int = 0):
        return [self.chat][offset : offset + limit]

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


class FailingGraph:
    async def ainvoke(self, graph_input, config):
        raise RuntimeError("Graph execution failed")


class AliasedPlannerOutput(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda value: (
            "plannerOutput" if value == "planner_output" else value
        )
    )

    planner_output: str


class TestTripChatService(unittest.TestCase):
    def test_bootstrap_returns_recent_summaries_and_selected_chat(self) -> None:
        repository = FakeRepository()
        result = asyncio.run(
            TripChatService(repository, FakeGraph({})).bootstrap(
                7, chat_id="chat-1", limit=10
            )
        )

        self.assertEqual([chat.id for chat in result.chats], ["chat-1"])
        self.assertIs(result.active_chat, repository.chat)

    def test_send_persists_planner_output_without_overwriting_legacy_contract(self) -> None:
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

        self.assertIs(result, repository.chat)
        self.assertEqual(graph.input["existing_itinerary"], {"itineraryId": "legacy-1"})
        self.assertIsNone(repository.appended[-2])
        self.assertEqual(repository.appended[-1], planner_output)

    def test_send_passes_six_recent_messages_with_explicit_roles(self) -> None:
        repository = FakeRepository()
        repository.chat.messages = [
            TripChatMessage(
                id=f"message-{index}",
                role="user" if index % 2 == 0 else "assistant",
                content=f"Nội dung {index}",
                created_at=datetime.now(timezone.utc),
            )
            for index in range(8)
        ]
        graph = FakeGraph(
            {
                "response": "Đã xử lý.",
                "decision": SimpleNamespace(route="finish"),
            }
        )

        asyncio.run(TripChatService(repository, graph).send(7, "chat-1", "Tin mới"))

        self.assertEqual(
            graph.input["recent_messages"],
            [
                "User: Nội dung 2",
                "Assistant: Nội dung 3",
                "User: Nội dung 4",
                "Assistant: Nội dung 5",
                "User: Nội dung 6",
                "Assistant: Nội dung 7",
            ],
        )

    def test_send_keeps_new_and_legacy_outputs_in_separate_arguments(self) -> None:
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

        self.assertEqual(repository.appended[-2], legacy)
        self.assertEqual(repository.appended[-1], planner_output)

    def test_send_serializes_planner_output_with_api_aliases(self) -> None:
        repository = FakeRepository()
        graph = FakeGraph(
            {
                "response": "Đã tạo.",
                "decision": SimpleNamespace(route="plan_trip"),
                "planner_output": AliasedPlannerOutput(planner_output="value"),
            }
        )

        asyncio.run(TripChatService(repository, graph).send(7, "chat-1", "Tạo lịch"))

        self.assertEqual(repository.appended[-1], {"plannerOutput": "value"})

    def test_send_graph_failure_does_not_change_memory(self) -> None:
        repository = FakeRepository()
        graph = FailingGraph()
        memory_repo = InMemoryMemoryRepository()
        memory_service = ConversationMemoryService(memory_repo)

        service = TripChatService(repository, graph, memory_service)
        try:
            asyncio.run(service.send(7, "chat-1", "Lên plan cho tôi"))
        except RuntimeError:
            pass

        context = asyncio.run(memory_service.load_context("chat-1", 7))
        self.assertEqual(context.version, 0)
        self.assertIsNone(context.destination)
        self.assertIsNone(context.duration_days)

    def test_send_graph_success_persists_bootstrap_destination_and_duration(self) -> None:
        repository = FakeRepository()
        repository.chat.current_itinerary = {"destination": "Hà Nội", "days": [1, 2, 3]}
        graph = FakeGraph(
            {
                "response": "Đã xử lý.",
                "decision": SimpleNamespace(route="explorer"),
            }
        )
        memory_repo = InMemoryMemoryRepository()
        memory_service = ConversationMemoryService(memory_repo)

        service = TripChatService(repository, graph, memory_service)
        asyncio.run(service.send(7, "chat-1", "Lên plan cho tôi"))

        context = asyncio.run(memory_service.load_context("chat-1", 7))
        self.assertEqual(context.version, 1)
        self.assertEqual(context.destination, "Hà Nội")
        self.assertEqual(context.duration_days, 3)

    def test_send_user_destination_change_overwrites_bootstrap(self) -> None:
        repository = FakeRepository()
        repository.chat.current_itinerary = {"destination": "Hà Nội", "days": [1, 2, 3]}
        graph = FakeGraph(
            {
                "response": "Đã đổi điểm đến.",
                "decision": SimpleNamespace(route="explorer"),
            }
        )
        memory_repo = InMemoryMemoryRepository()
        memory_service = ConversationMemoryService(memory_repo)

        service = TripChatService(repository, graph, memory_service)
        asyncio.run(service.send(7, "chat-1", "Đổi sang Đà Nẵng 5 ngày"))

        context = asyncio.run(memory_service.load_context("chat-1", 7))
        self.assertEqual(context.version, 1)
        self.assertEqual(context.destination, "Đà Nẵng")
        self.assertEqual(context.duration_days, 5)
