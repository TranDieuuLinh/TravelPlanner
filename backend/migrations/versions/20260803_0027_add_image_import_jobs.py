"""allow OCR images to use the persistent import-job queue

Revision ID: 20260803_0027
Revises: 20260802_0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260803_0027"
down_revision: str | None = "20260802_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_import_jobs",
        sa.Column("source_type", sa.String(length=16), server_default="url", nullable=False),
    )
    op.add_column("url_import_jobs", sa.Column("source_name", sa.String(length=255), nullable=True))
    op.add_column("url_import_jobs", sa.Column("image_mime_type", sa.String(length=64), nullable=True))
    op.add_column("url_import_jobs", sa.Column("image_data", sa.LargeBinary(), nullable=True))
    op.create_index("ix_url_import_jobs_source_type", "url_import_jobs", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_url_import_jobs_source_type", table_name="url_import_jobs")
    op.drop_column("url_import_jobs", "image_data")
    op.drop_column("url_import_jobs", "image_mime_type")
    op.drop_column("url_import_jobs", "source_name")
    op.drop_column("url_import_jobs", "source_type")
