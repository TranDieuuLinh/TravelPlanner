from decimal import Decimal

from app.modules.place_checker.analysis.budget import BudgetAnalysisService
from app.modules.place_checker.analysis.capacity import CapacityAnalysisService
from app.modules.place_checker.contract import CapacityRange
from app.modules.place_checker.enums import (
    BudgetAssessmentStatus,
    CapacityLoadStatus,
    CostTier,
    GeographicSpread,
    SourceTier,
)
from app.modules.place_checker.tests.analysis_fixtures import (
    analysis_context,
    empty_items,
    evaluated_place,
    place_batch,
)
from app.shared.contracts.place import Coordinates


def test_relative_low_budget_flags_expensive_optional_place() -> None:
    places = place_batch(
        evaluated_place("mandatory", cost_tier=CostTier.low),
        evaluated_place(
            "optional",
            mandatory=False,
            cost_tier=CostTier.premium,
        ),
    )

    result = BudgetAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(level="low"),
    )

    assert result.status == BudgetAssessmentStatus.at_risk
    assert result.target_amount is None
    assert result.mandatory.place_count == 1
    assert result.optional.place_count == 1


def test_target_budget_with_complete_range_is_within() -> None:
    places = place_batch(
        evaluated_place(
            "paid",
            minimum_cost=50,
            typical_cost=60,
            maximum_cost=80,
        )
    )

    result = BudgetAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(target_amount=Decimal("100")),
    )

    assert result.status == BudgetAssessmentStatus.within
    assert result.total.amount_range.maximum == Decimal("80")
    assert result.total.amount_range.complete is True


def test_target_budget_range_crossing_target_is_at_risk() -> None:
    places = place_batch(
        evaluated_place(
            "paid",
            minimum_cost=50,
            typical_cost=100,
            maximum_cost=150,
        )
    )

    result = BudgetAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(target_amount=Decimal("100")),
    )

    assert result.status == BudgetAssessmentStatus.at_risk


def test_mandatory_minimum_over_target_is_over_even_with_unknown_optional() -> None:
    places = place_batch(
        evaluated_place(
            "mandatory",
            minimum_cost=120,
            typical_cost=140,
            maximum_cost=160,
        ),
        evaluated_place("unknown", mandatory=False, cost_tier=CostTier.unknown),
    )

    result = BudgetAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(target_amount=Decimal("100")),
    )

    assert result.status == BudgetAssessmentStatus.over
    assert result.total.unknown_amount_count == 1


def test_unknown_cost_is_not_converted_to_zero_but_free_is_zero() -> None:
    places = place_batch(
        evaluated_place("unknown", cost_tier=CostTier.unknown),
        evaluated_place("free", mandatory=False, cost_tier=CostTier.free),
    )

    result = BudgetAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(),
    )

    assert result.total.unknown_amount_count == 1
    assert result.total.known_amount_count == 1
    assert result.total.amount_range.minimum == Decimal("0")
    assert result.total.amount_range.complete is False
    assert result.status == BudgetAssessmentStatus.at_risk


def test_mandatory_capacity_overload_is_reported_without_removal() -> None:
    places = place_batch(
        evaluated_place(
            "long_visit",
            minimum_duration=700,
            typical_duration=720,
            maximum_duration=750,
        )
    )
    context = analysis_context(
        capacity=CapacityRange(
            minimum_minutes=360,
            typical_minutes=480,
            maximum_minutes=600,
        )
    )

    result = CapacityAnalysisService().analyze(places, empty_items(), context)

    assert result.status == CapacityLoadStatus.overloaded
    assert result.mandatory.place_count == 1
    assert any("không tự loại" in warning for warning in result.warnings)


def test_capacity_uses_minutes_instead_of_places_per_day() -> None:
    places = place_batch(
        evaluated_place(
            "short_visit",
            minimum_duration=30,
            typical_duration=60,
            maximum_duration=90,
        )
    )

    result = CapacityAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(days=4),
    )

    assert result.status == CapacityLoadStatus.underloaded
    assert result.typical_utilization == 0.125


def test_unknown_duration_returns_unknown_capacity() -> None:
    places = place_batch(
        evaluated_place(
            "unknown_duration",
            minimum_duration=None,
            typical_duration=None,
            maximum_duration=None,
        )
    )

    result = CapacityAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(),
    )

    assert result.status == CapacityLoadStatus.unknown
    assert result.total.unknown_duration_count == 1


def test_geographic_overhead_uses_coarse_spread_without_matrix() -> None:
    places = place_batch(
        evaluated_place(
            "north",
            source_tier=SourceTier.direct_user,
            coordinates=Coordinates(latitude=21.20, longitude=105.84),
        ),
        evaluated_place(
            "south",
            mandatory=False,
            coordinates=Coordinates(latitude=21.00, longitude=105.84),
        ),
    )

    result = CapacityAnalysisService().analyze(
        places,
        empty_items(),
        analysis_context(),
    )

    assert result.geographic_overhead.spread == GeographicSpread.dispersed
    assert result.geographic_overhead.estimated_minutes == 45
