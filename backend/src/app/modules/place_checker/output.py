from app.modules.place_checker.analysis_contract import TripAggregateAnalysis
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
    UnresolvedEntityType,
    VerificationStatus,
)
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.item_contract import ItemResolutionBatch
from app.modules.place_checker.output_contract import (
    CheckedPlace,
    PlaceCheckerExecutionMetadata,
    PlaceCheckerPlannerOutput,
    PlaceCheckerPlanningProjection,
    PlaceCheckerResult,
    PlannerOutputPlace,
    PlannerPlaceContext,
    PlannerOutputTrip,
    PlannerBudget,
    PlannerPrice,
    UnresolvedEntity,
)
from app.modules.place_checker.retrieval_contract import RetrievalBatch
from app.modules.place_checker.scoring_contract import CandidateRankingBatch, ScoredCandidate


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
            and place.verification.status
            in {
                VerificationStatus.verified_kg,
                VerificationStatus.verified_external,
            }
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
                    *(warning for place in checked for warning in place.warnings),
                ]
            )
        )
        blocked_mandatory = any(
            evaluation.place.mandatory
            and evaluation.state == PlaceLifecycleState.blocked
            for evaluation in places.places
        )
        if context.destination.status != AdmResolutionStatus.resolved or blocked_mandatory:
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
        known_duration = bool(metadata and metadata.typical_duration_minutes is not None)
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
            rating=metadata.rating if metadata else None,
            review_count=metadata.review_count if metadata else None,
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
            relationship_score=scored.candidate.relationship_score if scored else 0,
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
            if evaluation.place.status == IdentityResolutionStatus.resolved:
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


class PlaceCheckerPlanningProjector:
    def project(self, result: PlaceCheckerResult) -> PlaceCheckerPlanningProjection:
        places: list[PlannerPlaceContext] = []
        blocked: list[str] = []
        warnings = list(result.warnings)
        for checked in result.checked_places:
            evaluation = checked.internal_evaluation
            if evaluation is None:
                warnings.append(
                    f"Bỏ qua {checked.canonical_name or 'place'} do thiếu internal evaluation."
                )
                continue
            if checked.mandatory and evaluation.state == PlaceLifecycleState.blocked:
                if checked.place_id:
                    blocked.append(checked.place_id)
                continue
            if not evaluation.planner_eligible:
                continue
            if checked.verification.status not in {
                VerificationStatus.verified_kg,
                VerificationStatus.verified_external,
            }:
                continue
            metadata = evaluation.place.metadata
            if not checked.place_id or not checked.canonical_name or metadata is None:
                warnings.append("Bỏ qua place thiếu canonical identity hoặc metadata.")
                continue
            if metadata.coordinates is None or not evaluation.place.source_places:
                warnings.append(f"Bỏ qua {checked.canonical_name} do thiếu tọa độ/provenance.")
                continue
            places.append(
                PlannerPlaceContext(
                    place_id=checked.place_id,
                    canonical_name=checked.canonical_name,
                    coordinates=metadata.coordinates,
                    address=checked.address,
                    state=evaluation.state,
                    source_tier=checked.source_tier,
                    mandatory=checked.mandatory,
                    removable=checked.removable,
                    category=metadata.category,
                    pool_category=checked.pool_category,
                    tags=metadata.tags,
                    rating=checked.rating,
                    review_count=checked.review_count,
                    distance_from_anchor_km=checked.distance_from_anchor_km,
                    relationship_score=checked.relationship_score,
                    minimum_duration_minutes=metadata.minimum_duration_minutes,
                    typical_duration_minutes=metadata.typical_duration_minutes,
                    maximum_duration_minutes=metadata.maximum_duration_minutes,
                    cost_tier=metadata.cost_tier,
                    minimum_cost=metadata.minimum_cost,
                    typical_cost=metadata.typical_cost,
                    maximum_cost=metadata.maximum_cost,
                    currency=metadata.cost_currency,
                    opening_hours=metadata.opening_hours,
                    operational_status=metadata.operational_status,
                    reservation_required=metadata.reservation_required,
                    time_preferences=checked.time_preferences,
                    adults_suitable=checked.suitability.adults,
                    children_suitable=checked.suitability.children,
                    infants_suitable=checked.suitability.infants,
                    accessibility=checked.suitability.accessibility,
                    verification_status=checked.verification.status,
                    identity_confidence=checked.verification.identity_confidence,
                    score=checked.ranking.score,
                    constraints=evaluation.planner_constraints,
                    provenance=evaluation.place.source_places,
                    warnings=checked.warnings,
                )
            )
        destination_id = result.trip_context.destination.adm_id or "unresolved"
        return PlaceCheckerPlanningProjection(
            destination_adm_id=destination_id,
            places=places,
            resolved_items=result.resolved_items,
            special_experiences=result.special_experiences,
            blocked_mandatory_place_ids=blocked,
            warnings=list(dict.fromkeys(warnings)),
            metadata={
                "place_checker_request_id": result.metadata.request_id,
                "place_checker_schema_version": result.metadata.schema_version,
            },
        )


