"""Experience fit evaluation tool for Knowledge Graph.

Evaluates whether an entity or experience fits a user's trip context
by checking multiple dimensions with evidence-based reasoning.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.modules.knowledge_graph.research.repository import (
    ScopeResolutionRepository,
)
from app.modules.knowledge_graph.research.experience_tool import (
    kg_discover_experiences,
)
from app.modules.knowledge_graph.research.schema import (
    BudgetLevel,
    CheckStatus,
    DimensionCheck,
    EntitySummaryFit,
    ExperienceFitInput,
    ExperienceFitOutput,
    ExperienceDiscoveryInput,
    TransportMode,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Hard constraints that cause overall conflicted if violated
# ---------------------------------------------------------------------------

HARD_CONSTRAINTS = frozenset({
    "excluded_type",
    "geographic_scope",
    "opening_hours",
    "booking_required",
})


# ---------------------------------------------------------------------------
# Provenance classification
# ---------------------------------------------------------------------------

def _is_verified_source(source: str | None) -> bool:
    """Check if a source is considered verified/trusted.

    Verified sources are authoritative data providers (official websites,
    government sources, booking platforms). AI-generated content or
    unverified scraped data are not considered verified.

    Inference/AI-generated claims are NEVER treated as verified.
    """
    if source is None:
        return False

    source_lower = source.lower()

    verified_prefixes = (
        "official:",
        "https://",
        "http://",
        "booking.com",
        "agoda",
        "tripadvisor",
        "google",
        "viettravel",
        "vietnamtourism",
        "wikipedia",
        "wikidata",
    )

    for prefix in verified_prefixes:
        if source_lower.startswith(prefix):
            return True

    return False


# ---------------------------------------------------------------------------
# Dimension evaluators
# ---------------------------------------------------------------------------

def _check_geographic_scope(
    repo: ScopeResolutionRepository,
    entity_id: str,
    destination: str,
) -> DimensionCheck:
    """Check if entity is within the geographic scope of the destination."""
    scope_ids = repo.get_scope_area_ids_for_destination(destination)
    if not scope_ids:
        return DimensionCheck(
            dimension="geographic_scope",
            status=CheckStatus.UNKNOWN,
            reason="Cannot resolve destination to a known area in the knowledge graph.",
            evidenceClaimIds=[],
            sources=[],
        )

    in_scope = repo.is_entity_in_scope(entity_id, scope_ids)
    if in_scope:
        prop_value, prop_source = repo.get_entity_property_with_source(
            entity_id, "latitude"
        )
        sources = [prop_source] if prop_source else []
        return DimensionCheck(
            dimension="geographic_scope",
            status=CheckStatus.SUPPORTED,
            reason="Entity is located within the resolved geographic scope.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )
    else:
        return DimensionCheck(
            dimension="geographic_scope",
            status=CheckStatus.CONFLICTED,
            reason="Entity is located outside the geographic scope of the destination.",
            evidenceClaimIds=[],
            sources=[],
        )


def _check_excluded_type(
    repo: ScopeResolutionRepository,
    entity_id: str,
    excluded_types: list[str],
) -> DimensionCheck:
    """Check if entity type is in the excluded list."""
    if not excluded_types:
        return DimensionCheck(
            dimension="excluded_type",
            status=CheckStatus.SUPPORTED,
            reason="No entity type exclusion constraints specified.",
            evidenceClaimIds=[],
            sources=[],
        )

    entity = repo.get_entity_by_id(entity_id)
    if entity is None:
        return DimensionCheck(
            dimension="excluded_type",
            status=CheckStatus.UNKNOWN,
            reason="Entity not found.",
            evidenceClaimIds=[],
            sources=[],
        )

    if entity.entity_type in excluded_types:
        return DimensionCheck(
            dimension="excluded_type",
            status=CheckStatus.CONFLICTED,
            reason=f"Entity type '{entity.entity_type}' is explicitly excluded.",
            evidenceClaimIds=[],
            sources=[],
        )

    return DimensionCheck(
        dimension="excluded_type",
        status=CheckStatus.SUPPORTED,
        reason=f"Entity type '{entity.entity_type}' is not in excluded list.",
        evidenceClaimIds=[],
        sources=[],
    )


def _check_opening_hours(
    repo: ScopeResolutionRepository,
    entity_id: str,
) -> DimensionCheck:
    """Check if opening hours are known and consistent with trip duration."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "opening_hours"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="opening_hours",
            status=CheckStatus.UNKNOWN,
            reason="No verified opening-hours data for this entity.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []
    verified = _is_verified_source(prop_source)

    if not verified:
        return DimensionCheck(
            dimension="opening_hours",
            status=CheckStatus.UNKNOWN,
            reason="Opening hours data exists but source is not verified. "
            "Inference is not treated as verified data.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )

    return DimensionCheck(
        dimension="opening_hours",
        status=CheckStatus.SUPPORTED,
        reason=f"Verified opening hours: {prop_value}",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_typical_duration(
    repo: ScopeResolutionRepository,
    entity_id: str,
    days: int,
) -> DimensionCheck:
    """Check if typical duration fits within the trip length."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "typical_duration_minutes"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="typical_duration",
            status=CheckStatus.UNKNOWN,
            reason="No typical duration data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    try:
        duration_minutes = int(float(prop_value))
    except ValueError:
        return DimensionCheck(
            dimension="typical_duration",
            status=CheckStatus.UNKNOWN,
            reason=f"Typical duration value '{prop_value}' is not parseable.",
            evidenceClaimIds=[],
            sources=[prop_source] if prop_source else [],
        )

    duration_hours = duration_minutes / 60.0
    max_sensible_hours = days * 8

    sources = [prop_source] if prop_source else []

    if duration_hours <= max_sensible_hours:
        return DimensionCheck(
            dimension="typical_duration",
            status=CheckStatus.SUPPORTED,
            reason=f"Typical duration {duration_minutes} min (~{duration_hours:.1f}h) fits within {days}-day trip.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )
    else:
        return DimensionCheck(
            dimension="typical_duration",
            status=CheckStatus.CONFLICTED,
            reason=f"Typical duration {duration_minutes} min (~{duration_hours:.1f}h) exceeds what is sensible for a {days}-day trip.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )


def _check_time_slot(
    repo: ScopeResolutionRepository,
    entity_id: str,
) -> DimensionCheck:
    """Check if best time slots are known."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "best_time_slots"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="time_slot",
            status=CheckStatus.UNKNOWN,
            reason="No best-time-slots data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []
    return DimensionCheck(
        dimension="time_slot",
        status=CheckStatus.SUPPORTED,
        reason=f"Best time slots recorded: {prop_value}",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_booking_required(
    repo: ScopeResolutionRepository,
    entity_id: str,
) -> DimensionCheck:
    """Check booking requirements and issue warning if booking is required."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "booking_required"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="booking_required",
            status=CheckStatus.UNKNOWN,
            reason="No booking requirement data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    booking_required = prop_value.lower() in ("true", "1", "yes", "required")
    sources = [prop_source] if prop_source else []

    if booking_required:
        booking_url, url_source = repo.get_entity_property_with_source(
            entity_id, "booking_url"
        )
        if booking_url:
            sources.extend([url_source] if url_source else [])
            return DimensionCheck(
                dimension="booking_required",
                status=CheckStatus.SUPPORTED,
                reason="Booking is required and booking URL is available.",
                evidenceClaimIds=[],
                sources=[s for s in sources if s],
            )
        else:
            return DimensionCheck(
                dimension="booking_required",
                status=CheckStatus.CONFLICTED,
                reason="Booking is required but no booking URL is recorded.",
                evidenceClaimIds=[],
                sources=[s for s in sources if s],
            )
    else:
        return DimensionCheck(
            dimension="booking_required",
            status=CheckStatus.SUPPORTED,
            reason="No booking required.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )


def _check_admission_fee(
    repo: ScopeResolutionRepository,
    entity_id: str,
    budget_level: BudgetLevel | None,
    budget_target: float | None,
) -> DimensionCheck:
    """Check admission fee against budget constraints."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "admission_price"
    )

    if prop_value is not None:
        try:
            admission_price = json.loads(prop_value)
            if admission_price.get("currency") == "VND":
                amount = next(
                    (
                        admission_price.get(key)
                        for key in (
                            "representativeAmount",
                            "maxAmount",
                            "minAmount",
                        )
                        if admission_price.get(key) is not None
                    ),
                    None,
                )
                prop_value = str(amount) if amount is not None else None
            else:
                prop_value = None
        except (json.JSONDecodeError, AttributeError, TypeError):
            prop_value = None

    if prop_value is None:
        prop_value, prop_source = repo.get_entity_property_with_source(
            entity_id, "price_level"
        )

    if prop_value is None:
        prop_value, prop_source = repo.get_entity_property_with_source(
            entity_id, "price_range_vnd"
        )

    if prop_value is None:
        return DimensionCheck(
            dimension="admission_fee",
            status=CheckStatus.UNKNOWN,
            reason="No price or admission fee data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []

    if budget_target is not None:
        try:
            fee = float(prop_value.replace(",", "").replace(" ", ""))
            if fee <= budget_target:
                return DimensionCheck(
                    dimension="admission_fee",
                    status=CheckStatus.SUPPORTED,
                    reason=f"Admission fee {fee:,.0f} VND is within target budget {budget_target:,.0f} VND.",
                    evidenceClaimIds=[],
                    sources=[s for s in sources if s],
                )
            else:
                return DimensionCheck(
                    dimension="admission_fee",
                    status=CheckStatus.CONFLICTED,
                    reason=f"Admission fee {fee:,.0f} VND exceeds target budget {budget_target:,.0f} VND.",
                    evidenceClaimIds=[],
                    sources=[s for s in sources if s],
                )
        except ValueError:
            pass

    if budget_level is not None:
        level_map = {
            BudgetLevel.LOW: (0, 100000),
            BudgetLevel.MEDIUM: (100000, 500000),
            BudgetLevel.HIGH: (500000, 2000000),
            BudgetLevel.LUXURY: (2000000, float("inf")),
        }
        low, high = level_map.get(budget_level, (0, float("inf")))

        try:
            fee = float(prop_value.replace(",", "").replace(" ", ""))
            if low <= fee <= high:
                return DimensionCheck(
                    dimension="admission_fee",
                    status=CheckStatus.SUPPORTED,
                    reason=f"Fee {fee:,.0f} VND is within {budget_level.value} budget range.",
                    evidenceClaimIds=[],
                    sources=[s for s in sources if s],
                )
            else:
                return DimensionCheck(
                    dimension="admission_fee",
                    status=CheckStatus.CONFLICTED,
                    reason=f"Fee {fee:,.0f} VND is outside {budget_level.value} budget range ({low:,.0f}-{high:,.0f} VND).",
                    evidenceClaimIds=[],
                    sources=[s for s in sources if s],
                )
        except ValueError:
            pass

    return DimensionCheck(
        dimension="admission_fee",
        status=CheckStatus.SUPPORTED,
        reason=f"Price data available: {prop_value}",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_accessibility(
    repo: ScopeResolutionRepository,
    entity_id: str,
    requirements: list[str],
) -> DimensionCheck:
    """Check accessibility features against user requirements."""
    if not requirements:
        return DimensionCheck(
            dimension="accessibility",
            status=CheckStatus.SUPPORTED,
            reason="No accessibility requirements specified.",
            evidenceClaimIds=[],
            sources=[],
        )

    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "accessibility_features"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="accessibility",
            status=CheckStatus.UNKNOWN,
            reason="No accessibility features data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    available_features = {f.strip().lower() for f in prop_value.split(",")}
    missing: list[str] = []

    for req in requirements:
        req_lower = req.lower()
        found = False
        for feature in available_features:
            if req_lower in feature or feature in req_lower:
                found = True
                break
        if not found:
            missing.append(req)

    sources = [prop_source] if prop_source else []

    if missing:
        return DimensionCheck(
            dimension="accessibility",
            status=CheckStatus.CONFLICTED,
            reason=f"Missing required accessibility features: {', '.join(missing)}.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )

    return DimensionCheck(
        dimension="accessibility",
        status=CheckStatus.SUPPORTED,
        reason="All required accessibility features are available.",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_suitable_for(
    repo: ScopeResolutionRepository,
    entity_id: str,
    party_size: int,
) -> DimensionCheck:
    """Check if entity is suitable for the party size."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "suitable_for"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="suitable_for",
            status=CheckStatus.UNKNOWN,
            reason="No suitability data for group size.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []

    prop_lower = prop_value.lower()
    suitable = True
    reason_suffix = ""

    if party_size == 1 and "solo" not in prop_lower and "individual" not in prop_lower:
        suitable = False
        reason_suffix = " May not be suitable for solo travelers."

    if party_size > 4 and "group" not in prop_lower and "large" not in prop_lower:
        suitable = False
        reason_suffix = " May not accommodate large groups well."

    if suitable:
        return DimensionCheck(
            dimension="suitable_for",
            status=CheckStatus.SUPPORTED,
            reason=f"Suitable for party size {party_size}. Data: {prop_value}.",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )
    else:
        return DimensionCheck(
            dimension="suitable_for",
            status=CheckStatus.CONFLICTED,
            reason=f"Party size {party_size} may not match suitability data: {prop_value}.{reason_suffix}",
            evidenceClaimIds=[],
            sources=[s for s in sources if s],
        )


def _check_requirements(
    repo: ScopeResolutionRepository,
    entity_id: str,
    user_constraints: list[str],
) -> DimensionCheck:
    """Check general requirements and user constraints."""
    if not user_constraints:
        return DimensionCheck(
            dimension="requirements",
            status=CheckStatus.SUPPORTED,
            reason="No additional user constraints specified.",
            evidenceClaimIds=[],
            sources=[],
        )

    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "requirements"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="requirements",
            status=CheckStatus.UNKNOWN,
            reason="No requirements data to cross-check against constraints.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []
    return DimensionCheck(
        dimension="requirements",
        status=CheckStatus.SUPPORTED,
        reason=f"Requirements data available: {prop_value}. User constraints: {', '.join(user_constraints)}.",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_weather_constraints(
    repo: ScopeResolutionRepository,
    entity_id: str,
    start_date: str | None,
    end_date: str | None,
) -> DimensionCheck:
    """Check weather constraints against trip dates."""
    prop_value, prop_source = repo.get_entity_property_with_source(
        entity_id, "weather_constraints"
    )

    if prop_value is None:
        return DimensionCheck(
            dimension="weather_constraints",
            status=CheckStatus.UNKNOWN,
            reason="No weather constraint data available.",
            evidenceClaimIds=[],
            sources=[],
        )

    sources = [prop_source] if prop_source else []
    return DimensionCheck(
        dimension="weather_constraints",
        status=CheckStatus.SUPPORTED,
        reason=f"Weather constraints recorded: {prop_value}",
        evidenceClaimIds=[],
        sources=[s for s in sources if s],
    )


def _check_provenance_trust(
    repo: ScopeResolutionRepository,
    entity_id: str,
) -> DimensionCheck:
    """Check the provenance and trust level of entity data."""
    entity = repo.get_entity_by_id(entity_id)
    if entity is None:
        return DimensionCheck(
            dimension="provenance_trust",
            status=CheckStatus.UNKNOWN,
            reason="Entity not found.",
            evidenceClaimIds=[],
            sources=[],
        )

    props = repo.get_all_properties_with_sources(entity_id)
    sources: set[str] = set()

    for _, _, source in props:
        if source:
            sources.add(source)

    verified_count = sum(1 for s in sources if _is_verified_source(s))
    total_count = len(sources)

    if total_count == 0:
        return DimensionCheck(
            dimension="provenance_trust",
            status=CheckStatus.UNKNOWN,
            reason="No source provenance recorded for any property.",
            evidenceClaimIds=[],
            sources=[],
        )

    if verified_count == total_count:
        return DimensionCheck(
            dimension="provenance_trust",
            status=CheckStatus.SUPPORTED,
            reason=f"All {total_count} sources are verified.",
            evidenceClaimIds=[],
            sources=list(sources),
        )
    elif verified_count > 0:
        return DimensionCheck(
            dimension="provenance_trust",
            status=CheckStatus.SUPPORTED,
            reason=f"{verified_count}/{total_count} sources are verified. Some data may be AI-inferred.",
            evidenceClaimIds=[],
            sources=list(sources),
        )
    else:
        return DimensionCheck(
            dimension="provenance_trust",
            status=CheckStatus.UNKNOWN,
            reason="No verified sources found. All data may be AI-inferred.",
            evidenceClaimIds=[],
            sources=list(sources),
        )


# ---------------------------------------------------------------------------
# Overall status computation
# ---------------------------------------------------------------------------

def _compute_overall_status(checks: list[DimensionCheck]) -> CheckStatus:
    """Compute overall status from dimension checks.

    Rules:
    - Any hard constraint conflicted -> overall conflicted
    - No conflicts but any critical unknown -> overall unknown
    - Only supported when every hard requirement has verified evidence
    """
    hard_conflict = False
    critical_unknown = False

    for check in checks:
        if check.dimension in HARD_CONSTRAINTS:
            if check.status == CheckStatus.CONFLICTED:
                hard_conflict = True
            elif check.status == CheckStatus.UNKNOWN:
                critical_unknown = True

    if hard_conflict:
        return CheckStatus.CONFLICTED
    if critical_unknown:
        return CheckStatus.UNKNOWN
    return CheckStatus.SUPPORTED


# ---------------------------------------------------------------------------
# Main tool entry point
# ---------------------------------------------------------------------------


class EntityNotFoundError(ValueError):
    """Raised when the target entity cannot be found."""

    pass


def _resolve_claim_target(
    repo: ScopeResolutionRepository,
    claim_id: str,
    destination: str,
) -> tuple[str, str | None] | None:
    """Resolve a virtual discovery claim to its activity and scope anchor.

    Discovery claim IDs are deterministic projections, not persisted entities.
    The activity owns fit metadata while the anchor Place (or claim subject)
    provides the geographic location for an Activity that is not LOCATED_IN.
    """
    bundle = kg_discover_experiences(
        repo,
        ExperienceDiscoveryInput(
            destination=destination,
            limit=50,
            includeInferred=True,
        ),
    )
    claim = next((item for item in bundle.claims if item.claimId == claim_id), None)
    if claim is None:
        return None

    target_id = (claim.activity or claim.object).id
    scope_entity_id = claim.subject.id
    if claim.anchorPlace is not None:
        scope_ids = repo.get_scope_area_ids_for_destination(destination)
        if scope_ids and repo.is_entity_in_scope(claim.anchorPlace.id, scope_ids):
            scope_entity_id = claim.anchorPlace.id
    return target_id, scope_entity_id


def kg_evaluate_experience_fit(
    repo: ScopeResolutionRepository,
    input_data: ExperienceFitInput,
) -> ExperienceFitOutput:
    """Evaluate whether an entity fits a user's trip context.

    Args:
        repo: The scope resolution repository (read-only)
        input_data: Input containing entity/claim ID and trip parameters

    Returns:
        ExperienceFitOutput with per-dimension checks and overall status

    Raises:
        EntityNotFoundError: If neither entityId nor claimId resolves to an entity

    Behavior:
        - Requires exactly one of entityId or claimId
        - Evaluates geographic scope against destination hierarchy
        - Checks entity type against exclusion list
        - Verifies opening hours, booking, fees, accessibility data
        - Missing data maps to 'unknown', never to 'supported'
        - Inference/AI sources are not treated as verified
        - Hard constraints (excluded_type, geographic_scope) cause
          overall 'conflicted' if violated
        - Deterministic output ordering
    """
    entity_id: str | None = None
    geographic_scope_entity_id: str | None = None

    if input_data.entityId is not None and input_data.claimId is not None:
        raise ValueError("Provide either entityId or claimId, not both.")

    if input_data.entityId is not None:
        entity_id = input_data.entityId
    elif input_data.claimId is not None:
        # Keep compatibility with older callers that used an entity ID in
        # claimId, then resolve current virtual discovery claims when needed.
        if repo.get_entity_by_id(input_data.claimId) is not None:
            entity_id = input_data.claimId
        else:
            resolved = _resolve_claim_target(
                repo,
                input_data.claimId,
                input_data.destination,
            )
            if resolved is not None:
                entity_id, geographic_scope_entity_id = resolved
            else:
                entity_id = input_data.claimId
    else:
        raise ValueError("Must provide either entityId or claimId.")

    entity = repo.get_entity_by_id(entity_id)
    if entity is None:
        raise EntityNotFoundError(f"Entity '{entity_id}' not found in knowledge graph.")

    checks: list[DimensionCheck] = [
        _check_geographic_scope(
            repo,
            geographic_scope_entity_id or entity_id,
            input_data.destination,
        ),
        _check_excluded_type(repo, entity_id, input_data.excludedPlaceTypes),
        _check_opening_hours(repo, entity_id),
        _check_typical_duration(repo, entity_id, input_data.days),
        _check_time_slot(repo, entity_id),
        _check_booking_required(repo, entity_id),
        _check_admission_fee(
            repo,
            entity_id,
            input_data.budgetLevel,
            input_data.budgetTargetAmount,
        ),
        _check_accessibility(repo, entity_id, input_data.accessibilityRequirements),
        _check_suitable_for(repo, entity_id, input_data.partySize),
        _check_requirements(repo, entity_id, input_data.userConstraints),
        _check_weather_constraints(
            repo, entity_id, input_data.startDate, input_data.endDate
        ),
        _check_provenance_trust(repo, entity_id),
    ]

    checks.sort(key=lambda c: c.dimension)

    overall_status = _compute_overall_status(checks)

    warnings: list[str] = []
    for check in checks:
        if check.dimension == "accessibility" and check.status == CheckStatus.UNKNOWN:
            warnings.append(
                "ACCESSIBILITY_UNKNOWN: Accessibility features are unknown. "
                "Verify before visiting."
            )

    entity_summary = EntitySummaryFit(
        id=entity.id,
        name=entity.canonical_name,
        type=entity.entity_type,
        status=entity.status,
    )

    return ExperienceFitOutput(
        entity=entity_summary,
        overallStatus=overall_status,
        checks=checks,
        warnings=warnings,
    )
