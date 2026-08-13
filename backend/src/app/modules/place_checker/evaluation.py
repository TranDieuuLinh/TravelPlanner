from __future__ import annotations

from datetime import UTC, datetime

from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.avoid_policy import matching_avoids
from app.modules.place_checker.enums import (
    CostTier,
    EvaluationDimension,
    IdentityResolutionStatus,
    IssueSeverity,
    OperationalStatus,
)
from app.modules.place_checker.evaluation_contract import (
    EvaluationFinding,
    PeopleSuitabilityEvaluation,
    PlaceEvaluation,
    PlaceEvaluationBatch,
    PlannerConstraint,
)
from app.modules.place_checker.evaluation_policy import (
    PLANNER_ELIGIBLE_STATES,
    destination_compatible,
    evaluate_data_quality,
    final_state,
    matching_labels,
    place_labels,
    unique_constraints,
)
from app.modules.place_checker.resolution_contract import EnrichedIdentityPlace
from app.shared.tools.search_places.normalization import normalize_text


class PlaceEvaluationService:
    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(UTC)

    def evaluate_all(
        self,
        places: list[EnrichedIdentityPlace],
        context: TripEvaluationContext,
    ) -> PlaceEvaluationBatch:
        evaluated = [self.evaluate(place, context) for place in places]
        eligible_ids = [
            result.place.place_id
            for result in evaluated
            if result.planner_eligible and result.place.place_id is not None
        ]
        warnings = list(
            dict.fromkeys(
                warning for result in evaluated for warning in result.warnings
            )
        )
        return PlaceEvaluationBatch(
            places=evaluated,
            planner_eligible_place_ids=eligible_ids,
            warnings=warnings,
        )

    def evaluate(
        self,
        place: EnrichedIdentityPlace,
        context: TripEvaluationContext,
    ) -> PlaceEvaluation:
        findings: list[EvaluationFinding] = []
        constraints: list[PlannerConstraint] = []
        metadata = place.metadata
        compatible_destination = destination_compatible(place)

        self._evaluate_identity(place, findings)
        self._evaluate_destination(compatible_destination, findings)
        self._evaluate_operational(place, findings, constraints)
        self._evaluate_people(place, context, findings, constraints)

        labels = place_labels(place)
        preference_matches = matching_labels(context.preferences, labels)
        avoid_conflicts = matching_avoids(context.avoids, labels)
        self._evaluate_avoids(avoid_conflicts, findings)
        self._evaluate_budget(place, context, findings)
        self._add_planning_constraints(place, constraints)

        data_quality = evaluate_data_quality(place, self.now)
        if data_quality.stale:
            findings.append(
                self._finding(
                    "metadata_stale",
                    EvaluationDimension.data_quality,
                    IssueSeverity.medium,
                    "Metadata đã cũ và cần được xác minh lại.",
                )
            )
            constraints.append(
                PlannerConstraint(
                    code="verify_stale_metadata",
                    message="Xác minh metadata hiện tại trước khi xếp lịch.",
                )
            )

        state = final_state(place, findings, constraints, avoid_conflicts)
        planner_eligible = state in PLANNER_ELIGIBLE_STATES
        warnings = list(
            dict.fromkeys(
                [
                    *place.warnings,
                    *(finding.message for finding in findings),
                ]
            )
        )
        suitability = PeopleSuitabilityEvaluation(
            children=metadata.children_suitable if metadata else None,
            infants=metadata.infants_suitable if metadata else None,
            accessibility=metadata.accessibility if metadata else [],
        )
        return PlaceEvaluation(
            place=place,
            state=state,
            planner_eligible=planner_eligible,
            destination_compatible=compatible_destination,
            preference_matches=preference_matches,
            avoid_conflicts=avoid_conflicts,
            people_suitability=suitability,
            data_quality=data_quality,
            findings=findings,
            planner_constraints=unique_constraints(constraints),
            warnings=warnings,
        )

    @staticmethod
    def _evaluate_identity(
        place: EnrichedIdentityPlace,
        findings: list[EvaluationFinding],
    ) -> None:
        if place.status != IdentityResolutionStatus.resolved or not place.place_id:
            findings.append(
                PlaceEvaluationService._finding(
                    "identity_not_resolved",
                    EvaluationDimension.identity,
                    IssueSeverity.critical,
                    "Địa điểm chưa có canonical identity đủ tin cậy.",
                    hard=True,
                )
            )
        if place.metadata is None or place.metadata.coordinates is None:
            findings.append(
                PlaceEvaluationService._finding(
                    "coordinates_missing",
                    EvaluationDimension.destination,
                    IssueSeverity.critical,
                    "Địa điểm chưa có tọa độ hợp lệ.",
                    hard=True,
                )
            )

    @staticmethod
    def _evaluate_destination(
        compatible: bool | None,
        findings: list[EvaluationFinding],
    ) -> None:
        if compatible is False:
            findings.append(
                PlaceEvaluationService._finding(
                    "destination_mismatch",
                    EvaluationDimension.destination,
                    IssueSeverity.critical,
                    "Địa điểm không thuộc destination đã xác định.",
                    hard=True,
                )
            )

    @staticmethod
    def _evaluate_operational(
        place: EnrichedIdentityPlace,
        findings: list[EvaluationFinding],
        constraints: list[PlannerConstraint],
    ) -> None:
        metadata = place.metadata
        if metadata is None:
            return
        if metadata.operational_status in {
            OperationalStatus.permanently_closed,
            OperationalStatus.temporarily_closed,
        }:
            findings.append(
                PlaceEvaluationService._finding(
                    metadata.operational_status.value,
                    EvaluationDimension.operational,
                    IssueSeverity.critical,
                    "Địa điểm hiện được ghi nhận là đóng cửa.",
                    hard=True,
                )
            )
        elif metadata.operational_status == OperationalStatus.unknown:
            findings.append(
                PlaceEvaluationService._finding(
                    "operational_status_unknown",
                    EvaluationDimension.operational,
                    IssueSeverity.medium,
                    "Chưa xác định được trạng thái hoạt động hiện tại.",
                )
            )
        if metadata.opening_hours is None:
            constraints.append(
                PlannerConstraint(
                    code="verify_opening_hours",
                    message="Xác minh giờ mở cửa trước khi chọn time slot.",
                )
            )
        if metadata.reservation_required is True:
            constraints.append(
                PlannerConstraint(
                    code="reservation_required",
                    message="Phải đặt chỗ trước khi đưa địa điểm vào lịch.",
                )
            )

    @staticmethod
    def _evaluate_people(
        place: EnrichedIdentityPlace,
        context: TripEvaluationContext,
        findings: list[EvaluationFinding],
        constraints: list[PlannerConstraint],
    ) -> None:
        metadata = place.metadata
        if metadata is None:
            return
        checks = (
            (context.people.children, metadata.children_suitable, "children"),
            (context.people.infants, metadata.infants_suitable, "infants"),
        )
        for count, suitable, group in checks:
            if count <= 0:
                continue
            if suitable is False:
                findings.append(
                    PlaceEvaluationService._finding(
                        f"{group}_not_suitable",
                        EvaluationDimension.people,
                        IssueSeverity.critical,
                        f"Địa điểm không phù hợp với nhóm {group}.",
                        hard=True,
                    )
                )
            elif suitable is None:
                constraints.append(
                    PlannerConstraint(
                        code=f"verify_{group}_suitability",
                        message=f"Xác minh mức độ phù hợp với nhóm {group}.",
                    )
                )

    @staticmethod
    def _evaluate_avoids(
        avoid_conflicts: list[str],
        findings: list[EvaluationFinding],
    ) -> None:
        for avoid in avoid_conflicts:
            findings.append(
                PlaceEvaluationService._finding(
                    f"avoid_{normalize_text(avoid).replace(' ', '_')}",
                    EvaluationDimension.avoid,
                    IssueSeverity.high,
                    f"Địa điểm xung đột với tránh né mềm: {avoid}.",
                )
            )

    @staticmethod
    def _evaluate_budget(
        place: EnrichedIdentityPlace,
        context: TripEvaluationContext,
        findings: list[EvaluationFinding],
    ) -> None:
        metadata = place.metadata
        if metadata is None:
            return
        if (
            context.budget.level == "low"
            and metadata.cost_tier in {CostTier.high, CostTier.premium}
        ):
            findings.append(
                PlaceEvaluationService._finding(
                    "relative_budget_conflict",
                    EvaluationDimension.cost,
                    IssueSeverity.high,
                    "Cost tier của địa điểm không phù hợp budget level thấp.",
                )
            )

    @staticmethod
    def _add_planning_constraints(
        place: EnrichedIdentityPlace,
        constraints: list[PlannerConstraint],
    ) -> None:
        metadata = place.metadata
        if metadata and metadata.typical_duration_minutes is None:
            constraints.append(
                PlannerConstraint(
                    code="estimate_duration",
                    message="Cần ước lượng duration trước khi xếp timeline.",
                )
            )
        if metadata and metadata.cost_tier == CostTier.unknown and (
            metadata.typical_cost is None
        ):
            constraints.append(
                PlannerConstraint(
                    code="verify_cost_profile",
                    message="Xác minh cost profile trước khi chốt ngân sách.",
                )
            )
        time_hints = list(
            dict.fromkeys(
                source.source_time_hint
                for source in place.source_places
                if source.source_time_hint
            )
        )
        for time_hint in time_hints:
            constraints.append(
                PlannerConstraint(
                    code="respect_source_time_hint",
                    message=f"Ưu tiên khung thời gian từ nguồn: {time_hint}.",
                )
            )

    @staticmethod
    def _finding(
        code: str,
        dimension: EvaluationDimension,
        severity: IssueSeverity,
        message: str,
        *,
        hard: bool = False,
    ) -> EvaluationFinding:
        return EvaluationFinding(
            code=code,
            dimension=dimension,
            severity=severity,
            hard=hard,
            message=message,
        )
