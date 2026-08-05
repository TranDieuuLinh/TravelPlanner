"""add optional note metadata to knowledge graph properties

Revision ID: 20260805_0032
Revises: 20260805_0031
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0032"
down_revision: str | None = "20260805_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    # The relational Knowledge Graph was imported independently of the current
    # Alembic history. Keep fresh installations safe while migrating databases
    # that already contain the table represented by database/kg_dump.sql.
    if _has_table("knowledge_properties") and not _has_column(
        "knowledge_properties", "note"
    ):
        op.add_column(
            "knowledge_properties",
            sa.Column("note", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_table("knowledge_properties") and _has_column(
        "knowledge_properties", "note"
    ):
        op.drop_column("knowledge_properties", "note")
