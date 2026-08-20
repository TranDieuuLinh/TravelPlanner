from app.modules.place_checker.analysis.contract import TripAggregateAnalysis
from app.modules.place_checker.checked_output_contract import (
    CheckedCost,
    CheckedDestination,
    CheckedDuration,
    CheckedEvaluation,
    CheckedOpening,
    CheckedProvenance,
    CheckedRanking,
    CheckedSuitability,
    CheckedVerification,
    GeographicAnalysis,
)
from app.modules.place_checker.contract import (
    CandidateValidationIssue,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    AdmResolutionStatus,
    IdentityResolutionStatus,
    ItemResolutionStatus,
    PlaceCheckerStatus,
    PlaceLifecycleState,
    SourceTier,
    UnresolvedEntityType,
    VerificationStatus,
)
from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.resolution.item_contract import ItemResolutionBatch
from app.modules.place_checker.selection.food.contract import (
    FoodMealCoverage,
    FoodSelectionBatch,
)
from app.modules.place_checker.output_contract import (
    CheckedPlace,
    PlaceCheckerExecutionMetadata,
    PlaceCheckerResult,
    UnresolvedEntity,
)
from app.modules.place_checker.retrieval.contract import RetrievalBatch
from app.modules.place_checker.scoring.contract import (
    CandidateRankingBatch,
    ScoredCandidate,
)
from app.modules.place_checker.selection.style_contract import (
    StyleCandidateSelectionBatch,
)


