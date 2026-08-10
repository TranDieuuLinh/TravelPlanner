from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PublicModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class InformationFinderInput(PublicModel):
    query: str = Field(min_length=1, max_length=4000)


class SourceReference(PublicModel):
    source_id: str
    title: str
    url: str
    updated_at: datetime
    date_kind: Literal["source_updated_at", "last_fetched_at"]
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    published_at: datetime | None = None


class InformationFinderOutput(PublicModel):
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EmbeddingIdentity(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    model_revision: str | None = None
    dimensions: int = 384


class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    provider: str = "tavily"
    provider_score: float | None = None
    provider_request_id: str | None = None
    provider_external_id: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    provider_request_id: str | None = None


class PreparedChunk(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    content_hash: str
    embedding: list[float]
    embedded_at: datetime


class PreparedSource(BaseModel):
    result: SearchResult
    canonical_url: str
    domain: str
    content_hash: str
    expires_at: datetime
    chunks: list[PreparedChunk]


class RetrievedSource(BaseModel):
    source_id: str
    snapshot_id: str
    title: str
    url: str
    content: str
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    freshness_score: float = 0.0
    provider_score: float | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    last_fetched_at: datetime
    expires_at: datetime
    review_status: Literal["pending", "approved", "rejected"] = "pending"
