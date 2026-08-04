"""create knowledge graph tables

Revision ID: 20260804_0001
Revises: 20260803_0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260804_0001"
down_revision: str | None = "20260803_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Knowledge Entities ---
    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_entities_normalized_name",
        "knowledge_entities",
        ["normalized_name"],
    )
    op.create_index(
        "ix_knowledge_entities_entity_type",
        "knowledge_entities",
        ["entity_type"],
    )
    op.create_index(
        "ix_knowledge_entities_normalized_type",
        "knowledge_entities",
        ["normalized_name", "entity_type"],
    )

    # --- Knowledge Aliases ---
    op.create_table(
        "knowledge_aliases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column(
            "language",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["knowledge_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "alias", name="uq_knowledge_aliases_entity_alias"),
    )
    op.create_index(
        "ix_knowledge_aliases_entity_id",
        "knowledge_aliases",
        ["entity_id"],
    )
    op.create_index(
        "ix_knowledge_aliases_normalized_alias",
        "knowledge_aliases",
        ["normalized_alias"],
    )

    # --- Knowledge Properties ---
    op.create_table(
        "knowledge_properties",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["knowledge_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "key", name="uq_knowledge_properties_entity_key"),
    )
    op.create_index(
        "ix_knowledge_properties_entity_id",
        "knowledge_properties",
        ["entity_id"],
    )

    # --- Knowledge Relationships ---
    op.create_table(
        "knowledge_relationships",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("from_entity_id", sa.String(length=96), nullable=False),
        sa.Column("relationship", sa.String(length=80), nullable=False),
        sa.Column("to_entity_id", sa.String(length=96), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_entity_id"],
            ["knowledge_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_entity_id"],
            ["knowledge_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_entity_id",
            "relationship",
            "to_entity_id",
            name="uq_knowledge_relationships_edge",
        ),
    )
    op.create_index(
        "ix_knowledge_relationships_from_entity_id",
        "knowledge_relationships",
        ["from_entity_id"],
    )
    op.create_index(
        "ix_knowledge_relationships_to_entity_id",
        "knowledge_relationships",
        ["to_entity_id"],
    )
    op.create_index(
        "ix_knowledge_relationships_relationship",
        "knowledge_relationships",
        ["relationship"],
    )
    op.create_index(
        "ix_knowledge_relationships_from_to",
        "knowledge_relationships",
        ["from_entity_id", "to_entity_id"],
    )

    # --- Knowledge Graph Imports ---
    op.create_table(
        "knowledge_graph_imports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="extracting",
        ),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("ontology_version", sa.String(length=64), nullable=False),
        sa.Column("dataset_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "warnings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "node_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "edge_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "issue_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_dataset_hash", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_graph_imports_status",
        "knowledge_graph_imports",
        ["status"],
    )
    op.create_index(
        "ix_knowledge_graph_imports_created_by",
        "knowledge_graph_imports",
        ["created_by"],
    )
    op.create_index(
        "ix_knowledge_graph_imports_created_at",
        "knowledge_graph_imports",
        ["created_at"],
    )

    # --- Knowledge Graph Import Nodes ---
    op.create_table(
        "knowledge_graph_import_nodes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_id", sa.String(length=64), nullable=False),
        sa.Column("temp_id", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column(
            "aliases",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "properties",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "evidence",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "match_status",
            sa.String(length=32),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "match_candidates",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("selected_entity_id", sa.String(length=96), nullable=True),
        sa.Column(
            "decision",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "validation_issues",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "required_properties",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "optional_properties",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["knowledge_graph_imports.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "temp_id", name="uq_kg_import_nodes"),
    )
    op.create_index(
        "ix_kg_import_nodes_import_id",
        "knowledge_graph_import_nodes",
        ["import_id"],
    )
    op.create_index(
        "ix_kg_import_nodes_import_temp",
        "knowledge_graph_import_nodes",
        ["import_id", "temp_id"],
    )

    # --- Knowledge Graph Import Edges ---
    op.create_table(
        "knowledge_graph_import_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_id", sa.String(length=64), nullable=False),
        sa.Column("temp_id", sa.String(length=80), nullable=False),
        sa.Column("from_ref", sa.String(length=80), nullable=False),
        sa.Column("relationship", sa.String(length=80), nullable=False),
        sa.Column("to_ref", sa.String(length=80), nullable=False),
        sa.Column(
            "recommendations",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("source", sa.String(length=2048), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "match_status",
            sa.String(length=32),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "decision",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "validation_issues",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["knowledge_graph_imports.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "temp_id", name="uq_kg_import_edges"),
    )
    op.create_index(
        "ix_kg_import_edges_import_id",
        "knowledge_graph_import_edges",
        ["import_id"],
    )
    op.create_index(
        "ix_kg_import_edges_import_temp",
        "knowledge_graph_import_edges",
        ["import_id", "temp_id"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_graph_import_edges")
    op.drop_table("knowledge_graph_import_nodes")
    op.drop_table("knowledge_graph_imports")
    op.drop_table("knowledge_relationships")
    op.drop_table("knowledge_properties")
    op.drop_table("knowledge_aliases")
    op.drop_table("knowledge_entities")