class PlaceCheckerPlannerOutputBuilder:
    """Build the compact JSON contract consumed by the final planner."""

    def build(
        self,
        result: PlaceCheckerResult,
        *,
        start_date: str | None = None,
    ) -> PlaceCheckerPlannerOutput:
        places: list[PlannerOutputPlace] = []
        food: list[PlannerOutputPlace] = []
        for checked in result.checked_places:
            if not checked.canonical_name:
                continue
            compact = self._place(checked)
            if checked.category in {"restaurant", "drink_dessert"}:
                food.append(compact)
            else:
                places.append(compact)

        budget = result.trip_context.budget
        return PlaceCheckerPlannerOutput(
            trip=PlannerOutputTrip(
                destination=(
                    result.trip_context.destination.canonical_name
                    or result.trip_context.destination.input_name
                ),
                days=result.trip_context.days,
                start_date=start_date,
                people=result.trip_context.people.total,
                budget=PlannerBudget(
                    amount=budget.target_amount,
                    currency=budget.currency or "VND",
                ),
                preferences=result.trip_context.preferences,
                avoids=result.trip_context.avoids,
            ),
            places=places,
            food=food,
        )

    @classmethod
    def _place(cls, checked: CheckedPlace) -> PlannerOutputPlace:
        relationships = [
            tag.split(":", 1)[1]
            for tag in checked.tags
            if tag.startswith(("relation:", "experience:", "item:"))
        ]
        notes = next(
            (
                source.evidence
                for source in checked.provenance.source_places
                if source.evidence
            ),
            None,
        )
        priority = "user_input" if checked.mandatory else None
        if not priority and any(
            tag.startswith(("relation:", "experience:")) for tag in checked.tags
        ):
            priority = "special_experience"
        return PlannerOutputPlace(
            place_id=checked.place_id,
            name=checked.canonical_name or "",
            coordinates=checked.coordinates,
            address=checked.address,
            priority=priority,
            notes=notes,
            tags=checked.tags,
            rating=checked.rating,
            review_count=checked.review_count,
            duration_minutes=checked.duration.typical_minutes,
            opening_hours=checked.opening.hours,
            preferred_time_windows=checked.time_preferences,
            price=cls._price(checked),
            relationships=list(dict.fromkeys(relationships)),
        )

    @staticmethod
    def _price(checked: CheckedPlace) -> PlannerPrice:
        minimum = checked.cost.minimum
        maximum = checked.cost.maximum
        if minimum is not None and maximum is not None:
            cost = (minimum + maximum) / 2
        elif checked.cost.typical is not None:
            cost = checked.cost.typical
        elif checked.cost.tier.value == "free":
            cost = 0
            minimum = minimum if minimum is not None else 0
            maximum = maximum if maximum is not None else 0
        else:
            cost = None
        return PlannerPrice(
            cost=cost,
            minimum=minimum,
            maximum=maximum,
            currency=checked.cost.currency or "VND",
            basis="perPerson",
        )
