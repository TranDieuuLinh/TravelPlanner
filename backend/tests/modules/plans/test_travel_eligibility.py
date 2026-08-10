from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.travel_eligibility import (
    is_default_travel_eligible,
)
from app.modules.plans.place_selector.visit_windows import (
    effective_preferred_time_windows,
)


def test_operational_venues_are_not_automatic_travel_activities() -> None:
    assert not is_default_travel_eligible(
        name="Phòng khám Đa khoa 5 Sao Hà Nội",
        place_type="medical clinic",
        tags=["health"],
    )
    assert not is_default_travel_eligible(
        name="Trung tâm tư vấn giáo dục",
        place_type="consultant",
        tags=["education"],
    )
    assert is_default_travel_eligible(
        name="Vietnam National Museum of History",
        place_type="museum",
        tags=["history"],
    )


def test_market_windows_require_structured_time_sensitive_type() -> None:
    generic = SelectablePlace(
        name="Local Market", placeType="market", regionKey="vn,ha-noi"
    )
    fresh = SelectablePlace(
        name="Morning Produce Market",
        placeType="market",
        regionKey="vn,ha-noi",
        tags=["fresh_market"],
    )

    assert effective_preferred_time_windows(generic) == []
    windows = effective_preferred_time_windows(fresh)
    assert [(window.start, window.end) for window in windows] == [
        ("05:00", "08:00")
    ]
