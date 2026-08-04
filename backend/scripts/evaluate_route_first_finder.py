from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
    TravelIntent,
    TripThemeRequirement,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool
from app.modules.plans.finder.candidate_selector import CandidateSelector
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector import PlaceSelectorService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


def _intent(days: int, interests: list[str]) -> TravelIntent:
    return TravelIntent(
        destination="Hanoi",
        days=days,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=interests,
    )


def _macro(themes: list[tuple[str, list[str]]], allocated: list[list[str]]) -> MacroPlan:
    all_tags = list(dict.fromkeys(tag for _, tags in themes for tag in tags))
    return MacroPlan(
        title="Hanoi route-first evaluation",
        destination="Hanoi",
        regionKey="vn,ha-noi",
        tripThemes=[
            TripThemeRequirement(
                theme=theme,
                focusTags=tags,
                minimumActivities=1,
            )
            for theme, tags in themes
        ],
        dayBriefs=[
            DayBrief(
                day=index,
                theme="Tối ưu theo tuyến",
                targetArea="Hanoi",
                targetRegionKey="vn,ha-noi",
                focusTags=all_tags,
                allocatedSelectedPlaceRefs=allocated[index - 1],
            )
            for index in range(1, len(themes) + 1)
        ],
    )


def main() -> None:
    cases = [
        {
            "name": "catalog_only_two_days",
            "themes": [("Local culture", ["culture"]), ("Food and lakes", ["food", "nature"])],
            "selected": [],
        },
        {
            "name": "one_url_place_without_source_order",
            "themes": [("Old quarter", ["culture"]), ("Heritage", ["history", "culture"])],
            "selected": [
                SelectedPlaceContext(
                    name="Confirmed URL stop",
                    regionKey="vn,ha-noi",
                    latitude=21.0285,
                    longitude=105.8542,
                    tags=["culture"],
                    sourceRefs=["https://example.com/travel-video"],
                )
            ],
        },
        {
            "name": "ordered_url_itinerary_is_supplemented",
            "themes": [("Reference itinerary", ["culture", "food"]), ("Open exploration", ["nature"])],
            "selected": [
                SelectedPlaceContext(
                    name="Ordered URL stop",
                    regionKey="vn,ha-noi",
                    latitude=21.0285,
                    longitude=105.8542,
                    tags=["culture"],
                    sourceRefs=["https://example.com/ordered-video"],
                    sourceOrder=1,
                    sourceDay=1,
                )
            ],
        },
        {
            "name": "narrow_themes_use_global_interests",
            "themes": [("Unmapped poetic theme alpha", []), ("Unmapped poetic theme beta", [])],
            "selected": [],
        },
        {
            "name": "three_day_route_first",
            "themes": [("Culture", ["culture"]), ("Nature", ["nature"]), ("Local food", ["food"])],
            "selected": [],
        },
    ]

    session = SessionLocal()
    try:
        place_tool = RepositoryFinderPlaceTool(SqlAlchemyPlaceRepository(session))
        finder = PlaceSelectorService(
            place_tool,
            route_optimizer=RouteFirstItineraryOptimizer(
                GeographicRouteOptimizer()
            ),
        )
        report = []
        for case in cases:
            selected = case["selected"]
            selected_refs = {place.stable_ref for place in selected}
            allocated = [[], *([] for _ in range(len(case["themes"]) - 1))]
            if selected:
                allocated[0] = [place.stable_ref for place in selected]
            result = finder.fill_main_plan(
                _macro(case["themes"], allocated),
                _intent(len(case["themes"]), ["culture", "food", "nature"]),
                selected,
                allow_finder_suggestions=True,
            )
            day_reports = []
            scheduled_selected_refs = set()
            all_place_ids = []
            for day in result.days:
                real_items = [
                    item
                    for item in day.items
                    if item.place_id is not None or item.source == "selected_place"
                ]
                meal_placeholders = [
                    item.name
                    for item in day.items
                    if item.place_type == "meal" and item.source == "finder_rule"
                ]
                social_placeholders = [
                    item.name
                    for item in day.items
                    if item.role == "group_social_activity"
                ]
                route_distance_km = round(
                    sum(leg.distance_meters for leg in day.transport_legs) / 1000,
                    1,
                )
                max_leg_km = round(
                    max(
                        (leg.distance_meters for leg in day.transport_legs),
                        default=0,
                    )
                    / 1000,
                    1,
                )
                assert len(real_items) >= 3, (
                    case["name"],
                    day.day,
                    [item.name for item in day.items],
                    result.warnings,
                )
                expected_roles = [
                    "breakfast_meal",
                    "main_activity_1",
                    "lunch_meal",
                    "main_activity_2",
                    "dinner_meal",
                ]
                assert len(real_items) == 5, (
                    case["name"], day.day, [item.name for item in real_items]
                )
                assert day.theme != "Tối ưu theo tuyến", (
                    case["name"], day.day, day.theme
                )
                assert [item.role for item in real_items] == expected_roles, (
                    case["name"], day.day, [item.role for item in real_items]
                )
                assert sum(
                    item.timeline_category == "activity" for item in real_items
                ) == 2, (case["name"], day.day)
                assert not any(
                    CandidateSelector._has_strong_food_name(
                        type("Candidate", (), {"name": item.name})()
                    )
                    for item in real_items
                    if item.timeline_category == "activity"
                    and item.source != "selected_place"
                ), (case["name"], day.day, [item.name for item in real_items])
                assert not any(
                    CandidateSelector._has_non_visit_name(
                        type("Candidate", (), {"name": item.name})()
                    )
                    for item in real_items
                    if item.timeline_category == "activity"
                    and item.source != "selected_place"
                ), (case["name"], day.day, [item.name for item in real_items])
                assert sum(
                    item.timeline_category == "food" for item in real_items
                ) == 3, (case["name"], day.day)
                assert not meal_placeholders, (case["name"], day.day, meal_placeholders)
                assert not social_placeholders, (case["name"], day.day, social_placeholders)
                assert route_distance_km <= 30, (
                    case["name"], day.day, route_distance_km
                )
                assert max_leg_km <= 12, (case["name"], day.day, max_leg_km)
                all_place_ids.extend(
                    item.place_id for item in real_items if item.place_id is not None
                )
                scheduled_selected_refs.update(
                    item.name for item in real_items if item.source == "selected_place"
                )
                day_reports.append(
                    {
                        "day": day.day,
                        "theme": day.theme,
                        "realPlaceCount": len(real_items),
                        "activityCount": sum(
                            item.timeline_category == "activity"
                            for item in real_items
                        ),
                        "mealCount": sum(
                            item.timeline_category == "food"
                            for item in real_items
                        ),
                        "roles": [item.role for item in real_items],
                        "items": [item.name for item in real_items],
                        "mealPlaceholderCount": len(meal_placeholders),
                        "routeDistanceKm": route_distance_km,
                        "maxLegKm": max_leg_km,
                    }
                )
            assert len(all_place_ids) == len(set(all_place_ids)), case["name"]
            assert selected_refs.issubset(scheduled_selected_refs), case["name"]
            report.append({"case": case["name"], "days": day_reports})
        print(json.dumps({"status": "passed", "cases": report}, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
