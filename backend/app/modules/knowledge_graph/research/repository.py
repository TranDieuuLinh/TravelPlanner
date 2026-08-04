"""PostgreSQL repository for Knowledge Graph research operations.

Read-only queries for scope resolution and graph statistics.
Does not modify data.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    AreaRef,
    GraphStats,
)

if TYPE_CHECKING:
    pass


def _normalized(value: str) -> str:
    """Normalize text for case/diacritic-insensitive matching.

    NFKD decomposition strips combining marks (diacritics), then removes
    non-alphanumeric characters and normalizes whitespace.
    """
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


class ScopeResolutionRepository:
    """Read-only repository for scope resolution queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Graph statistics ---

    def stats(self) -> GraphStats:
        """Return aggregate statistics for the knowledge graph."""
        entity_count = self.db.scalar(select(func.count(KnowledgeEntity.id))) or 0
        alias_count = self.db.scalar(select(func.count(KnowledgeAlias.id))) or 0
        relationship_count = self.db.scalar(
            select(func.count(KnowledgeRelationship.id))
        ) or 0

        # Get area counts per type
        area_count_map: dict[str, int] = {}
        for entity_type in AREA_TYPES:
            count = self.db.scalar(
                select(func.count(KnowledgeEntity.id)).where(
                    KnowledgeEntity.entity_type == entity_type
                )
            ) or 0
            area_count_map[entity_type] = count

        return GraphStats(
            entityCount=entity_count,
            aliasCount=alias_count,
            relationshipCount=relationship_count,
            areaCount=area_count_map.get("Area", 0),
            areaAdm0Count=area_count_map.get("AreaAdm0", 0),
            areaAdm1Count=area_count_map.get("AreaAdm1", 0),
            areaAdm2Count=area_count_map.get("AreaAdm2", 0),
        )

    def is_empty(self) -> bool:
        """Check if the knowledge graph has any entities."""
        count = self.db.scalar(select(func.count(KnowledgeEntity.id))) or 0
        return count == 0

    # --- Area resolution ---

    def resolve_area_by_name(self, destination: str) -> KnowledgeEntity | None:
        """Resolve an Area by canonical name or alias.

        First tries exact normalized match on canonical name, then on aliases.
        Returns the matching entity or None if not found.
        """
        normalized = _normalized(destination)

        entity = self.db.scalars(
            select(KnowledgeEntity).where(
                KnowledgeEntity.normalized_name == normalized,
                KnowledgeEntity.entity_type.in_(AREA_TYPES),
            )
        ).first()
        if entity is not None:
            return entity

        alias_record = self.db.scalars(
            select(KnowledgeAlias).where(
                KnowledgeAlias.normalized_alias == normalized,
            )
        ).first()
        if alias_record is not None:
            entity = self.db.get(KnowledgeEntity, alias_record.entity_id)
            if entity is not None and entity.entity_type in AREA_TYPES:
                return entity

        return None

    def get_area_by_id(self, entity_id: str) -> KnowledgeEntity | None:
        """Get an Area entity by ID if it exists and is an Area type."""
        entity = self.db.get(KnowledgeEntity, entity_id)
        if entity is not None and entity.entity_type in AREA_TYPES:
            return entity
        return None

    def get_area_ref(self, entity: KnowledgeEntity, depth: int = 0) -> AreaRef:
        """Convert a KnowledgeEntity to an AreaRef."""
        return AreaRef(
            id=entity.id,
            name=entity.canonical_name,
            normalizedName=entity.normalized_name,
            type=entity.entity_type,
            depth=depth,
        )

    def traverse_part_of_ancestors(
        self,
        entity_id: str,
        max_depth: int = 4,
    ) -> list[AreaRef]:
        """Traverse PART_OF relationships upward to get ancestors.

        Args:
            entity_id: Starting entity ID
            max_depth: Maximum traversal depth

        Returns:
            List of ancestor AreaRef objects, ordered from immediate parent outward
        """
        ancestors: list[AreaRef] = []
        visited: set[str] = {entity_id}
        current_id: str | None = entity_id
        depth = 0

        while current_id is not None and depth < max_depth:
            result = self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.from_entity_id == current_id,
                    KnowledgeRelationship.relationship_type == "PART_OF",
                )
            ).first()

            if result is None:
                break

            parent_entity = self.db.get(KnowledgeEntity, result.to_entity_id)
            if parent_entity is None:
                break

            if parent_entity.id in visited:
                break

            if parent_entity.entity_type in AREA_TYPES:
                depth += 1
                ancestors.append(self.get_area_ref(parent_entity, depth))
                visited.add(parent_entity.id)
                current_id = parent_entity.id
            else:
                break

        return ancestors

    def traverse_part_of_descendants(
        self,
        entity_id: str,
        max_depth: int = 4,
        limit: int = 100,
    ) -> list[AreaRef]:
        """Traverse PART_OF relationships downward to get descendants.

        Args:
            entity_id: Starting entity ID
            max_depth: Maximum traversal depth
            limit: Maximum number of descendants to return

        Returns:
            List of descendant AreaRef objects, grouped by depth
        """
        descendants: list[AreaRef] = []
        visited: set[str] = {entity_id}
        queue: list[tuple[str, int]] = [(entity_id, 0)]

        while queue and len(descendants) < limit:
            current_id, current_depth = queue.pop(0)

            if current_depth >= max_depth:
                continue

            child_relationships = self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.to_entity_id == current_id,
                    KnowledgeRelationship.relationship_type == "PART_OF",
                )
            ).all()

            for rel in child_relationships:
                child_entity = self.db.get(KnowledgeEntity, rel.from_entity_id)
                if (
                    child_entity is not None
                    and child_entity.id not in visited
                    and child_entity.entity_type in AREA_TYPES
                ):
                    visited.add(child_entity.id)
                    descendants.append(
                        self.get_area_ref(child_entity, current_depth + 1)
                    )
                    if len(descendants) >= limit:
                        break
                    queue.append((child_entity.id, current_depth + 1))

        descendants.sort(key=lambda x: (x.depth, x.name))
        return descendants

    def map_places_to_areas(
        self,
        place_ids: list[str],
        limit: int = 100,
    ) -> list[AreaRef]:
        """Map Place entities to their containing Areas via LOCATED_IN relationships.

        Args:
            place_ids: List of Place entity IDs
            limit: Maximum number of areas to return

        Returns:
            List of AreaRef objects for the places' locations
        """
        if not place_ids:
            return []

        area_refs: list[AreaRef] = []
        visited_place_areas: set[str] = set()

        for place_id in place_ids[:limit]:
            location_rel = self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.from_entity_id == place_id,
                    KnowledgeRelationship.relationship_type == "LOCATED_IN",
                )
            ).first()

            if location_rel is None:
                continue

            area_entity = self.db.get(KnowledgeEntity, location_rel.to_entity_id)
            if area_entity is None:
                continue

            if area_entity.entity_type in AREA_TYPES and area_entity.id not in visited_place_areas:
                visited_place_areas.add(area_entity.id)
                area_refs.append(self.get_area_ref(area_entity, 0))

        area_refs.sort(key=lambda x: x.name)
        return area_refs
