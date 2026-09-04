"""API integration tests for Trip Chat + Conversation Memory (Phase 03).

Verifies /v1/trip-chats/{chat_id}/messages API behavior, camelCase response schemas,
and backward compatibility for /v1/agent/invoke.
"""

import asyncio

from fastapi.testclient import TestClient

from app.api.dependencies import get_graph
from app.main import create_app
from app.modules.auth.public import AuthUser, require_current_user
from app.modules.conversation_memory.public import (
    InMemoryMemoryRepository,
    build_conversation_memory_service,
)
from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.public import SupervisorService
from app.modules.trip_chat.public import (
    InMemoryTripChatRepository,
)
from app.orchestration.root_graph import create_root_graph


class DummyClassifier:
    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        msg = payload.message.lower()
        if "hà nội" in msg or "lên plan" in msg:
            return ClassifierResult(
                route="explorer",
                confidence=1.0,
                reason="Destination or plan intent detected",
                response=None,
            )
        return ClassifierResult(
            route="finish",
            confidence=1.0,
            reason="Greeting response",
            response="Chào bạn! Tôi có thể giúp gì cho chuyến đi của bạn?",
        )


from datetime import datetime, timezone

from app.core.config import Settings

from app.modules.supervisor.public import SupervisorDecision

class DummyRootGraph:
    async def ainvoke(self, state, config=None):
        return {
            "decision": SupervisorDecision(
                route="explorer",
                confidence=1.0,
                reason="mock reason"
            ),
            "response": "Mock response"
        }

def build_test_app():
    app = create_app(Settings(database_url=""))
    app.router.lifespan_context = None
    app.dependency_overrides[require_current_user] = lambda: AuthUser(
        id=1,
        email="test@example.com",
        full_name="Test User",
        role="user",
        status="active",
        created_at=datetime.now(timezone.utc),
    )

    graph = DummyRootGraph()
    app.dependency_overrides[get_graph] = lambda: graph
    chat_repo = InMemoryTripChatRepository()
    app.state.trip_chat_repository = chat_repo

    memory_repo = InMemoryMemoryRepository()
    memory_service = build_conversation_memory_service(memory_repo)
    app.state.conversation_memory_service = memory_service

    return app, TestClient(app), memory_service


import unittest


