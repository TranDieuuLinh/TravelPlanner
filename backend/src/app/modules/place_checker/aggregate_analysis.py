from app.modules.place_checker.analysis_contract import (
    AnalysisGap,
    CoverageAnalysis,
    GapAnalysis,
    TripAggregateAnalysis,
)
from app.modules.place_checker.budget_analysis import BudgetAnalysisService
from app.modules.place_checker.capacity_analysis import CapacityAnalysisService
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    BudgetAssessmentStatus,
    CapacityLoadStatus,
    CoverageLevel,
    EvaluationDimension,
    GapType,
    GeographicSpread,
    IssueSeverity,
    ItemResolutionStatus,
)
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.item_contract import ItemResolutionBatch
from app.shared.tools.search_places.normalization import normalize_text


FOOD_CATEGORIES = {
    "food",
    "food venue",
    "restaurant",
    "cafe",
    "drink dessert",
}


class TripAggregateAnalysisService:
    def __init__(
        self,
        *,
        budget_service: BudgetAnalysisService | None = None,
        capacity_service: CapacityAnalysisService | None = None,
    ) -> None:
        self.budget_service = budget_service or BudgetAnalysisService()
        self.capacity_service = capacity_service or CapacityAnalysisService()

    def analyze(
        self,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        context: TripEvaluationContext,
    ) -> TripAggregateAnalysis:
        budget = self.budget_service.analyze(places, items, context)
        capacity = self.capacity_service.analyze(places, items, context)
        coverage = self._coverage(places, items)
        gaps = self._gaps(places, items, context, budget.status, capacity, coverage)
        return TripAggregateAnalysis(
            budget=budget,
            capacity=capacity,
            coverage=coverage,
            gaps=gaps,
        )

    @staticmethod
    def _coverage(
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
    ) -> CoverageAnalysis:
        eligible = [place for place in places.places if place.planner_eligible]
        categories: dict[str, int] = {}
        time_hints: list[str] = []
        for evaluation in eligible:
            metadata = evaluation.place.metadata
            category = normalize_text(metadata.category) if metadata and metadata.category else "unknown"
            categories[category] = categories.get(category, 0) + 1
            time_hints.extend(
                source.source_time_hint
                for source in evaluation.place.source_places
                if source.source_time_hint
            )
        resolved_items = [
            item for item in items.items if item.status == ItemResolutionStatus.resolved
        ]
        unresolved_items = [
            item for item in items.items if item.status != ItemResolutionStatus.resolved
        ]
        food_covered = any(category in FOOD_CATEGORIES for category in categories)
        food_covered = food_covered or any(
            normalize_text(item.item.item_type) in {"food", "meal", "drink", "coffee"}
            for item in resolved_items
        )
        experience_covered = any(
            category not in {*FOOD_CATEGORIES, "hotel", "accommodation", "unknown"}
            for category in categories
        ) or any(
            normalize_text(item.item.item_type) in {"activity", "experience", "attraction"}
            for item in resolved_items
        )
        if eligible and food_covered and experience_covered and not unresolved_items:
            level = CoverageLevel.sufficient
        elif eligible or resolved_items:
            level = CoverageLevel.partial
        else:
            level = CoverageLevel.insufficient
        return CoverageAnalysis(
            level=level,
            planner_eligible_place_count=len(eligible),
            mandatory_place_count=sum(place.place.mandatory for place in places.places),
            category_distribution=categories,
            resolved_item_count=len(resolved_items),
            unresolved_item_count=len(unresolved_items),
            food_covered=food_covered,
            experience_covered=experience_covered,
            time_hints=list(dict.fromkeys(time_hints)),
        )

    @classmethod
    def _gaps(
        cls,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        context: TripEvaluationContext,
        budget_status: BudgetAssessmentStatus,
        capacity,
        coverage: CoverageAnalysis,
    ) -> GapAnalysis:
        gaps: list[AnalysisGap] = []
        mandatory_missing = [
            evaluation
            for evaluation in places.places
            if evaluation.place.mandatory
            and (
                evaluation.place.place_id is None
                or any(
                    finding.code in {"identity_not_resolved", "coordinates_missing"}
                    for finding in evaluation.findings
                )
            )
        ]
        if mandatory_missing:
            gaps.append(
                cls._gap(
                    GapType.mandatory_identity_metadata,
                    IssueSeverity.critical,
                    f"{len(mandatory_missing)} mandatory place thiếu identity hoặc tọa độ.",
                    "Xác minh identity/metadata; không tự loại yêu cầu của người dùng.",
                    place_ids=cls._place_ids(mandatory_missing),
                )
            )

        if capacity.status != CapacityLoadStatus.balanced:
            severity = {
                CapacityLoadStatus.overloaded: IssueSeverity.critical,
                CapacityLoadStatus.at_risk: IssueSeverity.high,
                CapacityLoadStatus.unknown: IssueSeverity.high,
                CapacityLoadStatus.underloaded: IssueSeverity.low,
            }[capacity.status]
            action = (
                "Giữ mandatory place và yêu cầu Planner xử lý overload."
                if capacity.status == CapacityLoadStatus.overloaded
                else "Bổ sung duration hoặc optional experience phù hợp."
            )
            gaps.append(
                cls._gap(
                    GapType.trip_capacity,
                    severity,
                    f"Capacity status là {capacity.status.value}.",
                    action,
                )
            )

        unresolved_food = cls._item_indexes(items, {"food", "meal", "drink", "coffee"})
        if not coverage.food_covered or unresolved_food:
            gaps.append(
                cls._gap(
                    GapType.food_coverage,
                    IssueSeverity.high if unresolved_food else IssueSeverity.medium,
                    "Chưa có food venue đủ tin cậy cho requirement/trip coverage.",
                    "Tìm optional food venue trong đúng ADM và budget profile.",
                    item_indexes=unresolved_food,
                )
            )

        unresolved_experience = cls._item_indexes(
            items,
            {"activity", "experience", "attraction"},
        )
        if not coverage.experience_covered or unresolved_experience:
            gaps.append(
                cls._gap(
                    GapType.experience_coverage,
                    IssueSeverity.high if unresolved_experience else IssueSeverity.medium,
                    "Chưa có experience đủ tin cậy hoặc explicit item chưa resolve.",
                    "Tìm optional experience phù hợp preference và people profile.",
                    item_indexes=unresolved_experience,
                )
            )

        time_conflicts = [
            evaluation
            for evaluation in places.places
            if "source_time_hint_conflict" in evaluation.place.evidence_conflicts
        ]
        if time_conflicts:
            gaps.append(
                cls._gap(
                    GapType.time_of_day,
                    IssueSeverity.high,
                    "Các nguồn đưa time hint mâu thuẫn.",
                    "Yêu cầu review time hint trước khi xếp timeline.",
                    place_ids=cls._place_ids(time_conflicts),
                )
            )

        if budget_status != BudgetAssessmentStatus.within:
            severity = (
                IssueSeverity.critical
                if budget_status == BudgetAssessmentStatus.over
                else IssueSeverity.high
            )
            gaps.append(
                cls._gap(
                    GapType.budget,
                    severity,
                    f"Budget status là {budget_status.value}.",
                    "Xác minh unknown cost hoặc ưu tiên optional place cost thấp.",
                )
            )

        category_count = len(
            [category for category in coverage.category_distribution if category != "unknown"]
        )
        if context.days > 1 and coverage.planner_eligible_place_count and category_count < 2:
            gaps.append(
                cls._gap(
                    GapType.diversity,
                    IssueSeverity.medium,
                    "Planner-eligible set chỉ có một nhóm trải nghiệm.",
                    "Tìm optional candidate thuộc category khác nếu capacity cho phép.",
                )
            )

        if capacity.geographic_overhead.spread == GeographicSpread.dispersed:
            gaps.append(
                cls._gap(
                    GapType.geographic_balance,
                    IssueSeverity.high,
                    "Candidate set phân tán địa lý ở mức coarse.",
                    "Ưu tiên candidate gần cụm chính; route chi tiết để Planner xử lý.",
                )
            )

        people_issues = [
            evaluation
            for evaluation in places.places
            if any(finding.dimension == EvaluationDimension.people for finding in evaluation.findings)
            or any("suitability" in constraint.code for constraint in evaluation.planner_constraints)
        ]
        if people_issues:
            gaps.append(
                cls._gap(
                    GapType.people_accessibility,
                    IssueSeverity.high,
                    "Có place chưa phù hợp hoặc chưa rõ suitability cho đoàn.",
                    "Xác minh suitability/accessibility hoặc tìm optional alternative.",
                    place_ids=cls._place_ids(people_issues),
                )
            )

        quality_issues = [
            evaluation
            for evaluation in places.places
            if evaluation.data_quality.missing_fields or evaluation.data_quality.stale
        ]
        if quality_issues:
            gaps.append(
                cls._gap(
                    GapType.data_quality,
                    IssueSeverity.high,
                    "Một hoặc nhiều place thiếu cost/opening/duration/freshness data.",
                    "Enrich các field cần thiết trước final planning.",
                    place_ids=cls._place_ids(quality_issues),
                )
            )

        destination_issues = [
            evaluation
            for evaluation in places.places
            if evaluation.destination_compatible is False
        ]
        if destination_issues:
            gaps.append(
                cls._gap(
                    GapType.destination_compatibility,
                    IssueSeverity.critical,
                    "Có place nằm ngoài canonical destination.",
                    "Review destination hoặc loại optional mismatch khỏi Planner input.",
                    place_ids=cls._place_ids(destination_issues),
                )
            )
        return GapAnalysis(
            gaps=gaps,
            open_count=len(gaps),
            critical_count=sum(gap.severity == IssueSeverity.critical for gap in gaps),
        )

    @staticmethod
    def _gap(
        gap_type: GapType,
        severity: IssueSeverity,
        trigger: str,
        action: str,
        *,
        place_ids: list[str] | None = None,
        item_indexes: list[int] | None = None,
    ) -> AnalysisGap:
        return AnalysisGap(
            gap_id=f"gap:{gap_type.value}",
            gap_type=gap_type,
            severity=severity,
            trigger=trigger,
            suggested_action=action,
            related_place_ids=place_ids or [],
            related_item_indexes=item_indexes or [],
        )

    @staticmethod
    def _place_ids(evaluations) -> list[str]:
        return list(
            dict.fromkeys(
                evaluation.place.place_id
                for evaluation in evaluations
                if evaluation.place.place_id
            )
        )

    @staticmethod
    def _item_indexes(items: ItemResolutionBatch, types: set[str]) -> list[int]:
        return [
            item.item_index
            for item in items.items
            if item.status != ItemResolutionStatus.resolved
            and normalize_text(item.item.item_type) in types
        ]
