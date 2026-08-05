"""add knowledge alias provenance and trigram search

Revision ID: 20260805_0035
Revises: 20260805_0034
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0035"
down_revision: str | None = "20260805_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    # Migration 0032 can run before the Knowledge Graph branch creates this
    # table. Reconcile the merged branches here for both fresh and existing DBs.
    if _has_table("knowledge_properties") and "note" not in _columns(
        "knowledge_properties"
    ):
        op.add_column(
            "knowledge_properties",
            sa.Column("note", sa.Text(), nullable=True),
        )

    if not _has_table("knowledge_aliases"):
        return

    columns = _columns("knowledge_aliases")
    additions = (
        ("alias_type", sa.Column(
            "alias_type", sa.String(length=32), nullable=False,
            server_default="alternate_name",
        )),
        ("source", sa.Column("source", sa.Text(), nullable=True)),
        ("provider", sa.Column("provider", sa.String(length=64), nullable=True)),
        ("status", sa.Column(
            "status", sa.String(length=24), nullable=False,
            server_default="imported",
        )),
        ("confidence", sa.Column("confidence", sa.Float(), nullable=True)),
        ("verified_at", sa.Column(
            "verified_at", sa.DateTime(timezone=True), nullable=True,
        )),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("knowledge_aliases", column)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_entities_name_trgm "
            "ON knowledge_entities USING gin (normalized_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_aliases_name_trgm "
            "ON knowledge_aliases USING gin (normalized_alias gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_aliases_name_trgm")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_entities_name_trgm")
    if not _has_table("knowledge_aliases"):
        return
    columns = _columns("knowledge_aliases")
    for name in (
        "verified_at",
        "confidence",
        "status",
        "provider",
        "source",
        "alias_type",
    ):
        if name in columns:
            op.drop_column("knowledge_aliases", name)
