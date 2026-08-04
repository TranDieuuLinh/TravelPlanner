from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: "".join(
            [value.split("_")[0], *[part.title() for part in value.split("_")[1:]]]
        ),
        populate_by_name=True,
    )


class GraphImportCreate(CamelModel):
    source_label: str = Field(min_length=2, max_length=255)
    source_url: str | None = Field(default=None, max_length=2048)
    content: str = Field(min_length=20, max_length=50_000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("sourceUrl must be an absolute HTTP(S) URL")
        return value


class ExtractedNode(BaseModel):
    temp_id: str = Field(alias="tempId", min_length=1, max_length=80)
    entity_id: str = Field(alias="entityId", min_length=1, max_length=96)
    type: str = Field(min_length=1, max_length=80)
    canonical_name: str = Field(alias="canonicalName", min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    properties: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("aliases", "evidence")
    @classmethod
    def clean_text_list(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ExtractedEdge(BaseModel):
    temp_id: str = Field(alias="tempId", min_length=1, max_length=80)
    from_ref: str = Field(alias="fromRef", min_length=1, max_length=80)
    relationship: str = Field(min_length=1, max_length=80)
    to_ref: str = Field(alias="toRef", min_length=1, max_length=80)
    recommendations: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    source: str = Field(min_length=1, max_length=2048)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ExtractionOutput(BaseModel):
    nodes: list[ExtractedNode] = Field(default_factory=list, max_length=200)
    edges: list[ExtractedEdge] = Field(default_factory=list, max_length=400)
    warnings: list[str] = Field(default_factory=list, max_length=50)

    model_config = ConfigDict(extra="forbid")


class MatchCandidate(CamelModel):
    entity_id: str
    canonical_name: str
    type: str
    score: int = Field(ge=0, le=100)
    matched_rules: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ProposedNodeRead(CamelModel):
    temp_id: str
    entity_id: str
    type: str
    canonical_name: str
    aliases: list[str]
    properties: dict[str, str]
    evidence: list[str]
    confidence: float
    match_status: Literal["existing", "possible_duplicate", "new", "conflict"]
    match_candidates: list[MatchCandidate]
    selected_entity_id: str | None = None
    decision: Literal["pending", "approve_create", "approve_existing", "reject"] = "pending"
    validation_issues: list[str] = Field(default_factory=list)
    required_properties: list[str] = Field(default_factory=list)
    optional_properties: list[str] = Field(default_factory=list)


class ProposedEdgeRead(CamelModel):
    temp_id: str
    from_ref: str
    relationship: str
    to_ref: str
    recommendations: list[dict[str, object]]
    source: str
    evidence: list[str]
    confidence: float
    match_status: Literal["existing", "new", "needs_review", "invalid"]
    decision: Literal["pending", "approve_create", "approve_existing", "reject"] = "pending"
    validation_issues: list[str] = Field(default_factory=list)


class GraphImportSummary(CamelModel):
    id: str
    source_label: str
    source_url: str | None
    status: Literal["extracting", "needs_review", "applied", "failed"]
    node_count: int
    edge_count: int
    issue_count: int
    created_at: str
    applied_at: str | None = None
    error_message: str | None = None


class GraphImportDetail(GraphImportSummary):
    source_content: str
    schema_version: str
    ontology_version: str
    dataset_hash: str
    warnings: list[str]
    nodes: list[ProposedNodeRead]
    edges: list[ProposedEdgeRead]


class ProposedNodeUpdate(CamelModel):
    entity_id: str = Field(min_length=1, max_length=96)
    type: str = Field(min_length=1, max_length=80)
    canonical_name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    properties: dict[str, str] = Field(default_factory=dict)
    selected_entity_id: str | None = Field(default=None, max_length=96)
    decision: Literal["pending", "approve_create", "approve_existing", "reject"]


class ProposedEdgeUpdate(CamelModel):
    from_ref: str = Field(min_length=1, max_length=80)
    relationship: str = Field(min_length=1, max_length=80)
    to_ref: str = Field(min_length=1, max_length=80)
    recommendations: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    source: str = Field(min_length=1, max_length=2048)
    decision: Literal["pending", "approve_create", "approve_existing", "reject"]


class GraphImportList(CamelModel):
    items: list[GraphImportSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class GraphImportListQuery(CamelModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: Literal["extracting", "needs_review", "applied", "failed"] | None = None
    search: str | None = Field(default=None, max_length=120)


class GraphImportMeta(GraphImportSummary):
    """Summary + provenance metadata. No nodes/edges to keep payload small."""

    source_content: str
    schema_version: str
    ontology_version: str
    dataset_hash: str
    warnings: list[str]


class ProposedNodePage(CamelModel):
    items: list[ProposedNodeRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class ProposedEdgePage(CamelModel):
    items: list[ProposedEdgeRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class ProposedNodePageQuery(CamelModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ProposedEdgePageQuery(CamelModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ProposedNodeMutation(CamelModel):
    """Returned by write endpoints that change a single node."""

    summary: GraphImportSummary
    meta: GraphImportMeta
    node: ProposedNodeRead


class ProposedEdgeMutation(CamelModel):
    """Returned by write endpoints that change a single edge."""

    summary: GraphImportSummary
    meta: GraphImportMeta
    edge: ProposedEdgeRead


class DeleteNodeResponse(CamelModel):
    deleted_temp_id: str


class DeleteEdgeResponse(CamelModel):
    deleted_temp_id: str


class DeleteImportResponse(CamelModel):
    deleted_import_id: str
