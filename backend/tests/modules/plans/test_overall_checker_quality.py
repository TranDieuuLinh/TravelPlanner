from types import SimpleNamespace

import pytest

from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import Plan, PlanDay, PlanItem, TravelIntent, UnscheduledPlace
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace


def _plan(items, *, required_experiences=None, unscheduled=None):
    return Plan(
        id="quality-plan",
        kind=PlanKind.main,
        status=PlanStatus.checking,
        title="Quality fixture",
        destination="Hanoi",
        intent=TravelIntent(
            destination="Hanoi",
            days=1,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        requiredExperiences=required_experiences or [],
        days=[PlanDay(day=1, theme="Explore", items=items)],
        unscheduledPlaces=unscheduled or [],
    )


def _item(item_id, *, place_type="restaurant", tags=None, category=None, **kwargs):
    payload = {
        "itemId": item_id,
        "name": item_id,
        "timeWindow": kwargs.pop("time_window", "09:00-10:00"),
        "placeType": place_type,
        "timelineCategory": category or ("food" if place_type == "restaurant" else "activity"),
        "tags": tags or [],
        "openingHours": kwargs.pop("opening_hours", [{"openTime": "08:00", "closeTime": "20:00"}]),
    }
    payload.update(kwargs)
    return PlanItem(**payload)


def test_food_heavy_plan_reports_dominance_with_ids_and_action():
    items = [_item(f"food-{index}") for index in range(20)] + [
        _item("museum", place_type="museum", category="activity")
    ]

    report = OverallChecker().check(_plan(items))
    issues = {issue.code: issue for issue in report.issues}

    assert "food_drink_dominates_main_activities" in issues
    issue = issues["food_drink_dominates_main_activities"]
    assert issue.severity == "warning"
    assert issue.affected_item_ids[:2] == ["food-0", "food-1"]
    assert issue.suggested_action
    assert issue.owner == "planner"
    assert report.status in {"warning", "failed"}


def test_diverse_plan_has_no_diversity_warning():
    items = [
        _item("museum", place_type="museum", category="activity"),
        _item("park", place_type="park", category="activity"),
        _item("restaurant"),
    ]

    report = OverallChecker().check(_plan(items))

    assert "food_drink_dominates_main_activities" not in {i.code for i in report.issues}
    assert "insufficient_main_experience_diversity" not in {i.code for i in report.issues}


def test_missing_required_anchor_and_unpreserved_special_are_errors():
    requirement = SimpleNamespace(
        requirement_id="req-temple",
        category="main_experience",
        activity_id="walk-temple",
        anchor_place_ids=["temple"],
        candidate_place_ids=[],
    )

    report = OverallChecker().check(_plan([_item("lunch")], required_experiences=[requirement]))
    codes = {issue.code for issue in report.issues}

    assert "required_experience_missing" in codes
    assert "special_experience_not_preserved" in codes
    assert report.status == "failed"


def test_selected_place_unscheduled_is_distinct_from_route_errors():
    unscheduled = UnscheduledPlace(
        placeId="selected-1",
        name="Selected place",
        reason="No available slot",
        reasonCode="no_available_slot",
    )

    report = OverallChecker().check(_plan([_item("museum", place_type="museum", category="activity")], unscheduled=[unscheduled]))
    issue = next(issue for issue in report.issues if issue.code == "selected_place_unscheduled")

    assert issue.severity == "warning"
    assert issue.owner == "selector"
    assert "route error" not in issue.message.casefold()


def test_timing_opening_hours_and_nearby_evidence_are_reported_separately():
    item = _item(
        "nearby",
        place_type="museum",
        category="activity",
        selectionMethod="nearby_graph_survey",
        preferredTimeWindows=[{"start": "14:00", "end": "15:00"}],
        openingHours=[],
    )

    report = OverallChecker().check(_plan([item]))
    by_code = {issue.code: issue for issue in report.issues}

    assert by_code["timing_recommendation_ignored"].severity == "warning"
    assert by_code["opening_hours_unknown"].severity == "info"
    assert by_code["nearby_fill_without_evidence"].severity == "warning"
    assert by_code["opening_hours_unknown"].owner == "provider"
