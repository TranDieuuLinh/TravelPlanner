"""consolidate Explorer sources and proposals into Knowledge Graph staging

Revision ID: 20260805_0037
Revises: 20260805_0036
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0037"
down_revision: str | None = "20260805_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_source_documents()
    _extend_import_envelope()
    _extend_import_nodes()
    bind = op.get_bind()
    document_ids = _backfill_source_documents(bind)
    _backfill_explorer_intakes(bind)
    _backfill_explorer_nodes(bind, document_ids)
    _backfill_url_jobs(bind, document_ids)
    _drop_legacy_explorer_tables()


def _create_source_documents() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("extracted_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("artifact_hash", sa.String(128), nullable=True),
        sa.Column("extractor_version", sa.String(64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("canonical_url", name="uq_source_documents_canonical_url"),
    )
    op.create_index(
        "ix_source_documents_platform_fetched",
        "source_documents",
        ["platform", "fetched_at"],
    )


def _extend_import_envelope() -> None:
    columns = (
        sa.Column("import_kind", sa.String(32), nullable=False, server_default="knowledge_graph"),
        sa.Column("batch_id", sa.String(64), nullable=True),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="succeeded"),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("chat_id", sa.String(36), nullable=True),
        sa.Column("destination", sa.String(255), nullable=True),
        sa.Column("destination_entity_id", sa.String(96), nullable=True),
        sa.Column("candidate_reviews", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="url"),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("image_mime_type", sa.String(64), nullable=True),
        sa.Column("image_data", sa.LargeBinary(), nullable=True),
        sa.Column("force_refresh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("batch_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_revision", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("explorer_timing", sa.JSON(), nullable=True),
        sa.Column("planner_timing", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in columns:
        op.add_column("knowledge_graph_imports", column)
    op.alter_column("knowledge_graph_imports", "created_by", nullable=True)
    op.create_foreign_key(
        "fk_kg_imports_source_document",
        "knowledge_graph_imports", "source_documents",
        ["source_document_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_kg_imports_chat",
        "knowledge_graph_imports", "trip_chats",
        ["chat_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_kg_imports_destination_entity",
        "knowledge_graph_imports", "knowledge_entities",
        ["destination_entity_id"], ["id"], ondelete="SET NULL",
    )
    for name, columns in (
        ("ix_knowledge_graph_imports_import_kind", ["import_kind"]),
        ("ix_knowledge_graph_imports_batch_id", ["batch_id"]),
        ("ix_knowledge_graph_imports_source_document_id", ["source_document_id"]),
        ("ix_knowledge_graph_imports_processing_status", ["processing_status"]),
        ("ix_knowledge_graph_imports_review_status", ["review_status"]),
        ("ix_knowledge_graph_imports_chat_id", ["chat_id"]),
        ("ix_knowledge_graph_imports_destination_entity_id", ["destination_entity_id"]),
    ):
        op.create_index(name, "knowledge_graph_imports", columns)


def _extend_import_nodes() -> None:
    columns = (
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("candidate_key", sa.String(255), nullable=True),
        sa.Column("candidate_name", sa.String(255), nullable=True),
        sa.Column("search_region", sa.String(255), nullable=True),
        sa.Column("source_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_external_id", sa.String(255), nullable=True),
        sa.Column("provider_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("source_order", sa.Integer(), nullable=True),
        sa.Column("source_day", sa.Integer(), nullable=True),
        sa.Column("source_time_hint", sa.String(64), nullable=True),
        sa.Column("source_activity", sa.Text(), nullable=True),
        sa.Column("source_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("preference_level", sa.String(24), nullable=False, server_default="preferred"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_status", sa.String(32), nullable=False, server_default="unresolved"),
        sa.Column("selection_method", sa.String(32), nullable=True),
    )
    for column in columns:
        op.add_column("knowledge_graph_import_nodes", column)
    op.create_foreign_key(
        "fk_kg_import_nodes_source_document",
        "knowledge_graph_import_nodes", "source_documents",
        ["source_document_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_kg_import_nodes_selected_entity",
        "knowledge_graph_import_nodes", "knowledge_entities",
        ["selected_entity_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_kg_import_nodes_reviewed_by",
        "knowledge_graph_import_nodes", "users",
        ["reviewed_by"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_kg_import_nodes_source_document_id", "knowledge_graph_import_nodes", ["source_document_id"])
    op.create_index("ix_kg_import_nodes_selected_entity_id", "knowledge_graph_import_nodes", ["selected_entity_id"])
    op.create_index("ix_kg_import_nodes_identity_status", "knowledge_graph_import_nodes", ["identity_status"])


def _backfill_source_documents(bind) -> dict[str, str]:
    documents: dict[str, dict] = {}
    artifacts = sa.table(
        "url_source_artifacts",
        sa.column("source_url"), sa.column("platform"), sa.column("artifact_type"),
        sa.column("content_text"), sa.column("language"), sa.column("source"),
        sa.column("metadata"), sa.column("fetched_at"), sa.column("created_at"),
        sa.column("updated_at"),
    )
    for row in bind.execute(sa.select(artifacts)).mappings():
        entry = documents.setdefault(row["source_url"], {
            "platform": row["platform"], "artifacts": {}, "context": {},
            "fetched_at": row["fetched_at"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
        by_language = entry["artifacts"].setdefault(row["artifact_type"], {})
        by_language[row["language"] or "_"] = {
            "text": row["content_text"], "source": row["source"],
            "metadata": row["metadata"] or {},
        }
        if row["fetched_at"] and row["fetched_at"] > entry["fetched_at"]:
            entry["fetched_at"] = row["fetched_at"]

    cache = sa.table(
        "url_extraction_cache", sa.column("source_url"), sa.column("platform"),
        sa.column("extracted_context"), sa.column("fetched_at"), sa.column("updated_at"),
    )
    for row in bind.execute(sa.select(cache)).mappings():
        entry = documents.setdefault(row["source_url"], {
            "platform": row["platform"], "artifacts": {}, "context": {},
            "fetched_at": row["fetched_at"], "created_at": row["fetched_at"],
            "updated_at": row["updated_at"],
        })
        entry["context"] = row["extracted_context"] or {}
        entry["updated_at"] = row["updated_at"]

    youtube_cache = sa.table(
        "youtube_transcript_cache", sa.column("video_id"), sa.column("language"),
        sa.column("transcript_text"), sa.column("source"),
        sa.column("is_generated"), sa.column("fetched_at"), sa.column("updated_at"),
    )
    for row in bind.execute(sa.select(youtube_cache)).mappings():
        url = f"https://www.youtube.com/watch?v={row['video_id']}"
        entry = documents.setdefault(url, {
            "platform": "youtube", "artifacts": {}, "context": {},
            "fetched_at": row["fetched_at"], "created_at": row["fetched_at"],
            "updated_at": row["updated_at"],
        })
        captions = entry["artifacts"].setdefault("caption", {})
        captions[row["language"] or "_"] = {
            "text": row["transcript_text"], "source": row["source"],
            "metadata": {
                "videoId": row["video_id"],
                "isGenerated": row["is_generated"],
            },
        }
        if row["fetched_at"] and row["fetched_at"] > entry["fetched_at"]:
            entry["fetched_at"] = row["fetched_at"]
        if row["updated_at"] and row["updated_at"] > entry["updated_at"]:
            entry["updated_at"] = row["updated_at"]

    target = sa.table(
        "source_documents", sa.column("id"), sa.column("canonical_url"),
        sa.column("platform"), sa.column("artifacts"), sa.column("extracted_context"),
        sa.column("extractor_version"), sa.column("fetched_at"),
        sa.column("created_at"), sa.column("updated_at"),
    )
    ids: dict[str, str] = {}
    for url, value in documents.items():
        document_id = str(uuid5(NAMESPACE_URL, url))
        ids[url] = document_id
        bind.execute(target.insert().values(
            id=document_id, canonical_url=url, platform=value["platform"],
            artifacts=value["artifacts"], extracted_context=value["context"],
            extractor_version="legacy-backfill-v1", fetched_at=value["fetched_at"],
            created_at=value["created_at"], updated_at=value["updated_at"],
        ))
    return ids


def _backfill_explorer_intakes(bind) -> None:
    legacy = sa.table(
        "explorer_intakes", sa.column("id"), sa.column("user_id"),
        sa.column("destination"), sa.column("candidate_reviews"), sa.column("created_at"),
    )
    target = _imports_table()
    node_target = sa.table("knowledge_graph_import_nodes", *[sa.column(name) for name in (
        "import_id", "temp_id", "entity_id", "type", "canonical_name", "aliases",
        "properties", "evidence", "confidence", "match_status", "match_candidates",
        "selected_entity_id", "decision", "validation_issues", "required_properties",
        "optional_properties", "candidate_key", "candidate_name", "search_region",
        "source_evidence", "provider_snapshot", "preference_level", "attributes",
        "identity_status", "created_at", "updated_at",
    )])
    for row in bind.execute(sa.select(legacy)).mappings():
        numeric_user = int(row["user_id"]) if str(row["user_id"] or "").isdigit() else None
        bind.execute(target.insert().values(
            id=row["id"], import_kind="explorer_intake",
            source_label=row["destination"], source_content="", status="succeeded",
            processing_status="succeeded", review_status="pending",
            schema_version="legacy-explorer-v1", ontology_version="knowledge-graph-v2",
            dataset_hash="", warnings=[], node_count=1, edge_count=0, issue_count=0,
            created_by=numeric_user, destination=row["destination"],
            candidate_reviews=row["candidate_reviews"] or [], created_at=row["created_at"],
            updated_at=row["created_at"],
        ))
        area_key = str(uuid5(NAMESPACE_URL, f"area:{row['destination']}"))
        bind.execute(node_target.insert().values(
            import_id=row["id"], temp_id="area-root",
            entity_id=f"area_{area_key.replace('-', '')[:20]}", type="Area",
            canonical_name=row["destination"], aliases=[row["destination"]],
            properties={}, evidence=[], confidence=1.0, match_status="new",
            match_candidates=[], selected_entity_id=None, decision="pending",
            validation_issues=[], required_properties=[], optional_properties=[],
            candidate_key=f"area:{row['destination']}", candidate_name=row["destination"],
            search_region=row["destination"], source_evidence={}, provider_snapshot={},
            preference_level="mentioned", attributes=[], identity_status="unresolved",
            created_at=row["created_at"], updated_at=row["created_at"],
        ))


def _backfill_explorer_nodes(bind, document_ids: dict[str, str]) -> None:
    places = sa.table("user_must_place", *[sa.column(name) for name in (
        "id", "destination", "candidate_key", "candidate_name", "resolved_name",
        "place_type", "category", "address", "city", "latitude", "longitude",
        "provider", "external_id", "source_url", "source_link", "opening_hours",
        "rating", "review_count", "fetched_at", "confidence", "notes", "description",
        "source_evidence", "source_order", "source_day", "source_time_hint",
        "source_activity", "source_duration_minutes", "preference_level", "attributes",
    )])
    links = sa.table(
        "user_must_place_users", sa.column("user_must_place_id"), sa.column("intake_id")
    )
    target = sa.table("knowledge_graph_import_nodes", *[sa.column(name) for name in (
        "import_id", "temp_id", "entity_id", "type", "canonical_name", "aliases",
        "properties", "evidence", "confidence", "match_status", "match_candidates",
        "selected_entity_id", "decision", "validation_issues", "required_properties",
        "optional_properties", "source_document_id", "candidate_key", "candidate_name",
        "search_region", "source_evidence", "provider", "provider_external_id",
        "provider_snapshot", "source_note", "source_order", "source_day",
        "source_time_hint", "source_activity", "source_duration_minutes",
        "preference_level", "attributes", "identity_status", "created_at", "updated_at",
    )])
    edge_target = sa.table("knowledge_graph_import_edges", *[sa.column(name) for name in (
        "import_id", "temp_id", "from_ref", "relationship_type", "to_ref",
        "recommendations", "source", "evidence", "confidence", "match_status",
        "decision", "validation_issues", "created_at", "updated_at",
    )])
    rows = bind.execute(
        sa.select(places, links.c.intake_id).join(
            links, links.c.user_must_place_id == places.c.id
        )
    ).mappings()
    counts: dict[str, int] = defaultdict(lambda: 1)
    for row in rows:
        intake_id = row["intake_id"]
        counts[intake_id] += 1
        snapshot = {
            "status": "resolved", "externalId": row["external_id"],
            "name": row["resolved_name"], "placeType": row["place_type"] or row["category"],
            "address": row["address"], "city": row["city"],
            "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
            "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
            "googleMapsUrl": row["source_link"], "imageUrl": None,
            "openingHours": row["opening_hours"] or [],
            "rating": float(row["rating"]) if row["rating"] is not None else None,
            "reviewCount": row["review_count"],
            "fetchedAt": row["fetched_at"].isoformat() if row["fetched_at"] else None,
        }
        evidence = row["source_evidence"] or {}
        bind.execute(target.insert().values(
            import_id=intake_id, temp_id=f"legacy-{row['id']}",
            entity_id=f"legacy_{row['id']}", type=row["place_type"] or "TravelPlace",
            canonical_name=row["resolved_name"], aliases=[row["candidate_name"]],
            properties={}, evidence=list(evidence.values()), confidence=float(row["confidence"]),
            match_status="new", match_candidates=[], selected_entity_id=None,
            decision="pending", validation_issues=[], required_properties=[], optional_properties=[],
            source_document_id=document_ids.get(row["source_url"]),
            candidate_key=row["candidate_key"], candidate_name=row["candidate_name"],
            search_region=row["destination"], source_evidence=evidence,
            provider=row["provider"], provider_external_id=row["external_id"],
            provider_snapshot=snapshot, source_note=row["notes"] or row["description"],
            source_order=row["source_order"], source_day=row["source_day"],
            source_time_hint=row["source_time_hint"], source_activity=row["source_activity"],
            source_duration_minutes=row["source_duration_minutes"],
            preference_level=row["preference_level"] or "preferred",
            attributes=row["attributes"] or [], identity_status="provider_resolved",
        ))
        bind.execute(edge_target.insert().values(
            import_id=intake_id, temp_id=f"located-in-{row['id']}",
            from_ref=f"legacy-{row['id']}", relationship_type="LOCATED_IN",
            to_ref="area-root", recommendations=[],
            source=row["source_url"] or f"explorer:{intake_id}",
            evidence=list(evidence.values()), confidence=float(row["confidence"]),
            match_status="new", decision="pending", validation_issues=[],
        ))
    imports = sa.table(
        "knowledge_graph_imports", sa.column("id"), sa.column("node_count"),
        sa.column("edge_count"),
    )
    for intake_id, count in counts.items():
        bind.execute(imports.update().where(imports.c.id == intake_id).values(
            node_count=count, edge_count=max(0, count - 1)
        ))


def _backfill_url_jobs(bind, document_ids: dict[str, str]) -> None:
    jobs = sa.table("url_import_jobs", *[sa.column(name) for name in (
        "id", "user_id", "chat_id", "url", "request_content",
        "source_type", "source_name", "image_mime_type", "image_data", "force_refresh",
        "batch_position", "status", "attempt_count", "result_revision", "error_code",
        "error_message", "explorer_timing", "planner_timing", "created_at", "started_at",
        "finished_at", "updated_at",
    )])
    target = _imports_table()
    for row in bind.execute(sa.select(jobs)).mappings():
        url = row["url"] or None
        bind.execute(target.insert().values(
            id=row["id"], import_kind="explorer_job", batch_id=row["id"],
            source_label=row["source_name"] or url or "image",
            source_url=url, source_document_id=document_ids.get(url),
            source_content=row["request_content"], status=row["status"],
            processing_status=row["status"], review_status="not_required",
            schema_version="explorer-place-proposal-v1", ontology_version="knowledge-graph-v2",
            dataset_hash="", warnings=[], node_count=0, edge_count=0, issue_count=0,
            created_by=row["user_id"], chat_id=row["chat_id"],
            source_type=row["source_type"] or "url", source_name=row["source_name"],
            image_mime_type=row["image_mime_type"], image_data=row["image_data"],
            force_refresh=row["force_refresh"], batch_position=row["batch_position"],
            attempt_count=row["attempt_count"], result_revision=row["result_revision"],
            error_code=row["error_code"], error_message=row["error_message"],
            explorer_timing=row["explorer_timing"], planner_timing=row["planner_timing"],
            created_at=row["created_at"], started_at=row["started_at"],
            finished_at=row["finished_at"], updated_at=row["updated_at"],
        ))


def _imports_table():
    return sa.table("knowledge_graph_imports", *[sa.column(name) for name in (
        "id", "import_kind", "batch_id", "source_label", "source_url", "source_document_id",
        "source_content", "status", "processing_status", "review_status", "schema_version",
        "ontology_version", "dataset_hash", "warnings", "node_count", "edge_count",
        "issue_count", "created_by", "chat_id", "destination", "candidate_reviews",
        "source_type", "source_name", "image_mime_type", "image_data", "force_refresh",
        "batch_position", "attempt_count", "result_revision", "error_code", "error_message",
        "explorer_timing", "planner_timing", "created_at", "started_at", "finished_at", "updated_at",
    )])


def _drop_legacy_explorer_tables() -> None:
    for table_name in (
        "user_must_place_users", "user_must_place", "url_import_jobs",
        "explorer_intakes", "url_source_artifacts", "youtube_transcript_cache",
        "url_extraction_cache",
    ):
        op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20260805_0037 is an intentional Explorer data-model cutover; restore "
        "from backup instead of reconstructing the removed cache tables."
    )
