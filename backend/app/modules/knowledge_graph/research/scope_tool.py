"""Scope resolution research tool for Knowledge Graph.

This module provides read-only operations for resolving geographic scope
from the knowledge graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.knowledge_graph.research.repository import (
    ScopeResolutionRepository,
)
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    AreaRef,
    ScopeResolveInput,
    ScopeResolveOutput,
)

if TYPE_CHECKING:
    pass


class LegacyAreaWarning:
    """Warning code for legacy Area type usage."""

    CODE = "LEGACY_AREA_TYPE"


def kg_resolve_scope(
    repo: ScopeResolutionRepository,
    input_data: ScopeResolveInput,
) -> ScopeResolveOutput:
    """Resolve geographic scope from the knowledge graph.

    This tool resolves a destination name to an Area entity and traverses
    its PART_OF hierarchy to build a complete scope.

    Args:
        repo: The scope resolution repository (read-only)
        input_data: Input containing destination and optional parameters

    Returns:
        ScopeResolveOutput with root area, ancestors, descendants, and warnings

    Behavior:
        - Resolves destination by canonical name or alias (case/diacritic-insensitive)
        - Only resolves Area entity types (Area, AreaAdm0, AreaAdm1, AreaAdm2)
        - Warns if legacy 'Area' type is encountered
        - Warns if the knowledge graph is empty
        - Traverses PART_OF relationships up to maxDepth (default: 4)
        - Maps selected Place entities to Areas via LOCATED_IN
        - Returns deterministic ordering (sorted by name, then depth)
        - Does not load the entire graph into memory
    """
    warnings: list[str] = []
    included_areas: list[AreaRef] = []
    selected_place_areas: list[AreaRef] = []

    if repo.is_empty():
        warnings.append("KNOWLEDGE_GRAPH_EMPTY: Graph has no entities. Import data first.")

    root = repo.resolve_area_by_name(input_data.destination)

    if root is None:
        return ScopeResolveOutput(
            rootArea=None,
            ancestors=[],
            includedAreas=[],
            selectedPlaceAreas=[],
            warnings=warnings,
        )

    if root.entity_type == "Area":
        warnings.append(
            f"{LegacyAreaWarning.CODE}: Entity uses legacy 'Area' type. "
            "Consider migrating to AreaAdm0, AreaAdm1, or AreaAdm2."
        )

    root_ref = repo.get_area_ref(root, depth=0)

    ancestors = repo.traverse_part_of_ancestors(
        root.id,
        max_depth=input_data.maxDepth,
    )

    descendants = repo.traverse_part_of_descendants(
        root.id,
        max_depth=input_data.maxDepth,
        limit=input_data.resultLimit,
    )

    if descendants:
        included_areas = descendants
    else:
        included_areas = []

    if input_data.selectedPlaceIds:
        selected_place_areas = repo.map_places_to_areas(
            input_data.selectedPlaceIds,
            limit=input_data.resultLimit,
        )

    return ScopeResolveOutput(
        rootArea=root_ref,
        ancestors=ancestors,
        includedAreas=included_areas,
        selectedPlaceAreas=selected_place_areas,
        warnings=warnings,
    )
