from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.places.model import Place
from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.domain.entities import Plan
from app.modules.plans.schema import BackupPlanCreate, PlanningContextCreate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic Planner/Finder output evaluations."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. The report is always printed.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_evaluation())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")


async def run_evaluation() -> dict[str, Any]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(_catalog_places())
            session.commit()
            service = get_plan_service(session)

            catalog_plan = await service.create_main_plan_from_context(
                _context(
                    days=1,
                    interests=["culture", "food", "coffee"],
                )
            )
            _assert_final_plan(catalog_plan)
            catalog_items = _activity_items(catalog_plan)
            assert len(catalog_items) == 3
            assert all(item.source == "finder_suggestion" for item in catalog_items)
            assert {item.name for item in catalog_items} == {
                "Accessible Museum",
                "Local Food",
                "Local Coffee",
            }

            constrained_plan = await service.create_main_plan_from_context(
                _context(
                    days=1,
                    interests=["culture"],
                    user_status={
                        "availableAt": "15:00",
                        "constraints": {
                            "maxConsecutiveActiveMinutes": 90,
                            "requiredRestMinutes": 120,
                            "maxWalkingMinutesPerDay": 30,
                            "accessibilityNeeds": ["wheelchair"],
                        },
                    },
                )
            )
            _assert_final_plan(constrained_plan)
            assert all(
                _window_start_minutes(item.time_window) >= 15 * 60
                for item in _activity_items(constrained_plan)
            )

            selection_plan = await service.create_main_plan_from_context(
                _context(
                    days=1,
                    interests=["local"],
                    avoid_places=["Avoid Me"],
                    selected_places=[
                        {
                            "name": "Manual Place",
                            "mustVisit": False,
                            "sourceRefs": ["source-manual"],
                            "tags": ["indoor", "local"],
                            "priority": 1,
                        },
                        {
                            "placeId": "avoid-me",
                            "name": "Avoid Me",
                            "mustVisit": True,
                            "priority": 1,
                        },
                        *[
                            {
                                "placeId": f"selected-{index}",
                                "name": f"Selected {index}",
                                "mustVisit": True,
                                "priority": index + 1,
                            }
                            for index in range(1, 3)
                        ],
                        {
                            "placeId": "overflow-optional",
                            "name": "Overflow Optional",
                            "mustVisit": False,
                            "priority": 5,
                        },
                    ],
                )
            )
            _assert_final_plan(selection_plan)
            manual_item = next(
                item
                for item in _activity_items(selection_plan)
                if item.name == "Manual Place"
            )
            assert manual_item.place_id is None
            assert manual_item.source_refs == ["source-manual"]
            assert all(
                item.name != "Avoid Me"
                for item in _activity_items(selection_plan)
            )
            unscheduled_codes = {
                place.name: place.reason_code
                for place in selection_plan.unscheduled_places
            }
            assert unscheduled_codes["Avoid Me"] == "avoided_by_user"
            assert "no_day_capacity" in unscheduled_codes.values()

            backup_source = await service.create_main_plan_from_context(
                _context(
                    days=1,
                    interests=["indoor"],
                    selected_places=[
                        {
                            "placeId": "optional-indoor",
                            "name": "Optional Indoor Place",
                            "mustVisit": False,
                            "sourceRefs": ["source-optional"],
                            "tags": ["indoor"],
                        }
                    ],
                )
            )
            backup_bundle = await service.create_backup_plan(
                backup_source.id,
                BackupPlanCreate(reason="evaluation"),
            )
            backup_plan = backup_bundle.backup_plan
            _assert_final_plan(backup_plan)
            preserved_backup_items = [
                item
                for item in _activity_items(backup_plan)
                if item.source == "selected_place"
            ]
            assert any(
                item.name == "Optional Indoor Place"
                for item in preserved_backup_items
            )

            return {
                "status": "passed",
                "scenarios": [
                    _summary("catalog_fill", catalog_plan),
                    _summary("user_constraints", constrained_plan),
                    _summary("selection_boundaries", selection_plan),
                    _summary("backup_preservation", backup_plan),
                ],
            }
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _context(
    *,
    days: int,
    interests: list[str],
    avoid_places: list[str] | None = None,
    selected_places: list[dict[str, Any]] | None = None,
    user_status: dict[str, Any] | None = None,
) -> PlanningContextCreate:
    return PlanningContextCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "budgetLevel": "medium",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": interests,
                "avoidPlaces": avoid_places or [],
            },
            "tripSpec": {
                "days": days,
                "partySize": 2,
            },
            "regionKey": "vn,ha-noi",
            "selectedPlaces": selected_places or [],
            "userStatus": user_status or {},
        }
    )


