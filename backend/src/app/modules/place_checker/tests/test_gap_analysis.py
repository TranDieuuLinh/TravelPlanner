from app.modules.place_checker.aggregate_analysis import TripAggregateAnalysisService
from app.modules.place_checker.enums import (
    EvaluationDimension,
    GapType,
    IssueSeverity,
)
from app.modules.place_checker.evaluation_contract import (
    EvaluationFinding,
    PlannerConstraint,
)
from app.modules.place_checker.item_contract import ItemResolutionBatch
from app.modules.place_checker.tests.analysis_fixtures import (
    analysis_context,
    empty_items,
    evaluated_place,
    place_batch,
    unresolved_item,
)


def gap_types(result) -> set[GapType]:
    return {gap.gap_type for gap in result.gaps.gaps}


def test_missing_food_and_single_category_create_coverage_gaps() -> None:
    result = TripAggregateAnalysisService().analyze(
        place_batch(evaluated_place("museum", category="museum")),
        empty_items(),
        analysis_context(days=3),
    )

    assert result.coverage.food_covered is False
    assert GapType.food_coverage in gap_types(result)
    assert GapType.diversity in gap_types(result)


def test_resolved_food_and_experience_make_coverage_sufficient() -> None:
    result = TripAggregateAnalysisService().analyze(
        place_batch(
            evaluated_place("museum", category="museum"),
            evaluated_place("restaurant", mandatory=False, category="restaurant"),
        ),
        empty_items(),
        analysis_context(),
    )

    assert result.coverage.food_covered is True
    assert result.coverage.experience_covered is True
    assert result.coverage.level.value == "sufficient"
    assert GapType.food_coverage not in gap_types(result)


def test_unresolved_food_item_is_linked_to_food_gap() -> None:
    items = ItemResolutionBatch(
        items=[unresolved_item(3, name="pho", item_type="food")]
    )

    result = TripAggregateAnalysisService().analyze(
        place_batch(evaluated_place("museum", category="museum")),
        items,
        analysis_context(),
    )

    gap = next(gap for gap in result.gaps.gaps if gap.gap_type == GapType.food_coverage)
    assert gap.related_item_indexes == [3]
    assert gap.severity == IssueSeverity.high


def test_people_constraint_creates_people_accessibility_gap() -> None:
    place = evaluated_place(
        "family_unknown",
        constraints=[
            PlannerConstraint(
                code="verify_children_suitability",
                message="Verify children suitability",
            )
        ],
    )

    result = TripAggregateAnalysisService().analyze(
        place_batch(place),
        empty_items(),
        analysis_context(),
    )

    assert GapType.people_accessibility in gap_types(result)


def test_data_quality_gap_collects_related_place_ids() -> None:
    place = evaluated_place(
        "missing_hours",
        missing_fields=["opening_hours", "cost"],
    )

    result = TripAggregateAnalysisService().analyze(
        place_batch(place),
        empty_items(),
        analysis_context(),
    )

    gap = next(gap for gap in result.gaps.gaps if gap.gap_type == GapType.data_quality)
    assert gap.related_place_ids == ["missing_hours"]


def test_time_hint_conflict_creates_time_of_day_gap() -> None:
    place = evaluated_place(
        "time_conflict",
        evidence_conflicts=["source_time_hint_conflict"],
    )

    result = TripAggregateAnalysisService().analyze(
        place_batch(place),
        empty_items(),
        analysis_context(),
    )

    assert GapType.time_of_day in gap_types(result)


def test_destination_mismatch_creates_critical_gap() -> None:
    place = evaluated_place(
        "wrong_adm",
        planner_eligible=False,
        destination_compatible=False,
        findings=[
            EvaluationFinding(
                code="destination_mismatch",
                dimension=EvaluationDimension.destination,
                severity=IssueSeverity.critical,
                hard=True,
                message="Wrong destination",
            )
        ],
    )

    result = TripAggregateAnalysisService().analyze(
        place_batch(place),
        empty_items(),
        analysis_context(),
    )

    gap = next(
        gap
        for gap in result.gaps.gaps
        if gap.gap_type == GapType.destination_compatibility
    )
    assert gap.severity == IssueSeverity.critical


def test_gap_analysis_does_not_create_place_or_resolve_gap_itself() -> None:
    result = TripAggregateAnalysisService().analyze(
        place_batch(evaluated_place("museum", category="museum")),
        empty_items(),
        analysis_context(),
    )

    assert all(gap.resolved_place_ids == [] for gap in result.gaps.gaps)
    assert result.gaps.open_count == len(result.gaps.gaps)
