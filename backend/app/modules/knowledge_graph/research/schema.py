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
    "Restaurant",
    "TravelPlace",
    "Cafe",
    "Hotel",
    "Shop",
    "Attraction",
    "Entertainment",
    "Activity",
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
