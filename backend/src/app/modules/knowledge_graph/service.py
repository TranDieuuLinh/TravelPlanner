from __future__ import annotations

from dataclasses import dataclass

from app.modules.knowledge_graph.adapters.postgres import PostgresKnowledgeGraphStore
from app.modules.knowledge_graph.contract import (
    AliasUpsert,
    AutoAttachRule,
    EntityCreate,
    EntityUpdate,
    PropertyUpsert,
    RelationshipUpsert,
)


@dataclass
class KnowledgeGraphError(Exception):
    status_code: int
    code: str
    message: str


class KnowledgeGraphService:
    def __init__(self, store: PostgresKnowledgeGraphStore) -> None:
        self.store = store

    async def stats(self) -> dict:
        return await self.store.stats()

    async def search_stats(self, query: str) -> dict:
        return await self.store.search_stats(query)

    async def get_price_observations(self, region: str, category: str | None = None, currency: str = "VND") -> list[dict]:
        return await self.store.get_price_observations(region, category, currency)

    async def entities(self, **filters) -> tuple[list[dict], int]:
        return await self.store.list_entities(**filters)

    async def entity_filter_options(self) -> dict[str, list[str]]:
        return await self.store.entity_filter_options()

    async def relationships(self, **filters) -> tuple[list[dict], int]:
        return await self.store.list_relationships(**filters)

    async def auto_attach_rules(self) -> list[dict]:
        return await self.store.list_auto_attach_rules()

    async def upsert_auto_attach_rule(self, payload: AutoAttachRule) -> dict:
        try:
            return await self.store.upsert_auto_attach_rule(
                **payload.model_dump(by_alias=False)
            )
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise KnowledgeGraphError(409, "KG_AUTO_ATTACH_EXISTS", "Auto-attach rule Ä‘Ã£ tá»“n táº¡i.") from exc
            raise

    async def delete_auto_attach_rule(self, rule_id: str) -> None:
        if not await self.store.delete_auto_attach_rule(rule_id):
            raise KnowledgeGraphError(404, "KG_AUTO_ATTACH_NOT_FOUND", "KhÃ´ng tÃ¬m tháº¥y auto-attach rule.")

    async def auto_attach_aliases(self) -> list[dict]:
        return await self.store.list_auto_attach_aliases()

    async def upsert_auto_attach_alias(self, keyword: str, aliases: list[str], source: str) -> dict:
        return await self.store.upsert_auto_attach_alias(keyword=keyword, aliases=aliases, source=source)

    async def entity(self, entity_id: str, **limits) -> dict:
        result = await self.store.get_entity(entity_id, **limits)
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result

    async def entity_preview(self, name: str) -> dict:
        result = await self.store.get_entity_preview(name)
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result

    async def entity_preview_by_id(self, entity_id: str) -> dict:
        result = await self.store.get_entity_preview_by_id(entity_id)
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result

    async def create_entity(self, payload: EntityCreate) -> dict:
        try:
            return await self.store.create_entity(**payload.model_dump(by_alias=False))
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise KnowledgeGraphError(409, "KG_ENTITY_EXISTS", "Entity ID đã tồn tại.") from exc
            raise

    async def update_entity(self, entity_id: str, payload: EntityUpdate) -> dict:
        try:
            updates = payload.model_dump(exclude_unset=True, by_alias=False)
            # The URL identifies the entity being updated.  Do not forward the
            # optional body entity_id as a second value for the store argument.
            updates.pop("entity_id", None)
            result = await self.store.update_entity(entity_id, **updates)
        except Exception as exc:
            if any(marker in str(exc).lower() for marker in ("duplicate", "unique", "already exists")):
                raise KnowledgeGraphError(409, "KG_ENTITY_EXISTS", "Entity ID đã tồn tại.") from exc
            raise
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result

    async def delete_entity(self, entity_id: str) -> None:
        if not await self.store.delete_entity(entity_id):
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")

    async def copy_entity(self, entity_id: str, new_id: str, new_name: str) -> dict:
        try:
            result = await self.store.copy_entity(entity_id, new_id, new_name)
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise KnowledgeGraphError(409, "KG_ENTITY_EXISTS", "Entity ID đã tồn tại.") from exc
            raise
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result

    async def alias(self, entity_id: str, payload: AliasUpsert, alias_id: int | None = None) -> dict:
        if alias_id is None:
            result = await self.store.add_alias(entity_id, payload.alias, payload.language)
        else:
            result = await self.store.update_alias(entity_id, alias_id, payload.alias, payload.language)
        return await self._require_detail(result)

    async def delete_alias(self, entity_id: str, alias_id: int) -> None:
        if not await self.store.delete_alias(entity_id, alias_id):
            raise KnowledgeGraphError(404, "KG_ALIAS_NOT_FOUND", "Không tìm thấy alias.")

    async def property(self, entity_id: str, payload: PropertyUpsert, property_id: int | None = None) -> dict:
        if property_id is None:
            result = await self.store.add_property(entity_id, payload.key, payload.value, payload.source)
        else:
            result = await self.store.update_property(entity_id, property_id, payload.key, payload.value, payload.source)
        return await self._require_detail(result)

    async def delete_property(self, entity_id: str, property_id: int) -> None:
        if not await self.store.delete_property(entity_id, property_id):
            raise KnowledgeGraphError(404, "KG_PROPERTY_NOT_FOUND", "Không tìm thấy property.")

    async def relationship(self, entity_id: str, payload: RelationshipUpsert, relationship_id: int | None = None) -> dict:
        from_entity_id = payload.from_entity_id or entity_id
        if relationship_id is None:
            await self.store.add_relationship(from_entity_id, payload.relationship, payload.to_entity_id, payload.source, payload.recommendations)
        else:
            updated = await self.store.update_relationship(
                entity_id,
                relationship_id,
                payload.relationship,
                payload.to_entity_id,
                payload.source,
                payload.recommendations,
                from_entity_id=payload.from_entity_id,
            )
            if updated is None:
                raise KnowledgeGraphError(404, "KG_RELATIONSHIP_NOT_FOUND", "Không tìm thấy relationship.")
        return await self._require_detail(await self.store.get_entity(entity_id))

    async def delete_relationship(self, entity_id: str, relationship_id: int) -> None:
        if not await self.store.delete_relationship(entity_id, relationship_id):
            raise KnowledgeGraphError(404, "KG_RELATIONSHIP_NOT_FOUND", "Không tìm thấy relationship.")

    async def low_review_count(self, threshold: int) -> dict:
        count = await self.store.count_low_review(threshold)
        return {"threshold": threshold, "entity_count": count}

    async def delete_low_review(self, threshold: int) -> dict:
        deleted = await self.store.delete_low_review(threshold)
        return {"threshold": threshold, "entity_count": 0, "deleted_entity_count": deleted}

    async def _require_detail(self, result: dict | None) -> dict:
        if not result:
            raise KnowledgeGraphError(404, "KG_ENTITY_NOT_FOUND", "Không tìm thấy entity.")
        return result
