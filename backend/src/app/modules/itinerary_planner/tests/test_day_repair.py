from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.modules.itinerary_planner.day_repair import DayRepairError, DayRepairService
from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    RouteDetail,
    TravelMatrix,
)
from app.shared.tools.transport_cost import XanhSmTransportCostEstimator


class FakeRoutingProvider:
    async def matrix(self, locations, profile):
        cells = tuple(
            tuple(
                MatrixCell(0, 0, True)
                if origin == destination
                else MatrixCell(300, 1_000, True)
                for destination in locations
            )
            for origin in locations
        )
        return TravelMatrix(
            node_ids=tuple(item.node_id for item in locations),
            cells=cells,
            profile=profile,
            provider="fake",
            provider_version="test",
        )

    async def route(self, legs, profile):
        del profile
        return tuple(
            RouteDetail(
                leg.origin.node_id,
                leg.destination.node_id,
                300,
                1_000,
                "??_ibE_ibE",
                "fake",
            )
            for leg in legs
        )


def _stop(item_id: str, start: int, *, opening_hours=None) -> dict:
    return {
        "itemId": item_id,
        "placeId": item_id,
        "name": item_id.upper(),
        "kind": "place",
        "priority": "user_input",
        "startMinute": start,
        "endMinute": start + 60,
        "durationMinutes": 60,
        "coordinates": {"latitude": 21.0 + start / 100_000, "longitude": 105.8},
        "openingHours": opening_hours,
        "costPerPerson": 0,
    }


def _output(stops: list[dict]) -> dict:
    return {
        "destination": "Hà Nội",
        "timezone": "Asia/Ho_Chi_Minh",
        "people": 1,
        "accommodation": {
            "placeId": "hotel",
            "name": "Hotel",
            "coordinates": {"latitude": 21.01, "longitude": 105.81},
        },
        "days": [
            {
                "day": 1,
                "date": "2026-08-21",
                "stops": stops,
                "legs": [],
                "activityMinutes": 180,
                "travelMinutes": 0,
                "costPerPerson": 0,
                "costBreakdown": {
                    "accommodation": 0,
                    "food": 0,
                    "localTransport": 0,
                    "activities": 0,
                    "misc": 0,
                    "total": 0,
                    "currency": "VND",
                },
            },
            {
                "day": 2,
                "date": "2026-08-22",
                "stops": [_stop("other", 540)],
                "legs": [],
                "activityMinutes": 60,
                "travelMinutes": 0,
                "costPerPerson": 0,
                "costBreakdown": {"total": 0, "currency": "VND"},
            },
        ],
        "currency": "VND",
        "totalCostPerPerson": 0,
        "warnings": [],
        "phaseTimingsMs": {},
    }


def _replacement(*, opening_hours: list[str]) -> dict:
    return {
        "placeId": "new-b",
        "name": "New B",
        "address": "Hà Nội",
        "placeType": "travel_place",
        "latitude": 21.02,
        "longitude": 105.82,
        "durationMinutes": 60,
        "openingHours": opening_hours,
        "rating": 4.7,
        "reviewCount": 120,
        "costPerPerson": 50_000,
    }


def _service() -> DayRepairService:
    provider = FakeRoutingProvider()
    return DayRepairService(provider, provider, XanhSmTransportCostEstimator())


def test_replace_repairs_whole_day_and_keeps_other_days_unchanged() -> None:
    payload = _output([_stop("a", 540), _stop("b", 610), _stop("c", 680)])
    untouched = deepcopy(payload["days"][1])

    repaired = asyncio.run(
        _service().repair(
            payload,
            day=1,
            item_id="b",
            replacement=_replacement(opening_hours=["10:00-18:00"]),
        )
    )

    first_day = repaired["days"][0]
    assert [item["placeId"] for item in first_day["stops"]] == ["a", "new-b", "c"]
    assert [item["startMinute"] for item in first_day["stops"]] == [540, 610, 680]
    assert len(first_day["legs"]) == 3  # two stops legs plus return to hotel
    assert repaired["days"][1] == untouched
    assert "giữ nguyên thứ tự" in repaired["warnings"][-1]


def test_replace_uses_cp_sat_to_reorder_only_the_affected_day() -> None:
    first_hours = {"1": [{"startMinute": 600, "endMinute": 690}]}
    last_hours = {"1": [{"startMinute": 720, "endMinute": 900}]}
    payload = _output(
        [
            _stop("a", 600, opening_hours=first_hours),
            _stop("b", 700),
            _stop("c", 720, opening_hours=last_hours),
        ]
    )

    repaired = asyncio.run(
        _service().repair(
            payload,
            day=1,
            item_id="b",
            replacement=_replacement(opening_hours=["08:00-09:30"]),
        )
    )

    assert [item["placeId"] for item in repaired["days"][0]["stops"]] == [
        "new-b",
        "a",
        "c",
    ]
    assert "thứ tự được điều chỉnh" in repaired["warnings"][-1]


def test_replace_rejects_a_window_shorter_than_the_visit() -> None:
    payload = _output([_stop("a", 540), _stop("b", 610), _stop("c", 680)])

    with pytest.raises(DayRepairError) as captured:
        asyncio.run(
            _service().repair(
                payload,
                day=1,
                item_id="b",
                replacement=_replacement(opening_hours=["08:00-08:30"]),
            )
        )

    assert captured.value.code == "PLACE_CLOSED"
