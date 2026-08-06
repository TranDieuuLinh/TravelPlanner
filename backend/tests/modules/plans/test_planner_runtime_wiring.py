from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty
from app.modules.knowledge_graph.place_repository import (
    KnowledgeGraphPlaceRepository,
)
from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector import PlaceSelectorService
from app.modules.plans.trip_theme_planner import TripThemePlannerService
from app.modules.plans.trip_theme_planner.graph_research import (
    TripThemeGraphResearchService,
)
from app.modules.plans.schema import MainPlanCreate
from tests.modules.plans.test_planner_service import FakePlannerLLM


def test_knowledge_graph_place_repository_imports_without_statistics_cycle() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.modules.knowledge_graph.place_repository import "
                "KnowledgeGraphPlaceRepository; print(KnowledgeGraphPlaceRepository.__name__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "KnowledgeGraphPlaceRepository"


def test_planner_runtime_uses_knowledge_graph_place_repository() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            service = get_plan_service(session)

            place_tool = service.main_workflow.place_selector.place_tool
            assert isinstance(place_tool, RepositoryPlaceSelectionTool)
            assert isinstance(
                place_tool.repository,
                KnowledgeGraphPlaceRepository,
            )
            assert isinstance(
                service.main_workflow.trip_theme_planner.graph_research_service,
                TripThemeGraphResearchService,
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_runtime_finder_uses_place_repository_and_fills_catalog_places(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.plans.dependencies.get_llm_client",
        lambda: FakePlannerLLM(),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    KnowledgeEntity(
                        id="area-hanoi",
                        canonical_name="Hà Nội",
                        normalized_name="ha noi",
                        entity_type="Area",
                        status="verified",
                    ),
                    _place(
                        "place-museum",
                        "City Museum",
                        "museum",
                        ["culture"],
                    ),
                    _place(
                        "place-gallery",
                        "City Art Gallery",
                        "art_gallery",
                        ["culture", "art"],
                    ),
                    _place(
                        "place-restaurant",
                        "Local Restaurant",
                        "restaurant",
                        ["food"],
                    ),
                    _place(
                        "place-dinner",
                        "Local Dinner Restaurant",
                        "restaurant",
                        ["food", "dinner"],
                    ),
                    _place(
                        "place-coffee",
                        "Old Quarter Coffee",
                        "cafe",
                        ["coffee"],
                    ),
                    _place(
                        "place-bakery",
                        "Morning Bakery",
                        "bakery",
                        ["food", "breakfast"],
                    ),
                ]
            )
            session.commit()

            service = get_plan_service(session)
            assert isinstance(
                service.main_workflow.place_selector.place_tool,
                RepositoryPlaceSelectionTool,
            )
            assert isinstance(
                service.main_workflow.trip_theme_planner.graph_research_service,
                TripThemeGraphResearchService,
            )
            assert not hasattr(
                service.main_workflow.trip_theme_planner,
                "research_tool",
            )
            assert isinstance(
                service.main_workflow.place_selector.route_optimizer,
                RouteFirstItineraryOptimizer,
            )
            assert isinstance(
                service.main_workflow.place_selector,
                PlaceSelectorService,
            )
            assert isinstance(
                service.main_workflow.trip_theme_planner,
                TripThemePlannerService,
            )

            plan = asyncio.run(
                service.create_main_plan(
                    MainPlanCreate(
                        destination="Hà Nội",
                        days=1,
                        regionKey="vn,ha-noi",
                        interests=["culture", "food", "coffee"],
                        selectedPlaces=[],
                    )
                )
            )

            committed_items = [
                item
                for day in plan.days
                for item in day.items
                if item.place_id
            ]
            assert len(committed_items) == 5
            assert [item.role for item in committed_items] == [
                "breakfast_meal",
                "main_activity_1",
                "lunch_meal",
                "main_activity_2",
                "dinner_meal",
            ]
            assert all(
                item.source == "finder_suggestion"
                for item in committed_items
            )
            assert plan.status.value == "draft"
            assert plan.check_report is not None
            assert plan.check_report.status == "needs_backup"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_context_endpoint_builds_plan_from_normalized_input(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.plans.dependencies.get_llm_client",
        lambda: FakePlannerLLM(),
    )
    db_session.add_all(
        [
            KnowledgeEntity(
                id="area-hanoi-context",
                canonical_name="Hà Nội",
                normalized_name="ha noi",
                entity_type="Area",
                status="verified",
            ),
            _place("context-museum", "Context Museum", "museum", ["culture"]),
            _place("context-gallery", "Context Gallery", "art_gallery", ["culture"]),
            _place("context-food", "Context Food", "restaurant", ["food"]),
            _place(
                "context-dinner",
                "Context Dinner",
                "restaurant",
                ["food", "dinner"],
            ),
            _place("context-cafe", "Context Cafe", "cafe", ["coffee"]),
            _place("context-bakery", "Context Bakery", "bakery", ["breakfast"]),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/plans/main/from-context",
        json={
            "intent": {
                "destination": "Hà Nội",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture", "food", "coffee"],
            },
            "tripSpec": {
                "days": 1,
                "partySize": 2,
                "budget": {"targetAmount": None, "level": "medium"},
            },
            "regionKey": "vn,ha-noi",
            "selectedPlaces": [],
            "userStatus": {},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intent"]["days"] == 1
    assert len(
        [
            item
            for item in body["days"][0]["items"]
            if item["placeId"] is not None
        ]
    ) == 5
    assert [item["role"] for item in body["days"][0]["items"]] == [
        "breakfast_meal",
        "main_activity_1",
        "lunch_meal",
        "main_activity_2",
        "dinner_meal",
    ]
    assert body["status"] == "draft"
    assert body["checkReport"]["status"] == "needs_backup"


def test_from_explorer_provider_error_keeps_cors_headers(
    client: TestClient,
) -> None:
    class FailingPlanService:
        async def create_main_plan_from_explorer_with_timing(self, payload):
            raise RuntimeError("Planner provider failed.")

    app.dependency_overrides[get_plan_service] = lambda: FailingPlanService()
    response = client.post(
        "/api/plans/main/from-explorer",
        headers={"Origin": "http://localhost:3000"},
        json={
            "tripIntent": {
                "destination": "Ha Noi",
                "timing": {"days": 1},
                "travelParty": {"type": "solo", "adults": 1},
                "budget": {"targetAmount": None, "level": "medium"},
                "preferences": {
                    "travelStyle": "local",
                    "pace": "balanced",
                    "interests": ["culture"],
                },
            },
            "selectedPlaces": [],
        },
    )

    assert response.status_code == 502
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
    assert response.json()["detail"] == "Planner provider failed."


def test_from_explorer_rejects_removed_split_intent_contract(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/plans/main/from-explorer",
        json={
            "intent": {"destination": "Hà Nội"},
            "tripSpec": {"days": 2},
            "selectedPlaces": [],
        },
    )

    assert response.status_code == 422


def _place(
    place_id: str,
    name: str,
    place_type: str,
    tags: list[str],
) -> KnowledgeEntity:
    entity = KnowledgeEntity(
        id=place_id,
        canonical_name=name,
        normalized_name=name.casefold(),
        entity_type="Restaurant" if place_type in {"restaurant", "bakery", "cafe"} else "TravelPlace",
        status="verified",
    )
    values = {
        "place_type": place_type,
        "region_key": "vn,ha-noi",
        "catalog_status": "active",
        "typical_duration_minutes": "60",
        "data_confidence": "high",
        "opening_hours": '[{"openTime":"08:00","closeTime":"22:00","is24Hours":false}]',
        "metadata": json.dumps(
            {"tags": tags, "activityIntensity": "light"}
        ),
    }
    entity.properties = [
        KnowledgeProperty(key=key, value=value)
        for key, value in values.items()
    ]
    return entity
