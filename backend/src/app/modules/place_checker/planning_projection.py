from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import (
    PlaceLifecycleState,
    SourceTier,
    VerificationStatus,
)
from app.modules.place_checker.output_contract import (
    PlaceCheckerPlanningProjection,
    PlaceCheckerResult,
    PlannerPlaceContext,
)
from app.modules.place_checker.price_policy import has_usable_cost, typical_cost


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
            if not evaluation.planner_eligible or not self._verification_allowed(
                checked
            ):
                continue
            metadata = evaluation.place.metadata
            if not checked.place_id or not checked.canonical_name or metadata is None:
                warnings.append("Bỏ qua place thiếu canonical identity hoặc metadata.")
                continue
            if metadata.coordinates is None or not evaluation.place.source_places:
                warnings.append(
                    f"Bỏ qua {checked.canonical_name} do thiếu tọa độ/provenance."
                )
                continue
            if not has_usable_cost(
                minimum=metadata.minimum_cost,
                typical=metadata.typical_cost,
                maximum=metadata.maximum_cost,
                tier=metadata.cost_tier,
            ):
                warnings.append(f"Bỏ qua {checked.canonical_name} do thiếu giá.")
                continue
            places.append(self._place(checked, evaluation, metadata))
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

    @staticmethod
    def _place(checked, evaluation, metadata) -> PlannerPlaceContext:
        return PlannerPlaceContext(
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
            image_urls=metadata.image_urls,
            rating=checked.rating,
            review_count=checked.review_count,
            distance_from_anchor_km=checked.distance_from_anchor_km,
            relationship_score=checked.relationship_score,
            relationships=PlaceCheckerPlanningProjector._related_place_ids(checked),
            minimum_duration_minutes=metadata.minimum_duration_minutes,
            typical_duration_minutes=metadata.typical_duration_minutes,
            maximum_duration_minutes=metadata.maximum_duration_minutes,
            cost_tier=metadata.cost_tier,
            minimum_cost=metadata.minimum_cost,
            typical_cost=typical_cost(
                minimum=metadata.minimum_cost,
                typical=metadata.typical_cost,
                maximum=metadata.maximum_cost,
                tier=metadata.cost_tier,
            ),
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

    @staticmethod
    def _related_place_ids(checked: CheckedPlace) -> list[str]:
        return list(
            dict.fromkeys(
                relation.related_entity_id
                for relation in checked.relationship_evidence
                if relation.direction == "place_to_place" and relation.related_entity_id
            )
        )

    @staticmethod
    def _verification_allowed(checked: CheckedPlace) -> bool:
        if checked.verification.status in {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        }:
            return True
        return (
            checked.verification.status == VerificationStatus.provisional
            and checked.source_tier in {SourceTier.direct_user, SourceTier.url}
        )
