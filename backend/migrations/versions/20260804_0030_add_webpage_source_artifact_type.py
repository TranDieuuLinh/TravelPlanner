"""allow normalized webpage evidence artifacts

Revision ID: 20260804_0030
Revises: 20260802_0016
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260804_0030"
down_revision: str | None = "20260802_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("url_source_artifacts") as batch_op:
        batch_op.drop_constraint(
            "ck_url_source_artifacts_type",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_url_source_artifacts_type",
            "artifact_type IN ('webpage', 'caption', 'stt', 'ocr')",
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM url_source_artifacts WHERE artifact_type = 'webpage'"
    )
    with op.batch_alter_table("url_source_artifacts") as batch_op:
        batch_op.drop_constraint(
            "ck_url_source_artifacts_type",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_url_source_artifacts_type",
            "artifact_type IN ('caption', 'stt', 'ocr')",
        )
