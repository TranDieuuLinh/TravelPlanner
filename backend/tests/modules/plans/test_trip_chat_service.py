from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_model import TripChat, TripChatPlanRevision
from app.modules.plans.chat_service import TripChatService
from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    PlaceCandidateReview,
)
from app.modules.plans.schema import MainPlanFromExplorerCreate
from app.modules.plans.timing import PlanTimingReport
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
            "timingReport": {
                "intakeId": f"intake-{destination}",
                "status": "completed",
                "totalSeconds": 0.75,
                "stages": [],
                "sources": [],
                "urlCount": 0,
                "imageCount": 0,
                "candidateCount": 0,
                "resolvedCount": 0,
                "persistedCount": 0,
                "providerCounts": {},
                "resolvedProviderCounts": {},
            },
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
                            "source": "selected_place",
                            "sourceRefs": ["https://example.com/old-cafe"],
                            "sourceOrder": 1,
                            "sourceDay": 1,
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
        self.explore_kwargs: list[dict] = []
        self.plan_payloads: list[MainPlanFromExplorerCreate] = []
        self.candidate_reviews: list[PlaceCandidateReview] = []
        self._count = 0

    async def explore_from_intake(self, **kwargs) -> ExploreIntakeResponse:
        self.raw_requests.append(kwargs["raw_request"])
        self.explore_kwargs.append(kwargs)
        destination = (
            "Hà Nội"
            if kwargs["destination"] == "unspecified"
            else kwargs["destination"]
        )
        result = _explore(destination)
        result.explorer.candidate_reviews = list(self.candidate_reviews)
        return result

    async def retry_candidate_reviews(
        self,
        reviews: list[PlaceCandidateReview],
        *,
        destination: str,
    ) -> list[PlaceCandidateReview]:
        return [
            review.model_copy(
                update={
                    "status": "resolved",
                    "resolution_reason": None,
                    "provider": "fake_places",
                    "resolved_name": f"Verified {review.name}",
                    "address": destination,
                    "latitude": 21.0285,
                    "longitude": 105.8542,
                    "retryable": False,
                }
            )
            if review.status == "needs_review"
            else review
            for review in reviews
        ]

    async def create_main_plan_from_explorer_with_timing(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> tuple[Plan, PlanTimingReport]:
        self.plan_payloads.append(payload)
        self._count += 1
        plan = _plan(payload.intent.destination, plan_id=f"generated-{self._count}")
        self.repository.save(plan)
        return plan, PlanTimingReport(
            status="completed",
            totalSeconds=1.25,
            stages=[],
            dayCount=len(plan.days),
            itemCount=sum(len(day.items) for day in plan.days),
            transportLegCount=0,
            unscheduledCount=0,
            warningCount=0,
        )


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
    assert first.latest_planner_timing is not None
    assert first.latest_planner_timing.total_seconds == 1.25
    reloaded = service.get(chat.id, user)
    assert reloaded.latest_explorer_timing is not None
    assert reloaded.latest_explorer_timing.total_seconds == 0.75
    assert reloaded.latest_planner_timing is not None
    assert reloaded.latest_planner_timing.total_seconds == 1.25
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
    assert fake_plans.plan_payloads[1].selected_places[0].source_day == 1
    revisions = list(
        db_session.scalars(
            select(TripChatPlanRevision).order_by(
                TripChatPlanRevision.revision
            )
        )
    )
    assert [item.intake_id for item in revisions] == [
        "intake-Hà Nội",
        "intake-Hà Nội",
    ]


def test_chat_more_days_amendment_allows_duration_expansion(
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
    asyncio.run(
        service.amend(
            chat.id,
            user,
            content="Adjust this plan with more days using this URL",
            expected_revision=first.revision,
            initial_destination="ignored",
            urls=["https://example.com/new-reel"],
            images=[],
        )
    )

    assert fake_plans.explore_kwargs[1]["trip_spec"].days is None
    assert (
        fake_plans.plan_payloads[1].expand_days_to_fit_selected_places
        is True
    )


def test_chat_does_not_promote_finder_suggestions_to_selected_places(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    service = TripChatService(
        TripChatRepository(db_session),
        _FakePlanService(),  # type: ignore[arg-type]
    )
    plan = _plan("Hà Nội", plan_id="plan-1")
    plan.days[0].items[0].source = "finder_suggestion"

    assert service._selected_places_from(plan) == []


def test_chat_carries_resolved_url_places_missing_from_previous_plan(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    service = TripChatService(
        TripChatRepository(db_session),
        _FakePlanService(),  # type: ignore[arg-type]
    )
    plan = _plan("Hà Nội", plan_id="plan-1")
    plan.days[0].items[0].source = "finder_suggestion"
    source_url = "https://example.com/source-video"
    reviews = [
        PlaceCandidateReview(
            candidateId="url-place",
            name="URL Place",
            category="attraction",
            status="resolved",
            provider="google_maps_scraper",
            resolvedName="URL Place",
            address="Hà Nội",
            latitude=21.03,
            longitude=105.84,
            sourceUrls=[source_url],
            confidence=0.9,
            retryable=False,
        )
    ]

    selected = service._selected_places_from(plan, reviews)

    assert len(selected) == 1
    assert selected[0].name == "URL Place"
    assert selected[0].source_refs == [source_url]


def test_sequential_url_imports_preserve_all_candidate_sources(
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
    tiktok_url = "https://www.tiktok.com/@creator/video/123"
    youtube_url = "https://www.youtube.com/watch?v=abc123"

    fake_plans.candidate_reviews = [
        PlaceCandidateReview(
            candidateId="tiktok-hoan-kiem",
            name="Hồ Hoàn Kiếm",
            category="attraction",
            status="resolved",
            provider="google_maps_scraper",
            resolvedName="Hồ Hoàn Kiếm",
            address="Hanoi",
            latitude=21.0287,
            longitude=105.8522,
            sourceUrls=[tiktok_url],
            sourceOrder=1,
            confidence=0.9,
            retryable=False,
        )
    ]
    first = asyncio.run(
        service.amend(
            chat.id,
            user,
            content=f"Thêm video TikTok {tiktok_url}",
            expected_revision=0,
            initial_destination="Hà Nội",
            urls=[tiktok_url],
            images=[],
        )
    )

    fake_plans.candidate_reviews = [
        PlaceCandidateReview(
            candidateId="youtube-hoan-kiem",
            name="Hoan Kiem Lake",
            category="attraction",
            status="resolved",
            provider="google_maps_scraper",
            resolvedName="Hồ Hoàn Kiếm",
            address="Hanoi",
            latitude=21.0287,
            longitude=105.8522,
            sourceUrls=[youtube_url],
            sourceOrder=1,
            confidence=0.95,
            retryable=False,
        ),
        PlaceCandidateReview(
            candidateId="youtube-temple",
            name="Đền Ngọc Sơn",
            category="attraction",
            status="resolved",
            provider="google_maps_scraper",
            resolvedName="Đền Ngọc Sơn",
            address="Hà Nội",
            latitude=21.0307,
            longitude=105.8524,
            sourceUrls=[youtube_url],
            sourceOrder=2,
            confidence=0.9,
            retryable=False,
        ),
    ]
    second = asyncio.run(
        service.amend(
            chat.id,
            user,
            content=f"Thêm video YouTube {youtube_url}",
            expected_revision=first.revision,
            initial_destination="Hà Nội",
            urls=[youtube_url],
            images=[],
        )
    )

    assert second.current_explorer is not None
    reviews = second.current_explorer.candidate_reviews
    assert len(reviews) == 2
    assert reviews[0].candidate_id == "tiktok-hoan-kiem"
    assert reviews[0].source_urls == [tiktok_url, youtube_url]
    assert reviews[1].source_urls == [youtube_url]
    second_selected = fake_plans.plan_payloads[1].selected_places
    assert any(
        place.name == "Hồ Hoàn Kiếm"
        and place.source_refs == [tiktok_url]
        for place in second_selected
    )


def test_chat_read_recovers_candidate_sources_from_revision_history(
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
    tiktok_url = "https://www.tiktok.com/@creator/video/123"
    youtube_url = "https://www.youtube.com/watch?v=abc123"
    tiktok_review = PlaceCandidateReview(
        candidateId="tiktok-hoan-kiem",
        name="Hồ Hoàn Kiếm",
        category="attraction",
        status="resolved",
        provider="google_maps_scraper",
        resolvedName="Hồ Hoàn Kiếm",
        address="Hanoi",
        latitude=21.0287,
        longitude=105.8522,
        sourceUrls=[tiktok_url],
        confidence=0.9,
        retryable=False,
    )
    fake_plans.candidate_reviews = [tiktok_review]
    saved = asyncio.run(
        service.amend(
            chat.id,
            user,
            content=f"Thêm video TikTok {tiktok_url}",
            expected_revision=0,
            initial_destination="Hà Nội",
            urls=[tiktok_url],
            images=[],
        )
    )
    assert saved.current_explorer is not None

    stored = db_session.get(TripChat, chat.id)
    assert stored is not None
    overwritten = saved.current_explorer.model_copy(deep=True)
    overwritten.candidate_reviews = [
        tiktok_review.model_copy(
            update={
                "candidate_id": "youtube-hoan-kiem",
                "source_urls": [youtube_url],
            }
        )
    ]
    stored.current_explorer = overwritten.model_dump(mode="json", by_alias=True)
    db_session.commit()

    recovered = service.get(chat.id, user)

    assert recovered.current_explorer is not None
    assert recovered.current_explorer.candidate_reviews[0].source_urls == [
        tiktok_url,
        youtube_url,
    ]


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


def test_chat_retries_only_unresolved_candidates_and_updates_plan(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    fake_plans = _FakePlanService()
    fake_plans.candidate_reviews = [
        PlaceCandidateReview(
            candidateId="candidate-train-street",
            name="Train Street",
            category="attraction",
            status="needs_review",
            resolutionReason="provider_error",
            searchRegion="Hà Nội",
            sourceUrls=["https://example.com/reel"],
            sourceOrder=2,
            confidence=0.8,
        )
    ]
    service = TripChatService(
        TripChatRepository(db_session),
        fake_plans,  # type: ignore[arg-type]
    )
    chat = service.create(user)
    first = asyncio.run(
        service.amend(
            chat.id,
            user,
            content="Tạo chuyến Hà Nội từ URL",
            expected_revision=0,
            initial_destination="Hà Nội",
            urls=["https://example.com/reel"],
            images=[],
        )
    )

    retried = asyncio.run(
        service.retry_candidate_resolutions(
            chat.id,
            user,
            expected_revision=first.revision,
        )
    )

    assert retried.revision == 2
    assert retried.current_intake_id == "intake-Hà Nội"
    assert retried.current_explorer is not None
    assert retried.current_explorer.candidate_reviews[0].status == "resolved"
    assert fake_plans.plan_payloads[-1].selected_places[-1].name == (
        "Verified Train Street"
    )
