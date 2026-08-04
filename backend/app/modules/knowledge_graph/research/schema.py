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
