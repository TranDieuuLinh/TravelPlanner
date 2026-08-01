from app.modules.plans.planner.opening_hours_parser import (
    extract_time_intervals,
    is_24_hours,
)


def test_parses_google_meridiem_hours_with_unicode_spacing_and_dash() -> None:
    assert extract_time_intervals(
        [
            {
                "rawTimeSlots": "11\u202fAM–11\u202fPM",
                "is24Hours": False,
            }
        ]
    ) == [(11 * 60, 23 * 60)]


def test_parses_split_google_hours_with_inherited_meridiem() -> None:
    assert extract_time_intervals(
        [
            {
                "rawTimeSlots": "11 AM–2 PM, 5–11 PM",
                "is24Hours": False,
            }
        ]
    ) == [
        (11 * 60, 14 * 60),
        (17 * 60, 23 * 60),
    ]


def test_raw_open_24_hours_repairs_incorrect_boolean_flag() -> None:
    opening_hours = [
        {
            "rawTimeSlots": "Open 24 hours",
            "is24Hours": False,
        }
    ]

    assert extract_time_intervals(opening_hours) == [(0, 24 * 60)]
    assert is_24_hours(opening_hours) is True
