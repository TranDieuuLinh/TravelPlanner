from __future__ import annotations

import asyncio

import pytest

from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_service import TripChatService
from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.schema import ExploreIntakeResponse
from app.modules.plans.schema import MainPlanFromExplorerCreate
from app.modules.users.repository import UserRepository
from app.shared.errors import AppError


def _explore(destination: str, *, days: int = 2) -> ExploreIntakeResponse:
    return ExploreIntakeResponse.model_validate(
        {
            "intakeId": f"intake-{destination}",
            "userId": "1",
            "explorer": {
                "intent": {
                    "destination": destination,
                    "travelStyle": "local",
                    "pace": "balanced",
                    "interests": ["food"],
                    "mustVisitPlaces": [],
                    "avoidPlaces": [],
                    "constraints": [],
                    "clarifyingQuestions": [],
                },
                "tripSpec": {"days": days},
                "assumptions": [],
                "missingInfoQuestions": [],
                "preferenceSnapshot": {},
            },
            "allowFinderSuggestions": True,
        }
    )


def _plan(destination: str, *, plan_id: str) -> Plan:
    return Plan.model_validate(
        {
            "id": plan_id,
            "kind": "main",
            "status": "draft",
            "title": f"{destination} plan",
            "destination": destination,
            "intent": {
                "destination": destination,
                "days": 2,
                "budget": "medium",
                "travelStyle": "local",
                "pace": "balanced",
            },
            "macroPlan": {
                "title": f"{destination} plan",
                "destination": destination,
                "dayBriefs": [
                    {
                        "day": 1,
                        "theme": "Food",
                        "targetArea": destination,
                    },
                    {
                        "day": 2,
                        "theme": "Culture",
                        "targetArea": destination,
                    },
                ],
            },
            "days": [
                {
                    "day": 1,
                    "theme": "Food",
                    "items": [
                        {
                            "itemId": "item-1",
                            "placeId": "place-1",
                            "name": "Old Cafe",
                            "timeWindow": "09:00-10:00",
                            "placeType": "cafe",
                            "source": "finder",
                            "sourceRefs": [],
                        }
                    ],
                },
                {"day": 2, "theme": "Culture", "items": []},
            ],
        }
    )


class _MemoryPlanRepository:
    def __init__(self) -> None:
        self.plans: dict[str, Plan] = {}

    def save(self, plan: Plan) -> Plan:
        self.plans[plan.id] = plan
        return plan


class _FakePlanService:
    def __init__(self) -> None:
        self.repository = _MemoryPlanRepository()
        self.raw_requests: list[str] = []
        self.plan_payloads: list[MainPlanFromExplorerCreate] = []
        self._count = 0

    async def explore_from_intake(self, **kwargs) -> ExploreIntakeResponse:
        self.raw_requests.append(kwargs["raw_request"])
        destination = (
            "Hà Nội"
            if kwargs["destination"] == "unspecified"
            else kwargs["destination"]
        )
        return _explore(destination)

    async def create_main_plan_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        self.plan_payloads.append(payload)
        self._count += 1
        plan = _plan(payload.intent.destination, plan_id=f"generated-{self._count}")
        self.repository.save(plan)
        return plan


def test_chat_amendment_keeps_one_plan_identity_and_history(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    fake_plans = _FakePlanService()
    service = TripChatService(
        TripChatRepository(db_session),
        fake_plans,  # type: ignore[arg-type]
    )
    chat = service.create(user)

    first = asyncio.run(
        service.amend(
            chat.id,
            user,
            content="Tạo chuyến Hà Nội 2 ngày",
            expected_revision=0,
            initial_destination="Hà Nội",
            urls=[],
            images=[],
        )
    )
    second = asyncio.run(
        service.amend(
            chat.id,
            user,
            content="Thêm một quán cà phê vào ngày 2",
            expected_revision=1,
            initial_destination="ignored",
            urls=[],
            images=[],
        )
    )

    assert first.revision == 1
    assert second.revision == 2
    assert first.current_plan is not None
    assert second.current_plan is not None
    assert second.current_plan.id == first.current_plan.id
    assert [message.role for message in second.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "Tạo chuyến Hà Nội 2 ngày" in fake_plans.raw_requests[1]
    assert "Latest user amendment: Thêm một quán cà phê" in fake_plans.raw_requests[1]
    assert fake_plans.plan_payloads[1].selected_places[0].name == "Old Cafe"


def test_chat_amendment_rejects_stale_revision(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    service = TripChatService(
        TripChatRepository(db_session),
        _FakePlanService(),  # type: ignore[arg-type]
    )
    chat = service.create(user)

    with pytest.raises(AppError) as caught:
        asyncio.run(
            service.amend(
                chat.id,
                user,
                content="Sửa lịch trình",
                expected_revision=3,
                initial_destination="Hà Nội",
                urls=[],
                images=[],
            )
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "VERSION_CONFLICT"
