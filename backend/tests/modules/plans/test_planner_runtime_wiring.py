from __future__ import annotations

import asyncio
import subprocess
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.places.model import Place
from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool
from app.modules.plans.schema import MainPlanCreate
from tests.modules.plans.test_planner_service import FakePlannerLLM


def test_place_repository_imports_without_statistics_cycle() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.modules.places.repository import "
                "SqlAlchemyPlaceRepository; print(SqlAlchemyPlaceRepository.__name__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SqlAlchemyPlaceRepository"


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
                    _place(
                        "place-museum",
                        "City Museum",
                        "museum",
                        ["culture"],
                    ),
                    _place(
                        "place-restaurant",
                        "Local Restaurant",
                        "restaurant",
                        ["food"],
                    ),
                    _place(
                        "place-coffee",
                        "Old Quarter Coffee",
                        "cafe",
                        ["coffee"],
                    ),
                ]
            )
            session.commit()

            service = get_plan_service(session)
            assert isinstance(
                service.main_workflow.finder.place_tool,
                RepositoryFinderPlaceTool,
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
            assert len(committed_items) == 3
            assert all(
                item.source == "finder_suggestion"
                for item in committed_items
            )
            assert plan.status.value == "locked"
            assert plan.check_report is not None
            assert plan.check_report.status == "passed"
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
            _place("context-museum", "Context Museum", "museum", ["culture"]),
            _place("context-food", "Context Food", "restaurant", ["food"]),
            _place("context-cafe", "Context Cafe", "cafe", ["coffee"]),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/plans/main/from-context",
        json={
            "intent": {
                "destination": "Hà Nội",
                "budgetLevel": "medium",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture", "food", "coffee"],
            },
            "tripSpec": {
                "days": 1,
                "partySize": 2,
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
    ) == 3
    assert body["status"] == "locked"
    assert body["checkReport"]["status"] == "passed"


def _place(
    place_id: str,
    name: str,
    place_type: str,
    tags: list[str],
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key="vn,ha-noi",
        status="active",
        typical_duration_minutes=60,
        data_confidence="high",
        opening_hours=[
            {
                "openTime": "08:00",
                "closeTime": "22:00",
                "is24Hours": False,
            }
        ],
        metadata_json={
            "tags": tags,
            "activityIntensity": "light",
        },
    )
