"""PostgreSQL repository for Knowledge Graph entities and AI imports."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeGraphImport,
    KnowledgeGraphImportEdge,
    KnowledgeGraphImportNode,
    KnowledgeProperty,
    KnowledgeRelationship,
)

if TYPE_CHECKING:
    pass


def _normalized(value: str) -> str:
    """Normalize text for fuzzy matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


class KnowledgeGraphRepository:
    """Repository for Knowledge Graph entities (aliases, properties, relationships)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Stats ---

    def stats(self) -> dict:
        """Return aggregate statistics for the knowledge graph."""
        entity_count = self.db.scalar(select(func.count(KnowledgeEntity.id)))
        alias_count = self.db.scalar(select(func.count(KnowledgeAlias.id)))
        relationship_count = self.db.scalar(select(func.count(KnowledgeRelationship.id)))
        return {
            "entity_count": entity_count or 0,
            "alias_count": alias_count or 0,
            "relationship_count": relationship_count or 0,
        }

    # --- Entities ---

    def list_entities(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[KnowledgeEntity], int]:
        """List entities with optional filters and pagination."""
        query = select(KnowledgeEntity)
        count_query = select(func.count(KnowledgeEntity.id))

        if search:
            norm = _normalized(search)
            like_pattern = f"%{norm}%"
            query = query.where(
                (KnowledgeEntity.normalized_name.ilike(like_pattern))
                | (KnowledgeEntity.id.ilike(like_pattern))
            )
            count_query = count_query.where(
                (KnowledgeEntity.normalized_name.ilike(like_pattern))
                | (KnowledgeEntity.id.ilike(like_pattern))
            )

        if entity_type:
            query = query.where(KnowledgeEntity.entity_type == entity_type)
            count_query = count_query.where(KnowledgeEntity.entity_type == entity_type)

        if status:
            query = query.where(KnowledgeEntity.status == status)
            count_query = count_query.where(KnowledgeEntity.status == status)

        query = query.order_by(KnowledgeEntity.canonical_name).offset(offset).limit(limit)
        total = self.db.scalar(count_query) or 0
        entities = list(self.db.scalars(query))
        return entities, total

    def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        """Get a single entity by ID."""
        return self.db.get(KnowledgeEntity, entity_id)

    def get_entity_by_name(self, normalized_name: str) -> KnowledgeEntity | None:
        """Get entity by exact normalized name."""
        return self.db.scalars(
            select(KnowledgeEntity).where(
                KnowledgeEntity.normalized_name == normalized_name
            )
        ).first()

    def upsert_entity(
        self,
        entity_id: str,
        canonical_name: str,
        entity_type: str,
        status: str = "draft",
    ) -> KnowledgeEntity:
        """Create or update an entity."""
        normalized = _normalized(canonical_name)
        entity = self.db.get(KnowledgeEntity, entity_id)
        if entity:
            entity.canonical_name = canonical_name
            entity.normalized_name = normalized
            entity.entity_type = entity_type
            entity.status = status
            entity.updated_at = datetime.now(timezone.utc)
        else:
            entity = KnowledgeEntity(
                id=entity_id,
                canonical_name=canonical_name,
                normalized_name=normalized,
                entity_type=entity_type,
                status=status,
            )
            self.db.add(entity)
        self.db.flush()
        return entity

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and cascade to aliases/properties/relationships."""
        entity = self.db.get(KnowledgeEntity, entity_id)
        if entity is None:
            return False
        self.db.delete(entity)
        self.db.flush()
        return True

    # --- Aliases ---

    def get_aliases_for_entity(self, entity_id: str) -> list[KnowledgeAlias]:
        """Get all aliases for an entity."""
        return list(
            self.db.scalars(
                select(KnowledgeAlias).where(KnowledgeAlias.entity_id == entity_id)
            )
        )

    def get_alias_by_name(self, normalized_alias: str) -> KnowledgeAlias | None:
        """Get alias by exact normalized name."""
        return self.db.scalars(
            select(KnowledgeAlias).where(
                KnowledgeAlias.normalized_alias == normalized_alias
            )
        ).first()

    def upsert_alias(self, entity_id: str, alias: str, language: str = "en") -> KnowledgeAlias:
        """Create or update an alias for an entity."""
        normalized = _normalized(alias)
        existing = self.db.scalars(
            select(KnowledgeAlias).where(
                KnowledgeAlias.entity_id == entity_id,
                KnowledgeAlias.alias == alias,
            )
        ).first()
        if existing:
            existing.normalized_alias = normalized
            existing.language = language
            return existing
        alias_record = KnowledgeAlias(
            entity_id=entity_id,
            alias=alias,
            normalized_alias=normalized,
            language=language,
        )
        self.db.add(alias_record)
        self.db.flush()
        return alias_record

    def delete_alias(self, alias_id: int) -> bool:
        """Delete an alias by ID."""
        alias = self.db.get(KnowledgeAlias, alias_id)
        if alias is None:
            return False
        self.db.delete(alias)
        self.db.flush()
        return True

    # --- Properties ---

    def get_properties_for_entity(self, entity_id: str) -> list[KnowledgeProperty]:
        """Get all properties for an entity."""
        return list(
            self.db.scalars(
                select(KnowledgeProperty).where(
                    KnowledgeProperty.entity_id == entity_id
                )
            )
        )

    def upsert_property(
        self,
        entity_id: str,
        key: str,
        value: str,
        source: str | None = None,
    ) -> KnowledgeProperty:
        """Create or update a property for an entity."""
        existing = self.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
                KnowledgeProperty.key == key,
            )
        ).first()
        if existing:
            existing.value = value
            existing.source = source
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        prop = KnowledgeProperty(
            entity_id=entity_id,
            key=key,
            value=value,
            source=source,
        )
        self.db.add(prop)
        self.db.flush()
        return prop

    def delete_property(self, property_id: int) -> bool:
        """Delete a property by ID."""
        prop = self.db.get(KnowledgeProperty, property_id)
        if prop is None:
            return False
        self.db.delete(prop)
        self.db.flush()
        return True

    # --- Relationships ---

    def list_relationships(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        relationship: str | None = None,
        from_entity_id: str | None = None,
        to_entity_id: str | None = None,
        search: str | None = None,
    ) -> tuple[list[KnowledgeRelationship], int]:
        """List relationships with optional filters."""
        query = select(KnowledgeRelationship)
        count_query = select(func.count(KnowledgeRelationship.id))

        if relationship:
            query = query.where(KnowledgeRelationship.relationship == relationship)
            count_query = count_query.where(
                KnowledgeRelationship.relationship == relationship
            )
        if from_entity_id:
            query = query.where(KnowledgeRelationship.from_entity_id == from_entity_id)
            count_query = count_query.where(
                KnowledgeRelationship.from_entity_id == from_entity_id
            )
        if to_entity_id:
            query = query.where(KnowledgeRelationship.to_entity_id == to_entity_id)
            count_query = count_query.where(
                KnowledgeRelationship.to_entity_id == to_entity_id
            )
        if search:
            like_pattern = f"%{search}%"
            query = query.where(
                (KnowledgeRelationship.from_entity_id.ilike(like_pattern))
                | (KnowledgeRelationship.to_entity_id.ilike(like_pattern))
                | (KnowledgeRelationship.relationship.ilike(like_pattern))
            )
            count_query = count_query.where(
                (KnowledgeRelationship.from_entity_id.ilike(like_pattern))
                | (KnowledgeRelationship.to_entity_id.ilike(like_pattern))
                | (KnowledgeRelationship.relationship.ilike(like_pattern))
            )

        query = query.order_by(KnowledgeRelationship.id).offset(offset).limit(limit)
        total = self.db.scalar(count_query) or 0
        relationships = list(self.db.scalars(query))
        return relationships, total

    def get_relationship(
        self,
        from_entity_id: str,
        relationship: str,
        to_entity_id: str,
    ) -> KnowledgeRelationship | None:
        """Get a specific relationship by its unique key."""
        return self.db.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.from_entity_id == from_entity_id,
                KnowledgeRelationship.relationship == relationship,
                KnowledgeRelationship.to_entity_id == to_entity_id,
            )
        ).first()

    def upsert_relationship(
        self,
        from_entity_id: str,
        relationship: str,
        to_entity_id: str,
        recommendations: dict | None = None,
        source: str | None = None,
    ) -> KnowledgeRelationship:
        """Create or update a relationship."""
        existing = self.get_relationship(from_entity_id, relationship, to_entity_id)
        if existing:
            if recommendations is not None:
                existing.recommendations = recommendations
            if source and source not in (existing.source or ""):
                existing.source = (
                    f"{existing.source} | {source}" if existing.source else source
                )
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        rel = KnowledgeRelationship(
            from_entity_id=from_entity_id,
            relationship=relationship,
            to_entity_id=to_entity_id,
            recommendations=recommendations,
            source=source,
        )
        self.db.add(rel)
        self.db.flush()
        return rel

    def delete_relationship(self, relationship_id: int) -> bool:
        """Delete a relationship by ID."""
        rel = self.db.get(KnowledgeRelationship, relationship_id)
        if rel is None:
            return False
        self.db.delete(rel)
        self.db.flush()
        return True

    # --- Entity detail with pagination ---

    def get_entity_detail(
        self,
        entity_id: str,
        *,
        alias_offset: int = 0,
        alias_limit: int = 50,
        property_offset: int = 0,
        property_limit: int = 50,
    ) -> dict | None:
        """Get entity with paginated aliases and properties."""
        entity = self.db.get(KnowledgeEntity, entity_id)
        if entity is None:
            return None

        alias_query = (
            select(KnowledgeAlias)
            .where(KnowledgeAlias.entity_id == entity_id)
            .order_by(KnowledgeAlias.id)
            .offset(alias_offset)
            .limit(alias_limit)
        )
        alias_total = self.db.scalar(
            select(func.count(KnowledgeAlias.id)).where(
                KnowledgeAlias.entity_id == entity_id
            )
        ) or 0

        property_query = (
            select(KnowledgeProperty)
            .where(KnowledgeProperty.entity_id == entity_id)
            .order_by(KnowledgeProperty.id)
            .offset(property_offset)
            .limit(property_limit)
        )
        property_total = self.db.scalar(
            select(func.count(KnowledgeProperty.id)).where(
                KnowledgeProperty.entity_id == entity_id
            )
        ) or 0

        return {
            "entity": entity,
            "aliases": list(self.db.scalars(alias_query)),
            "alias_total": alias_total,
            "alias_has_more": alias_offset + len(list(self.db.scalars(alias_query))) < alias_total,
            "properties": list(self.db.scalars(property_query)),
            "property_total": property_total,
            "property_has_more": property_offset + len(list(self.db.scalars(property_query))) < property_total,
        }

    # --- Matching helpers (limited queries) ---

    def find_exact_name_match(self, canonical_name: str) -> KnowledgeEntity | None:
        """Find entity by exact normalized name."""
        normalized = _normalized(canonical_name)
        return self.db.scalars(
            select(KnowledgeEntity).where(
                KnowledgeEntity.normalized_name == normalized
            )
        ).first()

    def find_exact_alias_match(self, alias: str) -> KnowledgeAlias | None:
        """Find alias by exact normalized alias."""
        normalized = _normalized(alias)
        return self.db.scalars(
            select(KnowledgeAlias).where(
                KnowledgeAlias.normalized_alias == normalized
            )
        ).first()

    def find_fuzzy_entity_candidates(
        self,
        normalized_name: str,
        limit: int = 5,
    ) -> list[KnowledgeEntity]:
        """Find fuzzy matching entities (exact prefix match)."""
        pattern = f"{normalized_name}%"
        return list(
            self.db.scalars(
                select(KnowledgeEntity)
                .where(KnowledgeEntity.normalized_name.ilike(pattern))
                .limit(limit)
            )
        )

    def entity_exists(self, entity_id: str) -> bool:
        """Check if entity exists."""
        return self.db.get(KnowledgeEntity, entity_id) is not None

    def relationship_exists(
        self,
        from_entity_id: str,
        relationship: str,
        to_entity_id: str,
    ) -> bool:
        """Check if relationship exists."""
        return (
            self.get_relationship(from_entity_id, relationship, to_entity_id) is not None
        )
