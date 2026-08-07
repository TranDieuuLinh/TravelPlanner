"""PostgreSQL repository for Knowledge Graph research operations.

Read-only queries for scope resolution and graph statistics.
Does not modify data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.text import normalize_knowledge_text
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    ActivityTypes,
    AreaRef,
    EntitySummary,
    GraphStats,
    PLACE_TYPES,
    Recommendation,
    RecommendationPriority,
    TrustLevel,
)

if TYPE_CHECKING:
    pass

# Trust inference source prefix
INFERENCE_PREFIX = "inference:"


def _normalized(value: str) -> str:
    """Normalize text for case/diacritic-insensitive matching.

    NFKD decomposition strips combining marks (diacritics), then removes
    non-alphanumeric characters and normalizes whitespace.
    """
    return normalize_knowledge_text(value)


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

    def list_meal_item_nodes(self, *, limit: int = 100) -> list[KnowledgeEntity]:
        """Return canonical food/drink nodes for a bounded planner query."""
        return list(
            self.db.scalars(
                select(KnowledgeEntity)
                .where(KnowledgeEntity.entity_type.in_(("FoodItem", "DrinkItem")))
                .order_by(KnowledgeEntity.entity_type, KnowledgeEntity.canonical_name)
                .limit(limit)
            ).all()
        )

    def list_places_offering_items(
        self,
        item_ids: list[str],
        *,
        limit: int = 250,
    ) -> list[KnowledgeEntity]:
        """Resolve graph Places connected to FoodItem/DrinkItem via OFFERS_ITEM."""
        if not item_ids:
            return []
        place = aliased(KnowledgeEntity)
        return list(
            self.db.scalars(
                select(place)
                .join(
                    KnowledgeRelationship,
                    KnowledgeRelationship.from_entity_id == place.id,
                )
                .where(
                    KnowledgeRelationship.to_entity_id.in_(item_ids),
                    KnowledgeRelationship.relationship_type == "OFFERS_ITEM",
                    place.entity_type.in_(PLACE_TYPES),
                )
                .order_by(KnowledgeRelationship.id)
                .limit(limit)
            ).all()
        )

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

        entity = self.db.scalars(
            select(KnowledgeEntity)
            .join(KnowledgeAlias, KnowledgeAlias.entity_id == KnowledgeEntity.id)
            .where(
                KnowledgeAlias.normalized_alias == normalized,
                KnowledgeEntity.entity_type.in_(AREA_TYPES),
            )
        ).first()
        if entity is not None:
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

    # --- Experience Fit Evaluation ---

    def get_entity_by_id(self, entity_id: str) -> KnowledgeEntity | None:
        """Get an entity by its ID."""
        return self.db.get(KnowledgeEntity, entity_id)

    def get_entity_properties(self, entity_id: str) -> dict[str, str]:
        """Get all properties for an entity as a flat dict.

        Returns:
            Dict mapping property key to (value, source) tuples.
        """
        rows = self.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
            )
        ).all()
        return {row.key: row.value for row in rows}

    def get_entity_property_with_source(self, entity_id: str, key: str) -> tuple[str | None, str | None]:
        """Get a single property value and its source for an entity.

        Returns:
            Tuple of (value, source) or (None, None) if not found.
        """
        prop = self.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
                KnowledgeProperty.key == key,
            )
        ).first()
        if prop is None:
            return None, None
        return prop.value, prop.source

    def get_located_in_area(self, entity_id: str) -> str | None:
        """Get the Area ID that an entity is located in via LOCATED_IN relationship.

        Returns:
            Area entity ID or None if not found.
        """
        rel = self.db.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.from_entity_id == entity_id,
                KnowledgeRelationship.relationship_type == "LOCATED_IN",
            )
        ).first()
        if rel is None:
            return None
        return rel.to_entity_id

    def is_entity_in_scope(self, entity_id: str, scope_area_ids: set[str]) -> bool:
        """Check if an entity is within the geographic scope.

        Traverses LOCATED_IN chain to find the root area, then checks
        if it is within the allowed scope area IDs.

        Returns:
            True if entity's root area is in scope, False otherwise.
        """
        visited: set[str] = set()
        current_id: str | None = entity_id

        while current_id is not None and current_id not in visited:
            if current_id in scope_area_ids:
                return True
            visited.add(current_id)
            next_area = self.get_located_in_area(current_id)
            if next_area is None or next_area == current_id:
                break
            current_id = next_area

        return False

    def get_scope_area_ids_for_destination(
        self,
        destination: str,
        max_depth: int = 4,
    ) -> set[str]:
        """Get all area IDs within the geographic scope of a destination.

        Args:
            destination: Destination name to resolve
            max_depth: Maximum PART_OF traversal depth

        Returns:
            Set of area entity IDs in the scope.
        """
        root = self.resolve_area_by_name(destination)
        if root is None:
            return set()

        area_ids: set[str] = {root.id}

        descendants = self.traverse_part_of_descendants(root.id, max_depth=max_depth)
        for area_ref in descendants:
            area_ids.add(area_ref.id)

        ancestors = self.traverse_part_of_ancestors(root.id, max_depth=max_depth)
        for area_ref in ancestors:
            area_ids.add(area_ref.id)

        return area_ids

    def get_all_properties_with_sources(self, entity_id: str) -> list[tuple[str, str, str | None]]:
        """Get all properties for an entity with their sources.

        Returns:
            List of (key, value, source) tuples.
        """
        rows = self.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
            )
        ).all()
        return [(row.key, row.value, row.source) for row in rows]
    # --- Experience Discovery Queries ---

    def get_entity_summary(self, entity: KnowledgeEntity) -> EntitySummary:
        """Convert a KnowledgeEntity to EntitySummary."""
        return EntitySummary(
            id=entity.id,
            name=entity.canonical_name,
            type=entity.entity_type,
            status=entity.status,
        )

    def _determine_trust(
        self,
        entity: KnowledgeEntity,
        edge_source: str | None,
    ) -> tuple[TrustLevel, str | None]:
        """Determine trust level and inference source for an entity/edge.

        Returns:
            Tuple of (trust_level, inference_source)
        """
        inference_source = None

        if edge_source and edge_source.startswith(INFERENCE_PREFIX):
            trust = TrustLevel.INFERRED
            inference_source = edge_source
        elif edge_source:
            trust = TrustLevel.SOURCE_BACKED
        elif entity.status == "verified":
            trust = TrustLevel.VERIFIED
        else:
            trust = TrustLevel.INFERRED
            if edge_source:
                inference_source = edge_source
            elif entity.status == "draft":
                inference_source = "inference:draft_status"

        return trust, inference_source

    def _parse_recommendations(
        self,
        recommendations_data: dict | None,
        property_provenance: str | None,
    ) -> tuple[list[Recommendation], TrustLevel, list[str]]:
        """Parse recommendations from edge or property data.

        Returns:
            Tuple of (recommendations, trust, warnings)
        """
        recommendations: list[Recommendation] = []
        warnings: list[str] = []
        base_trust = TrustLevel.VERIFIED

        if recommendations_data:
            if isinstance(recommendations_data, list):
                recs_data = recommendations_data
            else:
                recs_data = [recommendations_data]

            for rec_data in recs_data:
                if isinstance(rec_data, dict):
                    priority_str = rec_data.get("priority", "recommended")
                    try:
                        priority = RecommendationPriority(priority_str)
                    except ValueError:
                        priority = RecommendationPriority.RECOMMENDED

                    # Normalize timeSlots: convert objects to strings like "08:00-11:30"
                    raw_time_slots = rec_data.get("timeSlots", [])
                    normalized_time_slots: list[str | dict] = []
                    for slot in raw_time_slots:
                        if isinstance(slot, dict):
                            if "start" in slot and "end" in slot:
                                normalized_time_slots.append(f"{slot['start']}-{slot['end']}")
                            else:
                                normalized_time_slots.append(slot)
                        elif isinstance(slot, str):
                            normalized_time_slots.append(slot)

                    rec = Recommendation(
                        priority=priority,
                        intent=rec_data.get("intent"),
                        timeSlots=normalized_time_slots,
                        recommendedVisitMinutes=rec_data.get("recommendedVisitMinutes"),
                        reason=rec_data.get("reason"),
                        warnings=[],
                    )

                    # Trust policy: downgrade 'must' to 'recommended' if only inference
                    if (
                        priority == RecommendationPriority.MUST
                        and property_provenance
                        and property_provenance.startswith(INFERENCE_PREFIX)
                    ):
                        rec = Recommendation(
                            priority=RecommendationPriority.RECOMMENDED,
                            intent=rec.intent,
                            timeSlots=rec.timeSlots,
                            recommendedVisitMinutes=rec.recommendedVisitMinutes,
                            reason=rec.reason,
                            warnings=[
                                f"Priority downgraded from 'must' to 'recommended': "
                                f"source is {property_provenance}"
                            ],
                        )
                        warnings.append(
                            f"Downgraded 'must' priority for claim due to inferred source"
                        )

                    recommendations.append(rec)
                elif isinstance(rec_data, str):
                    recommendations.append(
                        Recommendation(
                            priority=RecommendationPriority.RECOMMENDED,
                            intent=rec_data,
                        )
                    )

        if property_provenance and property_provenance.startswith(INFERENCE_PREFIX):
            base_trust = TrustLevel.INFERRED

        return recommendations, base_trust, warnings

    def query_special_experiences_in_scope(
        self,
        location_ids: list[str],
        interests: list[str] | None = None,
        limit: int = 100,
    ) -> list[KnowledgeRelationship]:
        """Query schema-v7 SPECIAL_EXPERIENCE edges in scope.

        Path: LocationEntity → SPECIAL_EXPERIENCE → Activity
        """
        source_entity = aliased(KnowledgeEntity)
        activity_entity = aliased(KnowledgeEntity)
        query = (
            select(KnowledgeRelationship)
            .join(
                source_entity,
                KnowledgeRelationship.from_entity_id == source_entity.id,
            )
            .join(
                activity_entity,
                KnowledgeRelationship.to_entity_id == activity_entity.id,
            )
            .where(
                KnowledgeRelationship.from_entity_id.in_(location_ids),
                KnowledgeRelationship.relationship_type == "SPECIAL_EXPERIENCE",
                source_entity.entity_type.in_(AREA_TYPES),
                activity_entity.entity_type.in_(ActivityTypes),
            )
            .order_by(KnowledgeRelationship.id)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def query_activities_in_scope(
        self,
        area_ids: list[str],
        interests: list[str] | None = None,
        limit: int = 100,
    ) -> list[KnowledgeRelationship]:
        """Query SPECIAL_EXPERIENCE edges from Areas pointing to Activities.

        Path: Area → SPECIAL_EXPERIENCE → Activity
        """
        return self.query_special_experiences_in_scope(area_ids, interests, limit)

    def query_activity_targets_place(
        self,
        activity_ids: list[str],
        limit: int = 100,
    ) -> list[KnowledgeRelationship]:
        """Query schema-v7 Activity → TARGETS_PLACE → Place anchors."""

        if not activity_ids:
            return []
        source_entity = aliased(KnowledgeEntity)
        place_entity = aliased(KnowledgeEntity)
        query = (
            select(KnowledgeRelationship)
            .join(source_entity, KnowledgeRelationship.from_entity_id == source_entity.id)
            .join(place_entity, KnowledgeRelationship.to_entity_id == place_entity.id)
            .where(
                KnowledgeRelationship.from_entity_id.in_(activity_ids),
                KnowledgeRelationship.relationship_type == "TARGETS_PLACE",
                source_entity.entity_type.in_(ActivityTypes),
                place_entity.entity_type.in_(PLACE_TYPES),
            )
            .order_by(KnowledgeRelationship.id)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def query_place_offers_activity(
        self,
        place_ids: list[str],
        limit: int = 100,
    ) -> list[KnowledgeRelationship]:
        """Query OFFERS_ACTIVITY edges from Places.

        Path: Place → OFFERS_ACTIVITY → Activity
        """
        place_entity = aliased(KnowledgeEntity)
        activity_entity = aliased(KnowledgeEntity)
        query = (
            select(KnowledgeRelationship)
            .join(place_entity, KnowledgeRelationship.from_entity_id == place_entity.id)
            .join(activity_entity, KnowledgeRelationship.to_entity_id == activity_entity.id)
            .where(
                KnowledgeRelationship.from_entity_id.in_(place_ids),
                KnowledgeRelationship.relationship_type == "OFFERS_ACTIVITY",
                place_entity.entity_type.in_(PLACE_TYPES),
                activity_entity.entity_type.in_(ActivityTypes),
            )
            .order_by(KnowledgeRelationship.id)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def query_located_in_place_offers_activity(
        self,
        area_ids: list[str],
        limit: int = 100,
    ) -> list[tuple[KnowledgeRelationship, KnowledgeRelationship]]:
        """Query chained LOCATED_IN + OFFERS_ACTIVITY paths.

        Path: Area ← LOCATED_IN ← Place → OFFERS_ACTIVITY → Activity
        Returns tuples of (located_in_rel, offers_rel).
        """
        located_in_rels = (
            select(KnowledgeRelationship)
            .where(
                KnowledgeRelationship.to_entity_id.in_(area_ids),
                KnowledgeRelationship.relationship_type == "LOCATED_IN",
            )
            .limit(limit)
        )
        located_in_list = list(self.db.scalars(located_in_rels).all())
        place_ids = list({rel.from_entity_id for rel in located_in_list})

        if not place_ids:
            return []

        offers_rels = self.query_place_offers_activity(place_ids, limit=limit)
        offers_by_place: dict[str, list[KnowledgeRelationship]] = {}
        for rel in offers_rels:
            offers_by_place.setdefault(rel.from_entity_id, []).append(rel)

        chained: list[tuple[KnowledgeRelationship, KnowledgeRelationship]] = []
        for li_rel in located_in_list:
            for offers_rel in offers_by_place.get(li_rel.from_entity_id, []):
                chained.append((li_rel, offers_rel))

        return chained

    def query_located_in_children(
        self,
        parent_place_ids: list[str],
        *,
        limit: int = 100,
    ) -> list[KnowledgeRelationship]:
        """Return child Places/landmarks attached by LOCATED_IN."""
        if not parent_place_ids:
            return []
        return list(
            self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.to_entity_id.in_(parent_place_ids),
                    KnowledgeRelationship.relationship_type == "LOCATED_IN",
                ).limit(limit)
            ).all()
        )

    def get_entities_by_ids(
        self,
        entity_ids: list[str],
    ) -> dict[str, KnowledgeEntity]:
        """Batch fetch entities by IDs."""
        entities = self.db.scalars(
            select(KnowledgeEntity).where(KnowledgeEntity.id.in_(entity_ids))
        ).all()
        return {e.id: e for e in entities}

    def get_property_value(
        self,
        entity_id: str,
        key: str,
    ) -> KnowledgeProperty | None:
        """Get a single property for an entity."""
        return self.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
                KnowledgeProperty.key == key,
            )
        ).first()

    def get_scope_area_ids(
        self,
        root_area_id: str,
        max_depth: int = 4,
    ) -> list[str]:
        """Get all Area IDs in scope (root + descendants)."""
        area_ids = [root_area_id]
        queue: list[str] = [root_area_id]

        while queue:
            current_id = queue.pop(0)
            children = self.db.scalars(
                select(KnowledgeRelationship.to_entity_id).where(
                    KnowledgeRelationship.from_entity_id == current_id,
                    KnowledgeRelationship.relationship_type == "PART_OF",
                )
            ).all()

            for child_id in children:
                child_entity = self.db.get(KnowledgeEntity, child_id)
                if child_entity and child_entity.entity_type in AREA_TYPES:
                    area_ids.append(child_id)
                    queue.append(child_id)

        return area_ids


# Alias for compatibility with experience discovery tool
KnowledgeGraphResearchRepository = ScopeResolutionRepository