class TestTripChatMemoryAPI(unittest.TestCase):
    def test_deletes_manual_plan_item_through_http_endpoint(self):
        app, client, _memory_service = build_test_app()
        created = client.post("/v1/trip-chats", json={"title": "Delete item"}).json()
        seeded = asyncio.run(
            app.state.trip_chat_repository.append_exchange(
                1,
                created["id"],
                "Tạo lịch",
                {"content": "Đã tạo"},
                None,
                {
                    "destination": "Hà Nội",
                    "days": [{
                        "day": 1,
                        "stops": [
                            {"itemId": "planner:1:a", "placeId": "a", "name": "A"},
                            {"itemId": "planner:1:b", "placeId": "b", "name": "B"},
                            {"itemId": "planner:1:c", "placeId": "c", "name": "C"},
                        ],
                        "legs": [
                            {"fromPlaceId": "a", "toPlaceId": "b"},
                            {"fromPlaceId": "b", "toPlaceId": "c"},
                        ],
                    }],
                },
            )
        )
        self.assertIsNotNone(seeded)

        response = client.request(
            "DELETE",
            f"/v1/trip-chats/{created['id']}/plan/days/1/items/planner%3A1%3Ab",
            data={"expectedRevision": seeded.revision},
        )

        self.assertEqual(response.status_code, 200)
        day = response.json()["currentPlannerOutput"]["days"][0]
        self.assertEqual(
            [stop["itemId"] for stop in day["stops"]],
            ["planner:1:a", "planner:1:c"],
        )
        self.assertEqual(day["legs"], [])

    def test_updates_manual_plan_item_through_http_endpoint(self):
        app, client, _memory_service = build_test_app()
        created = client.post("/v1/trip-chats", json={"title": "Update item"}).json()
        seeded = asyncio.run(
            app.state.trip_chat_repository.append_exchange(
                1,
                created["id"],
                "Tạo lịch",
                {"content": "Đã tạo"},
                None,
                {
                    "destination": "Hà Nội",
                    "days": [{
                        "day": 1,
                        "stops": [{
                            "itemId": "planner:1:a",
                            "placeId": "a",
                            "name": "A",
                            "coordinates": {"latitude": 21.01, "longitude": 105.81},
                        }],
                        "legs": [],
                    }],
                },
            )
        )
        self.assertIsNotNone(seeded)

        response = client.patch(
            f"/v1/trip-chats/{created['id']}/plan/days/1/items/planner%3A1%3Aa",
            data={
                "expectedRevision": seeded.revision,
                "placeId": "a-new",
                "name": "A mới",
                "latitude": 21.11,
                "longitude": 105.91,
            },
        )

        self.assertEqual(response.status_code, 200)
        stop = response.json()["currentPlannerOutput"]["days"][0]["stops"][0]
        self.assertEqual(stop["placeId"], "a-new")
        self.assertEqual(stop["name"], "A mới")
        self.assertEqual(
            stop["coordinates"],
            {"latitude": 21.11, "longitude": 105.91},
        )

    def test_updates_personal_note_without_changing_source_note(self):
        app, client, _memory_service = build_test_app()
        created = client.post("/v1/trip-chats", json={"title": "Notes"}).json()
        source_note = {
            "text": "Đến trước 8 giờ",
            "sourceType": "url",
            "sourceUrl": "https://example.test/video",
        }
        seeded = asyncio.run(
            app.state.trip_chat_repository.append_exchange(
                1,
                created["id"],
                "Tạo lịch",
                {"content": "Đã tạo"},
                None,
                {
                    "destination": "Hà Nội",
                    "days": [{
                        "day": 1,
                        "stops": [{
                            "itemId": "planner:1:lake",
                            "placeId": "lake",
                            "notes": source_note,
                            "personalNotes": None,
                        }],
                    }],
                },
            )
        )
        self.assertIsNotNone(seeded)

        response = client.patch(
            f"/v1/trip-chats/{created['id']}/plan/days/1/items/planner%3A1%3Alake/personal-notes",
            json={
                "expectedRevision": seeded.revision,
                "personalNotes": "Nhớ mang ô",
            },
        )

        self.assertEqual(response.status_code, 200)
        stop = response.json()["currentPlannerOutput"]["days"][0]["stops"][0]
        self.assertEqual(stop["notes"], source_note)
        self.assertEqual(stop["personalNotes"], "Nhớ mang ô")

    def test_bootstrap_returns_recent_chats_and_requested_active_chat(self):
        _app, client, _memory_service = build_test_app()
        first = client.post("/v1/trip-chats", json={"title": "First"}).json()
        second = client.post("/v1/trip-chats", json={"title": "Second"}).json()

        response = client.get(
            "/v1/trip-chats/bootstrap",
            params={"chatId": first["id"], "limit": 1},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["chats"]), 1)
        self.assertEqual(payload["chats"][0]["id"], second["id"])
        self.assertEqual(payload["activeChat"]["id"], first["id"])

    def test_create_and_send_trip_chat_message_with_memory(self):
        _app, client, memory_service = build_test_app()

        # 1. Create chat
        create_res = client.post("/v1/trip-chats", json={"title": "Hanoi Trip"})
        self.assertEqual(create_res.status_code, 201)
        chat_data = create_res.json()
        chat_id = chat_data["id"]

        # 2. Send message 1: "Đi du lịch Hà Nội 3 ngày."
        msg1_res = client.post(
            f"/v1/trip-chats/{chat_id}/messages",
            json={"content": "Đi du lịch Hà Nội 3 ngày."},
        )
        self.assertEqual(msg1_res.status_code, 200)
        res1_data = msg1_res.json()
        self.assertEqual(res1_data["chat"]["id"], chat_id)
        self.assertEqual(res1_data["assistantMessage"]["route"], "explorer")

        # 3. Send message 2: "Lên plan cho tôi."
        msg2_res = client.post(
            f"/v1/trip-chats/{chat_id}/messages",
            json={"content": "Lên plan cho tôi."},
        )
        self.assertEqual(msg2_res.status_code, 200)
        res2_data = msg2_res.json()
        self.assertEqual(res2_data["assistantMessage"]["route"], "explorer")

    def test_agent_invoke_backward_compatibility(self):
        _app, client, _memory_service = build_test_app()

        # Legacy /v1/agent/invoke without chat_id / conversation_memory
        invoke_res = client.post(
            "/v1/agent/invoke",
            json={"threadId": "legacy-thread-1", "message": "Xin chào"},
        )
        self.assertEqual(invoke_res.status_code, 200)
        data = invoke_res.json()
        self.assertIn("requestId", data)
        self.assertIn("route", data)
        self.assertIn("response", data)


if __name__ == "__main__":
    unittest.main()
