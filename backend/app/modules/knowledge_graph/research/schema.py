"""Pydantic schemas for Knowledge Graph research tools."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AreaType(str, Enum):
    """Allowed Area entity types."""

    LEGACY_AREA = "Area"
    AREA_ADM0 = "AreaAdm0"
    AREA_ADM1 = "AreaAdm1"
    AREA_ADM2 = "AreaAdm2"


AREA_TYPES: frozenset[str] = frozenset({t.value for t in AreaType})

PLACE_TYPES: frozenset[str] = frozenset({
    # Schema v7 concrete Place descendants.
    "Restaurant",
    "TravelPlace",
    "DrinkDessert",
    "Accommodation",
    # Read compatibility for pre-v7 graph rows.
    "Cafe",
    "Hotel",
    "Shop",
    "Attraction",
    "Entertainment",
})

ActivityTypes: frozenset[str] = frozenset({
    "Activity",
    "Event",
    "Tour",
    "Workshop",
    "Class",
})


class AreaRef(BaseModel):
    """Reference to an Area entity with its hierarchy context."""

    id: str = Field(description="Entity identifier")
    name: str = Field(description="Canonical name")
    normalizedName: str = Field(description="Case/diacritic-normalized name")
    type: str = Field(description="Entity type (Area, AreaAdm0, AreaAdm1, AreaAdm2)")
    depth: int = Field(description="Depth in hierarchy (0 = root)")


class ScopeResolveInput(BaseModel):
    """Input schema for kg_resolve_scope tool."""

    destination: str = Field(min_length=1, description="Destination name to resolve")
    selectedPlaceIds: list[str] | None = Field(
        default=None,
        description="Optional list of Place entity IDs to map to Areas",
    )
    maxDepth: int = Field(default=4, ge=1, le=10, description="Maximum PART_OF traversal depth")
    resultLimit: int = Field(default=100, ge=1, le=1000, description="Maximum areas to return")


class ScopeResolveOutput(BaseModel):
    """Output schema for kg_resolve_scope tool."""

    rootArea: AreaRef | None = Field(
        default=None,
        description="The resolved root Area entity",
    )
    ancestors: list[AreaRef] = Field(
        default_factory=list,
        description="Ancestor Areas (parent, grandparent, etc.)",
    )
    includedAreas: list[AreaRef] = Field(
        default_factory=list,
        description="All Areas within the scope including descendants",
    )
    selectedPlaceAreas: list[AreaRef] = Field(
        default_factory=list,
        description="Areas mapped from selected Place entities via LOCATED_IN",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (legacy types, empty graph, etc.)",
    )


class GraphStats(BaseModel):
    """Statistics about the knowledge graph."""

    entityCount: int = Field(description="Total number of entities")
    aliasCount: int = Field(description="Total number of aliases")
    relationshipCount: int = Field(description="Total number of relationships")
    areaCount: int = Field(description="Number of Area entities")
    areaAdm0Count: int = Field(description="Number of AreaAdm0 entities")
    areaAdm1Count: int = Field(description="Number of AreaAdm1 entities")
    areaAdm2Count: int = Field(description="Number of AreaAdm2 entities")


class SpecialtyMealCandidate(BaseModel):
    """Bounded meal venue projected from destination graph relationships."""

    activityId: str
    activityName: str
    placeId: str
    itemId: str | None = None
    itemName: str | None = None
    selectionPath: str = Field(pattern=r"^(target_place|offers_item)$")
    bestTimeSlots: list[str] = Field(default_factory=list)


class OfferedActivityCandidate(BaseModel):
    """A concrete Place connected to an Activity by ``OFFERS_ACTIVITY``."""

    placeId: str
    activityId: str
    activityName: str


# ---------------------------------------------------------------------------
# Experience Fit Evaluation schemas
# ---------------------------------------------------------------------------


class BudgetLevel(str, Enum):
    """Budget level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    LUXURY = "luxury"


class TransportMode(str, Enum):
    """Preferred or avoided transport modes."""

    WALKING = "walking"
    CYCLING = "cycling"
    PUBLIC_TRANSIT = "public_transit"
    TAXI = "taxi"
    CAR = "car"
    BOAT = "boat"
    MOTORBIKE = "motorbike"


class CheckStatus(str, Enum):
    """Status for each evaluation dimension."""

    SUPPORTED = "supported"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