class PlaceCheckerOutputAssembler:
    def assemble(
        self,
        *,
        context: TripEvaluationContext,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        analysis: TripAggregateAnalysis,
        metadata: PlaceCheckerExecutionMetadata,
        validation_issues: list[CandidateValidationIssue] | None = None,
        retrieval: RetrievalBatch | None = None,
        ranking: CandidateRankingBatch | None = None,
        verification_by_place_id: dict[str, VerificationStatus] | None = None,
        ranking_by_place_id: dict[str, ScoredCandidate] | None = None,
        extra_warnings: list[str] | None = None,
        food_selection: FoodSelectionBatch | None = None,
        style_selection: StyleCandidateSelectionBatch | None = None,
    ) -> PlaceCheckerResult:
        verification = verification_by_place_id or {}
        ranking_map = ranking_by_place_id or {}
        checked = [
            self._checked(evaluation, verification, ranking_map)
            for evaluation in places.places
        ]
        eligible_ids = [
            place.place_id
            for place in checked
            if place.place_id
            and place.evaluation.planner_eligible
            and self._planner_verification_allowed(place)
        ]
        unresolved = self._unresolved(
            context,
            places,
            items,
            validation_issues or [],
        )
        constraints = list(
            {
                (constraint.code, constraint.message): constraint
                for evaluation in places.places
                for constraint in evaluation.planner_constraints
            }.values()
        )
        warnings = list(
            dict.fromkeys(
                [
                    *places.warnings,
                    *items.warnings,
                    *(retrieval.warnings if retrieval else []),
                    *(extra_warnings or []),
                    *(food_selection.warnings if food_selection else []),
                    *(style_selection.warnings if style_selection else []),
                    *(warning for place in checked for warning in place.warnings),
                ]
            )
        )
        blocked_mandatory = any(
            evaluation.place.mandatory
            and evaluation.state == PlaceLifecycleState.blocked
            for evaluation in places.places
        )
        if (
            context.destination.status != AdmResolutionStatus.resolved
            or blocked_mandatory
        ):
            status = PlaceCheckerStatus.blocked
        elif metadata.partial:
            status = PlaceCheckerStatus.partial
        elif analysis.gaps.open_count or unresolved or warnings:
            status = PlaceCheckerStatus.conditional
        else:
            status = PlaceCheckerStatus.completed
        specials = [
            item.special_experience
            for item in items.items
            if item.special_experience is not None
        ]
        return PlaceCheckerResult(
            status=status,
            trip_context=context,
            checked_places=checked,
            planner_eligible_place_ids=list(dict.fromkeys(eligible_ids)),
            resolved_items=items.items,
            special_experiences=specials,
            food_restaurant_selections=(
                food_selection.selections if food_selection else []
            ),
            food_meal_coverage=(
                food_selection.meal_coverage
                if food_selection
                else FoodMealCoverage(days=context.days)
            ),
            food_style_coverage=(
                food_selection.style_coverage if food_selection else []
            ),
            style_candidate_selections=(
                style_selection.selections if style_selection else []
            ),
            style_candidate_coverage=(
                style_selection.coverage if style_selection else []
            ),
            unresolved_style_inputs=(
                style_selection.unresolved_style_inputs if style_selection else []
            ),
            unresolved_item_style_inputs=(
                style_selection.unresolved_item_inputs if style_selection else []
            ),
            budget_analysis=analysis.budget,
            capacity_analysis=analysis.capacity,
            coverage_analysis=analysis.coverage,
            geographic_analysis=GeographicAnalysis(
                known_coordinate_count=(
                    analysis.capacity.geographic_overhead.known_coordinate_count
                ),
                unknown_coordinate_count=(
                    analysis.capacity.geographic_overhead.unknown_coordinate_count
                ),
                spread=analysis.capacity.geographic_overhead.spread.value,
                radius_km=analysis.capacity.geographic_overhead.radius_km,
                coarse_overhead_minutes=(
                    analysis.capacity.geographic_overhead.estimated_minutes
                ),
            ),
            gap_analysis=analysis.gaps,
            retrieval=retrieval,
            ranking=ranking,
            unresolved_entities=unresolved,
            planner_constraints=constraints,
            warnings=warnings,
            metadata=metadata,
        )

    @staticmethod
    def _checked(
        evaluation,
        verification: dict[str, VerificationStatus],
        ranking: dict[str, ScoredCandidate],
    ) -> CheckedPlace:
        place = evaluation.place
        metadata = place.metadata
        place_id = place.place_id
        status = verification.get(
            place_id or "",
            (
                VerificationStatus.verified_kg
                if place.status == IdentityResolutionStatus.resolved
                else VerificationStatus.provisional
                if place.status == IdentityResolutionStatus.provisional
                else VerificationStatus.needs_review
                if place.status == IdentityResolutionStatus.needs_review
                else VerificationStatus.unresolved
            ),
        )
        scored = ranking.get(place_id or "")
        time_preferences = list(
            dict.fromkeys(
                source.source_time_hint
                for source in place.source_places
                if source.source_time_hint
            )
        )
        known_duration = bool(
            metadata and metadata.typical_duration_minutes is not None
        )
        known_cost = bool(
            metadata
            and (
                metadata.cost_tier.value != "unknown"
                or metadata.typical_cost is not None
            )
        )
        known_opening = bool(metadata and metadata.opening_hours is not None)
        selected_option = next(
            (
                option
                for option in place.match_options
                if option.place.place_id == place_id
            ),
            None,
        )
        return CheckedPlace(
            place_id=place_id,
            canonical_name=place.canonical_name,
            original_names=place.original_names,
            aliases=place.aliases,
            address=metadata.address if metadata else None,
            coordinates=metadata.coordinates if metadata else None,
            destination=CheckedDestination(
                adm_id=selected_option.place.adm_id if selected_option else None,
                compatible=evaluation.destination_compatible,
            ),
            source_tier=place.source_tier,
            mandatory=place.mandatory,
            removable=place.removable,
            category=metadata.category if metadata else None,
            pool_category=scored.candidate.pool_category if scored else None,
            tags=metadata.tags if metadata else [],
            image_urls=metadata.image_urls if metadata else [],
            rating=metadata.rating if metadata else None,
            review_count=metadata.review_count if metadata else None,
            provider_note=metadata.source_note if metadata else None,
            duration=CheckedDuration(
                minimum_minutes=metadata.minimum_duration_minutes if metadata else None,
                typical_minutes=metadata.typical_duration_minutes if metadata else None,
                maximum_minutes=metadata.maximum_duration_minutes if metadata else None,
                known=known_duration,
            ),
            cost=CheckedCost(
                tier=metadata.cost_tier if metadata else "unknown",
                currency=metadata.cost_currency if metadata else None,
                minimum=metadata.minimum_cost if metadata else None,
                typical=metadata.typical_cost if metadata else None,
                maximum=metadata.maximum_cost if metadata else None,
                known=known_cost,
            ),
            opening=CheckedOpening(
                hours=metadata.opening_hours if metadata else None,
                operational_status=(
                    metadata.operational_status if metadata else "unknown"
                ),
                reservation_required=(
                    metadata.reservation_required if metadata else None
                ),
                known=known_opening,
            ),
            time_preferences=time_preferences,
            suitability=CheckedSuitability(
                adults=evaluation.people_suitability.adults,
                children=evaluation.people_suitability.children,
                infants=evaluation.people_suitability.infants,
                accessibility=evaluation.people_suitability.accessibility,
            ),
            verification=CheckedVerification(
                status=status,
                identity_confidence=place.identity_confidence,
                provider=metadata.source if metadata else None,
                fetched_at=metadata.fetched_at if metadata else None,
            ),
            evaluation=CheckedEvaluation(
                state=evaluation.state,
                planner_eligible=evaluation.planner_eligible,
                preference_matches=evaluation.preference_matches,
                avoid_conflicts=evaluation.avoid_conflicts,
                findings=evaluation.findings,
                planner_constraints=evaluation.planner_constraints,
                data_quality=evaluation.data_quality,
            ),
            ranking=CheckedRanking(
                score=scored.final_score if scored else None,
                reasons=(
                    [*scored.penalties.keys(), *scored.rerank_reasons]
                    if scored
                    else ["mandatory_place_not_removed_by_ranking"]
                    if place.mandatory
                    else []
                ),
            ),
            distance_from_anchor_km=(
                scored.distance_from_anchor_km if scored else None
            ),
            relationship_score=(
                scored.candidate.relationship_score
                if scored
                else max(
                    (relationship.score for relationship in metadata.relationships),
                    default=0,
                )
                if metadata
                else 0
            ),
            relationship_evidence=(
                scored.candidate.relationships
                if scored
                else metadata.relationships
                if metadata
                else []
            ),
            provenance=CheckedProvenance(
                source_places=place.source_places,
                url_notes=place.url_notes,
            ),
            warnings=evaluation.warnings,
            internal_evaluation=evaluation,
        )

    @staticmethod
    def _unresolved(
        context: TripEvaluationContext,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        validation_issues: list[CandidateValidationIssue],
    ) -> list[UnresolvedEntity]:
        result: list[UnresolvedEntity] = []
        if context.destination.status != AdmResolutionStatus.resolved:
            result.append(
                UnresolvedEntity(
                    entity_type=UnresolvedEntityType.adm,
                    input_name=context.destination.input_name,
                    reason=f"destination_{context.destination.status.value}",
                    mandatory=True,
                )
            )
        for index, evaluation in enumerate(places.places):
            if evaluation.place.status in {
                IdentityResolutionStatus.resolved,
                IdentityResolutionStatus.provisional,
            }:
                continue
            result.append(
                UnresolvedEntity(
                    entity_type=UnresolvedEntityType.place,
                    input_index=index,
                    input_name=(evaluation.place.original_names or [None])[0],
                    reason="identity_not_resolved",
                    mandatory=evaluation.place.mandatory,
                )
            )
        for item in items.items:
            if item.status == ItemResolutionStatus.resolved:
                continue
            result.append(
                UnresolvedEntity(
                    entity_type=UnresolvedEntityType.item,
                    input_index=item.item_index,
                    input_name=item.item.name,
                    reason=f"item_{item.status.value}",
                )
            )
        result.extend(
            UnresolvedEntity(
                entity_type=UnresolvedEntityType.validation,
                input_index=issue.index,
                input_name=issue.name,
                reason=issue.code,
            )
            for issue in validation_issues
        )
        return result

    @staticmethod
    def _planner_verification_allowed(place: CheckedPlace) -> bool:
        if place.verification.status in {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        }:
            return True
        return (
            place.verification.status == VerificationStatus.provisional
            and place.source_tier in {SourceTier.direct_user, SourceTier.url}
        )
