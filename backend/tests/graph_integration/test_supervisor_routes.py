import asyncio
from uuid import uuid4

from app.modules.supervisor.contract import ClassifierResult
from app.modules.supervisor.service import SupervisorService
from app.orchestration.root_graph import create_root_graph
from app.modules.plan_editor.public import EditOperation
from app.shared.contracts.itinerary import Itinerary, ItineraryDay, ItineraryItem
from app.shared.contracts.place import Coordinates, VerifiedPlace
from app.shared.contracts.trip import TripIntent


def invoke(graph, payload):
    return asyncio.run(
        graph.ainvoke(payload, config={"configurable": {"thread_id": str(uuid4())}})
    )


class CapturingClassifier:
    def __init__(self):
        self.payload = None

    async def classify(self, payload):
        self.payload = payload
        return ClassifierResult(
            route="finish",
            confidence=1.0,
            reason="Context test",
            response="Đã hiểu.",
        )


class StaticClassifier:
    def __init__(self, result: ClassifierResult):
        self.result = result

    async def classify(self, payload):
        return self.result


def test_supervisor_context_keeps_six_previous_role_tagged_messages():
    classifier = CapturingClassifier()
    context = [
        f"{'User' if index % 2 == 0 else 'Assistant'}: Tin nhắn {index}"
        for index in range(8)
    ]

    invoke(
        create_root_graph(
            supervisor_service=SupervisorService(classifier=classifier),
        ),
        {
            "request_id": "context-1",
            "message": "Thế còn Nha Trang?",
            "recent_messages": context,
        },
    )

    assert classifier.payload.message == "Thế còn Nha Trang?"
    assert classifier.payload.conversation_context == context[-6:]
    assert "User: Thế còn Nha Trang?" not in classifier.payload.conversation_context


def test_information_finder_route_completes_with_response():
    result = invoke(
        create_root_graph(supervisor_service=SupervisorService(
            classifier=StaticClassifier(ClassifierResult(
                route="information_finder",
                confidence=1.0,
                reason="Structured information request.",
            ))
        )),
        {"request_id": "info-1", "message": "Giá vé và giờ mở cửa bảo tàng?"},
    )
    assert result["decision"].route == "information_finder"
    assert result["response"]


def test_finish_route_completes_with_meaningful_response():
    result = invoke(
        create_root_graph(supervisor_service=SupervisorService(
            classifier=StaticClassifier(ClassifierResult(
                route="finish",
                confidence=1.0,
                reason="Structured greeting.",
                response="Xin chào, mình có thể hỗ trợ bạn về du lịch.",
            ))
        )),
        {"request_id": "finish-1", "message": "Xin chào"},
    )
    assert result["decision"].route == "finish"
    assert "du lịch" in result["response"].casefold()


def test_plan_editor_route_requires_and_uses_structured_state():
    itinerary = Itinerary(
        itinerary_id="itinerary-1",
        intent=TripIntent(destination="Da Nang", days=1),
        days=[
            ItineraryDay(
                day=1,
                items=[
                    ItineraryItem(
                        item_id="item-1",
                        place=VerifiedPlace(
                            place_id="place-1",
                            name="Museum",
                            coordinates=Coordinates(latitude=16.07, longitude=108.22),
                            source="test",
                        ),
                        start_minute=540,
                        end_minute=660,
                    )
                ],
            )
        ],
    )
    result = invoke(
        create_root_graph(),
        {
            "request_id": "edit-1",
            "message": "Cập nhật lịch trình",
            "existing_itinerary": itinerary,
            "edit_operation": EditOperation(type="lock_item", item_id="item-1"),
        },
    )
    assert result["decision"].route == "plan_editor"
    assert result["itinerary"].days[0].items[0].locked is True