class DimensionCheck(BaseModel):
    """Result of a single dimension evaluation."""

    dimension: str = Field(
        description="Dimension name (e.g. 'opening_hours', 'admission_fee')"
    )
    status: CheckStatus = Field(description="Evaluation result for this dimension")
    reason: str = Field(
        description="Human-readable explanation of why this status was assigned"
    )
    evidenceClaimIds: list[str] = Field(
        default_factory=list,
        description="IDs of evidence claims that support this check",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Source labels that provided evidence for this check",
    )


class EntitySummaryFit(BaseModel):
    """Minimal entity representation returned in fit evaluation."""

    id: str = Field(description="Entity identifier")
    name: str = Field(description="Canonical name")
    type: str = Field(description="Entity type")
    status: str = Field(description="Entity status (verified, draft, etc.)")


class ExperienceFitInput(BaseModel):
    """Input schema for kg_evaluate_experience_fit tool."""

    entityId: str | None = Field(
        default=None,
        description="Entity ID to evaluate (mutually exclusive with claimId)",
    )
    claimId: str | None = Field(
        default=None,
        description="Claim/Experience ID to evaluate (mutually exclusive with entityId)",
    )
    destination: str = Field(min_length=1, description="Destination name for scope check")
    days: int = Field(ge=1, le=30, description="Number of trip days")
    partySize: int = Field(ge=1, le=20, default=1, description="Number of travelers")
    startDate: str | None = Field(
        default=None,
        description="Optional trip start date (ISO 8601)",
    )
    endDate: str | None = Field(
        default=None,
        description="Optional trip end date (ISO 8601)",
    )
    budgetLevel: BudgetLevel | None = Field(
        default=None,
        description="Budget level preference",
    )
    budgetTargetAmount: float | None = Field(
        default=None,
        ge=0,
        description="Target total budget in VND",
    )
    excludedPlaceTypes: list[str] = Field(
        default_factory=list,
        description="Place types to exclude (e.g. 'Restaurant', 'Accommodation')",
    )
    preferredTransportModes: list[TransportMode] = Field(
        default_factory=list,
        description="Preferred transport modes",
    )
    avoidedTransportModes: list[TransportMode] = Field(
        default_factory=list,
        description="Transport modes to avoid",
    )
    accessibilityRequirements: list[str] = Field(
        default_factory=list,
        description="Accessibility requirements (e.g. 'wheelchair', 'hearing_aid')",
    )
    userConstraints: list[str] = Field(
        default_factory=list,
        description="Additional user-defined constraints",
    )


class ExperienceFitOutput(BaseModel):
    """Output schema for kg_evaluate_experience_fit tool."""

    entity: EntitySummaryFit | None = Field(
        default=None,
        description="Summary of the evaluated entity",
    )
    overallStatus: CheckStatus = Field(
        description="Aggregated status across all dimensions"
    )
    checks: list[DimensionCheck] = Field(
        default_factory=list,
        description="Per-dimension evaluation results",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings and recommendations",
    )


# --- Experience Discovery Schemas ---


class TrustLevel(str, Enum):
    """Trust level for graph evidence."""

    VERIFIED = "verified"
    SOURCE_BACKED = "source_backed"
    INFERRED = "inferred"


class RecommendationPriority(str, Enum):
    """Priority level for recommendations."""

    MUST = "must"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class EntitySummary(BaseModel):
    """Summary of an entity for inclusion in claims."""

    id: str = Field(description="Entity identifier")
    name: str = Field(description="Canonical name")
    type: str = Field(description="Entity type")
    status: str | None = Field(default=None, description="Entity verification status")


class Recommendation(BaseModel):
    """Structured recommendation for an experience."""

    priority: RecommendationPriority = Field(description="Priority level")
    intent: str | None = Field(default=None, description="Intent or theme")
    timeSlots: list[str | dict] = Field(
        default_factory=list, description="Suggested time slots (strings or time ranges)"
    )
    recommendedVisitMinutes: int | None = Field(
        default=None, description="Suggested visit duration in minutes"
    )
    reason: str | None = Field(default=None, description="Reason for recommendation")
    warnings: list[str] = Field(
        default_factory=list, description="Warnings or caveats"
    )

    @property
    def time_slots(self) -> list[str | dict]:
        """Pythonic read alias for the public ``timeSlots`` field."""
        return self.timeSlots

    @property
    def recommended_visit_minutes(self) -> int | None:
        """Pythonic read alias for the public timing field."""
        return self.recommendedVisitMinutes