def _assert_final_plan(plan: Plan) -> None:
    assert len(plan.days) == plan.intent.days
    item_ids = [
        item.item_id
        for day in plan.days
        for item in day.items
        if item.item_id
    ]
    assert len(item_ids) == len(set(item_ids))

    place_ids = [
        item.place_id
        for item in _activity_items(plan)
        if item.place_id
    ]
    assert len(place_ids) == len(set(place_ids))

    for item in _activity_items(plan):
        if item.duration_minutes is None:
            continue
        assert item.duration_minutes <= _window_duration_minutes(
            item.time_window
        ), (
            f"{item.name} duration {item.duration_minutes} exceeds "
            f"{item.time_window}"
        )

    remaining = set(plan.final_plan_status.remaining_selected_place_ids)
    unscheduled_refs = {
        place.place_id or place.name
        for place in plan.unscheduled_places
    }
    assert remaining.issubset(unscheduled_refs)


def _activity_items(plan: Plan):
    return [
        item
        for day in plan.days
        for item in day.items
        if item.place_type != "break"
    ]


def _summary(name: str, plan: Plan) -> dict[str, Any]:
    return {
        "name": name,
        "planId": plan.id,
        "days": len(plan.days),
        "activityItems": [
            {
                "name": item.name,
                "placeId": item.place_id,
                "source": item.source,
                "timeWindow": item.time_window,
                "durationMinutes": item.duration_minutes,
            }
            for item in _activity_items(plan)
        ],
        "unscheduledPlaces": [
            {
                "name": place.name,
                "reasonCode": place.reason_code,
            }
            for place in plan.unscheduled_places
        ],
        "warnings": plan.warnings,
    }


def _window_duration_minutes(value: str) -> int:
    start, end = value.split("-", 1)
    return _clock_minutes(end) - _clock_minutes(start)


def _window_start_minutes(value: str) -> int:
    start, _ = value.split("-", 1)
    return _clock_minutes(start)


def _clock_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _catalog_places() -> list[Place]:
    return [
        _place(
            "catalog-museum",
            "Accessible Museum",
            "museum",
            ["culture"],
            accessibility=["wheelchair"],
        ),
        _place(
            "catalog-food",
            "Local Food",
            "restaurant",
            ["food"],
            accessibility=["wheelchair"],
        ),
        _place(
            "catalog-coffee",
            "Local Coffee",
            "cafe",
            ["coffee"],
            accessibility=["wheelchair"],
        ),
        _place(
            "catalog-beach",
            "Coastal Walk",
            "beach",
            ["outdoor", "beach"],
        ),
        _place(
            "catalog-long",
            "All-day Experience",
            "attraction",
            ["culture"],
            duration=240,
            accessibility=["wheelchair"],
        ),
    ]


def _place(
    place_id: str,
    name: str,
    place_type: str,
    tags: list[str],
    *,
    duration: int = 60,
    accessibility: list[str] | None = None,
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key="vn,ha-noi",
        status="active",
        typical_duration_minutes=duration,
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
            "accessibilityFeatures": accessibility or [],
        },
    )


if __name__ == "__main__":
    main()
