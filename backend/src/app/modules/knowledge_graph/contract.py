from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class KGModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class KGStats(KGModel):
    entity_count: int
    alias_count: int
    relationship_count: int


class EntitySummary(KGModel):
    id: str
    canonical_name: str
    entity_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    review_count: int | None = None


class EntityListPage(KGModel):
    items: list[EntitySummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class EntityFilterOptions(KGModel):
    entity_types: list[str]
    statuses: list[str]
    property_keys: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)


class AliasDetail(KGModel):
    id: int
    alias: str
    language: str
    created_at: datetime


class PropertyDetail(KGModel):
    id: int
    key: str
    value: str
    source: str | None = None
    updated_at: datetime


class RelationshipSummary(KGModel):
    id: int
    from_entity_id: str
    relationship: str
    to_entity_id: str
    source: str | None = None
    created_at: datetime


class EntityDetail(EntitySummary):
    aliases: list[AliasDetail]
    alias_total: int
    alias_has_more: bool
    properties: list[PropertyDetail]
    property_total: int
    property_has_more: bool
    relationships: list[RelationshipSummary]
    relationship_total: int
    relationship_has_more: bool


class EntityCreate(KGModel):
    entity_id: str = Field(min_length=1, max_length=200)
    canonical_name: str = Field(min_length=1, max_length=500)
    entity_type: str = Field(min_length=1, max_length=100)
    status: str = Field(default="draft", min_length=1, max_length=40)


class EntityCopy(KGModel):
    entity_id: str = Field(min_length=1, max_length=200)
    canonical_name: str = Field(min_length=1, max_length=500)


class EntityUpdate(KGModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=500)
    entity_type: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, min_length=1, max_length=40)


class AliasUpsert(KGModel):
    alias: str = Field(min_length=1, max_length=500)
    language: str = Field(default="und", min_length=2, max_length=16)


class PropertyUpsert(KGModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=10000)
    source: str | None = Field(default=None, max_length=2000)


class RelationshipUpsert(KGModel):
    from_entity_id: str | None = Field(default=None, min_length=1, max_length=200)
    relationship: str = Field(min_length=1, max_length=100)
    to_entity_id: str = Field(min_length=1, max_length=200)
    source: str | None = Field(default=None, max_length=2000)
    recommendations: dict[str, object] | None = None


class DeleteResponse(KGModel):
    deleted_entity_id: str | None = None
    deleted_alias_id: int | None = None
    deleted_property_id: int | None = None
    deleted_relationship_id: int | None = None


class LowReviewResponse(KGModel):
    threshold: int
    entity_count: int
    deleted_entity_count: int | None = None