class EdgeEvidence(BaseModel):
    """Evidence for a graph edge."""

    edgeId: int | str | None = Field(default=None, description="Edge database ID")
    source: str | None = Field(
        default=None, description="Source attribution or URL"
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="Edge recommendations"
    )
    propertyProvenance: str | None = Field(
        default=None, description="Property source (e.g., 'inference:taxonomy')"
    )


class GraphEvidenceClaim(BaseModel):
    """A single evidence claim from the knowledge graph."""

    claimId: str = Field(description="Stable unique claim identifier")
    subject: EntitySummary = Field(description="Source entity (Area or Place)")
    predicate: str = Field(description="Relationship type")
    object: EntitySummary = Field(description="Target entity (Place or Activity)")
    path: list[str] = Field(
        default_factory=list, description="Full path through graph"
    )
    anchorPlace: EntitySummary | None = Field(
        default=None, description="Anchor Place for OFFERS_ACTIVITY path"
    )
    activity: EntitySummary | None = Field(
        default=None, description="Activity entity if applicable"
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="Structured recommendations"
    )
    evidence: list[EdgeEvidence] = Field(
        default_factory=list, description="Evidence from each edge in path"
    )
    trust: TrustLevel = Field(description="Trust level for this claim")
    inferenceSource: str | None = Field(
        default=None, description="Inference source if trust is inferred"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warnings about this claim"
    )


class UnknownClaim(BaseModel):
    """Placeholder for unresolved queries."""

    query: str = Field(description="The unresolved query")
    reason: str = Field(description="Why resolution failed")


class GraphSnapshot(BaseModel):
    """Snapshot of graph state for provenance."""

    timestamp: str = Field(description="ISO timestamp of snapshot")
    areaIds: list[str] = Field(
        default_factory=list, description="Area IDs in scope"
    )
    placeIds: list[str] = Field(
        default_factory=list, description="Place IDs included"
    )
    activityIds: list[str] = Field(
        default_factory=list, description="Activity IDs included"
    )


class GraphEvidenceBundle(BaseModel):
    """Bounded evidence bundle from experience discovery."""

    claims: list[GraphEvidenceClaim] = Field(
        default_factory=list, description="Evidence claims"
    )
    unknowns: list[UnknownClaim] = Field(
        default_factory=list, description="Unresolved queries"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings"
    )
    graphSnapshot: GraphSnapshot = Field(
        description="Graph state snapshot"
    )
    catalog: "SpecialExperienceCatalog" = Field(
        default_factory=lambda: SpecialExperienceCatalog(),
        description="Bounded catalog of evidence-backed Activity candidates",
    )


class ExperienceDiscoveryInput(BaseModel):
    """Input schema for kg_discover_experiences tool."""

    rootAreaId: str | None = Field(
        default=None, description="Root Area entity ID"
    )
    destination: str | None = Field(
        default=None, description="Destination name to resolve to Area"
    )
    interests: list[str] = Field(
        default_factory=list, description="Interest tags to filter by"
    )
    selectedPlaceIds: list[str] | None = Field(
        default=None, description="Optional Place IDs to filter by"
    )
    limit: int = Field(default=20, ge=1, le=50, description="Maximum claims to return")
    includeInferred: bool = Field(
        default=True, description="Include inferred claims"
    )


class SpecialExperienceCandidate(BaseModel):
    """A selectable Activity with graph provenance and bounded evidence."""

    claim_ids: list[str] = Field(default_factory=list, alias="claimIds")
    place_ids: list[str] = Field(default_factory=list, alias="placeIds")
    anchor_place_ids: list[str] = Field(default_factory=list, alias="anchorPlaceIds")
    activity_id: str = Field(alias="activityId")
    predicate: str = Field(description="Predicate of the primary evidence claim")
    path: list[str] = Field(default_factory=list, description="Primary graph path")
    edge_evidence: list[EdgeEvidence] = Field(default_factory=list, alias="edgeEvidence")
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")
    recommendation: Recommendation | None = None
    trust: TrustLevel = TrustLevel.SOURCE_BACKED
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class SpecialExperienceCatalog(BaseModel):
    """Bounded main-experience catalog; raw provider payload is never included."""

    candidates: list[SpecialExperienceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}


# ---------------------------------------------------------------------------
# Trip Research Orchestrator schemas
# ---------------------------------------------------------------------------


class TravelBudget(BaseModel):
    """Budget information for a trip research request."""

    level: BudgetLevel = Field(
        default=BudgetLevel.MEDIUM, description="Budget level classification"
    )
    targetAmount: float | None = Field(
        default=None, ge=0, description="Target total budget amount"
    )
    currency: str = Field(
        default="VND", description="Currency code"
    )


class TripResearchInput(BaseModel):
    """Input schema for the GraphResearchOrchestrator.

    This is the input contract for the trip research orchestration flow.
    """

    destination: str = Field(min_length=1, description="Primary destination name")
    destinationStays: list[str] = Field(
        default_factory=list, description="Additional destinations or stays"
    )
    selectedPlaceIds: list[str] = Field(
        default_factory=list, description="Place IDs pre-selected by user"
    )
    interests: list[str] = Field(
        default_factory=list, description="Interest tags (e.g. culture, coffee)"
    )
    travelStyle: str = Field(
        default="balanced", description="Travel style preference"
    )
    pace: str = Field(
        default="balanced", description="Trip pace (relaxed, balanced, busy)"
    )
    days: int = Field(ge=1, le=30, default=3, description="Number of trip days")
    partySize: int = Field(ge=1, le=20, default=2, description="Number of travelers")
    startDate: str | None = Field(
        default=None, description="Trip start date (ISO 8601)"
    )
    endDate: str | None = Field(
        default=None, description="Trip end date (ISO 8601)"
    )
    budget: TravelBudget = Field(
        default_factory=TravelBudget, description="Budget constraints"
    )
    constraints: list[str] = Field(
        default_factory=list, description="Additional user constraints"
    )
    excludedPlaceTypes: list[str] = Field(
        default_factory=list, description="Place types to exclude"
    )
    preferredModes: list[TransportMode] = Field(
        default_factory=list, description="Preferred transport modes"
    )
    avoidModes: list[TransportMode] = Field(
        default_factory=list, description="Transport modes to avoid"
    )
    includeInferred: bool = Field(
        default=True, description="Include inferred claims"
    )
    candidateLimit: int = Field(
        default=30, ge=1, le=100, description="Maximum candidates to return"
    )


class FitResult(BaseModel):
    """Fit evaluation result for a single candidate."""

    status: CheckStatus = Field(description="Overall fit status")
    hasHardConflict: bool = Field(
        description="Whether this candidate has a hard constraint conflict"
    )
    dimensionCount: int = Field(description="Number of dimensions evaluated")


class RankedExperience(BaseModel):
    """An experience candidate with rank and reasons."""

    claim: GraphEvidenceClaim = Field(description="The evidence claim")
    fit: FitResult = Field(description="Fit evaluation result")
    rank: int = Field(ge=1, description="Final rank (1-based)")
    rankReasons: list[str] = Field(
        default_factory=list, description="Reasons for this rank"
    )


class ConflictedExperience(BaseModel):
    """An experience that has hard constraint conflicts."""

    claim: GraphEvidenceClaim = Field(description="The evidence claim")
    fit: FitResult = Field(description="Fit evaluation result")
    conflictReasons: list[str] = Field(
        default_factory=list, description="Hard constraint violations"
    )


class ResearchTrace(BaseModel):
    """Execution trace for debugging and observability."""

    scopeResultCount: int = Field(
        default=0, description="Number of areas in resolved scope"
    )
    discoveredClaimCount: int = Field(
        default=0, description="Number of claims discovered"
    )
    evaluatedExperienceCount: int = Field(
        default=0, description="Number of experiences evaluated"
    )
    eligibleExperienceCount: int = Field(
        default=0, description="Number of eligible experiences in output"
    )
    conflictedExperienceCount: int = Field(
        default=0, description="Number of conflicted experiences in output"
    )


class TripResearchBundle(BaseModel):
    """Output bundle from the trip research orchestration.

    This is the bounded output contract containing ranked experiences,
    conflicts, and metadata for downstream planning.
    """

    scope: ScopeResolveOutput = Field(description="Resolved geographic scope")
    eligibleExperiences: list[RankedExperience] = Field(
        default_factory=list, description="Eligible experiences sorted by rank"
    )
    conflictedExperiences: list[ConflictedExperience] = Field(
        default_factory=list, description="Experiences with hard conflicts"
    )
    unknowns: list[GraphEvidenceClaim] = Field(
        default_factory=list, description="Experiences with unknown fit status"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings"
    )
    graphSnapshot: GraphSnapshot = Field(
        description="Graph state snapshot at time of research"
    )
    trace: ResearchTrace = Field(
        default_factory=ResearchTrace, description="Execution trace"
    )
    catalog: SpecialExperienceCatalog = Field(
        default_factory=lambda: SpecialExperienceCatalog(),
        description="Bounded main-experience catalog",
    )
