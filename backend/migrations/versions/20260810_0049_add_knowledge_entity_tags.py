"""add provenance-aware knowledge entity tags

Revision ID: 20260810_0049
Revises: 20260810_0048
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260810_0049"
down_revision: str | None = "20260810_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TAG_DEFINITIONS = (
    ("indoor", "setting", "Trong nhà", "Indoor", "low"),
    ("outdoor", "setting", "Ngoài trời", "Outdoor", "low"),
    ("rooftop", "setting", "Sân thượng", "Rooftop", "low"),
    ("night_view", "setting", "Ngắm cảnh đêm", "Night view", "medium"),
    ("weather_sensitive", "constraint", "Phụ thuộc thời tiết", "Weather sensitive", "low"),
    ("fixed_schedule", "operations", "Lịch cố định", "Fixed schedule", "medium"),
    ("ticketed", "operations", "Cần vé", "Ticketed", "medium"),
    ("free", "operations", "Miễn phí", "Free", "medium"),
    ("reservation_recommended", "operations", "Nên đặt trước", "Reservation recommended", "medium"),
    ("late_night", "operations", "Mở khuya", "Late night", "low"),
    ("family_friendly", "audience", "Phù hợp gia đình", "Family friendly", "medium"),
    ("adult_only", "audience", "Chỉ dành cho người lớn", "Adults only", "high"),
    ("adult_optional", "audience", "Thiên về người lớn", "Adult oriented", "medium"),
    ("group_friendly", "audience", "Phù hợp nhóm", "Group friendly", "low"),
    ("couples", "audience", "Phù hợp cặp đôi", "Couples", "medium"),
    ("solo_friendly", "audience", "Phù hợp đi một mình", "Solo friendly", "medium"),
    ("quiet", "ambience", "Yên tĩnh", "Quiet", "medium"),
    ("lively", "ambience", "Sôi động", "Lively", "medium"),
    ("crowded", "ambience", "Đông đúc", "Crowded", "medium"),
    ("romantic", "ambience", "Lãng mạn", "Romantic", "medium"),
    ("local", "ambience", "Địa phương", "Local", "medium"),
    ("touristy", "ambience", "Phổ biến với du khách", "Touristy", "medium"),
    ("street_food", "food_drink", "Ẩm thực đường phố", "Street food", "low"),
    ("bar", "food_drink", "Quán bar", "Bar", "low"),
    ("cocktail", "food_drink", "Cocktail", "Cocktail", "low"),
    ("beer", "food_drink", "Bia", "Beer", "low"),
    ("alcohol", "food_drink", "Đồ uống có cồn", "Alcohol", "low"),
    ("non_alcoholic", "food_drink", "Không cồn", "Non-alcoholic", "medium"),
    ("coffee", "food_drink", "Cà phê", "Coffee", "low"),
    ("local_food", "food_drink", "Ẩm thực địa phương", "Local food", "medium"),
    ("performance", "activity", "Biểu diễn", "Performance", "low"),
    ("live_music", "activity", "Nhạc sống", "Live music", "medium"),
    ("acoustic", "activity", "Nhạc acoustic", "Acoustic", "medium"),
    ("jazz", "activity", "Nhạc jazz", "Jazz", "low"),
    ("spa", "activity", "Spa", "Spa", "low"),
    ("massage", "activity", "Massage", "Massage", "low"),
    ("market", "activity", "Chợ", "Market", "low"),
    ("shopping", "activity", "Mua sắm", "Shopping", "low"),
    ("walking", "activity", "Đi bộ", "Walking", "low"),
    ("guided_tour", "activity", "Tour có hướng dẫn", "Guided tour", "medium"),
    ("karaoke", "activity", "Karaoke", "Karaoke", "low"),
)


def upgrade() -> None:
    tags = op.create_table(
        "knowledge_tags",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("tag_group", sa.String(length=32), nullable=False),
        sa.Column("display_name_vi", sa.String(length=128), nullable=False),
        sa.Column("display_name_en", sa.String(length=128), nullable=False),
        sa.Column("applicable_entity_types", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_knowledge_tags_tag_group", "knowledge_tags", ["tag_group"])

    op.create_table(
        "knowledge_tag_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("tagged_count", sa.Integer(), nullable=False),
        sa.Column("no_evidence_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_tag_runs_status", "knowledge_tag_runs", ["status"])

    op.create_table(
        "knowledge_entity_tag_assertions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("tag_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("inference_run_id", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_key"], ["knowledge_tags.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inference_run_id"], ["knowledge_tag_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "tag_key", "source", name="uq_knowledge_entity_tag_assertion"),
    )
    op.create_index("ix_knowledge_entity_tag_assertions_entity_id", "knowledge_entity_tag_assertions", ["entity_id"])
    op.create_index("ix_knowledge_entity_tag_assertions_tag_key", "knowledge_entity_tag_assertions", ["tag_key"])
    op.create_index("ix_knowledge_entity_tag_assertions_status", "knowledge_entity_tag_assertions", ["status"])
    op.create_index("ix_knowledge_entity_tag_assertions_inference_run_id", "knowledge_entity_tag_assertions", ["inference_run_id"])
    op.create_index("ix_knowledge_entity_tag_effective", "knowledge_entity_tag_assertions", ["entity_id", "status", "confidence"])

    op.create_table(
        "knowledge_tag_scan_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("assertion_count", sa.Integer(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["knowledge_tag_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "entity_id", name="uq_knowledge_tag_scan_run_entity"),
    )
    op.create_index("ix_knowledge_tag_scan_results_run_id", "knowledge_tag_scan_results", ["run_id"])
    op.create_index("ix_knowledge_tag_scan_results_entity_id", "knowledge_tag_scan_results", ["entity_id"])

    op.bulk_insert(
        tags,
        [
            {
                "key": key,
                "tag_group": group,
                "display_name_vi": vi,
                "display_name_en": en,
                "applicable_entity_types": [
                    "TravelPlace", "Restaurant", "DrinkDessert", "Accommodation",
                    "Cafe", "Hotel", "Shop", "Attraction", "Entertainment",
                ],
                "risk_level": risk,
            }
            for key, group, vi, en, risk in TAG_DEFINITIONS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_tag_scan_results_entity_id", table_name="knowledge_tag_scan_results")
    op.drop_index("ix_knowledge_tag_scan_results_run_id", table_name="knowledge_tag_scan_results")
    op.drop_table("knowledge_tag_scan_results")
    op.drop_index("ix_knowledge_entity_tag_effective", table_name="knowledge_entity_tag_assertions")
    op.drop_index("ix_knowledge_entity_tag_assertions_inference_run_id", table_name="knowledge_entity_tag_assertions")
    op.drop_index("ix_knowledge_entity_tag_assertions_status", table_name="knowledge_entity_tag_assertions")
    op.drop_index("ix_knowledge_entity_tag_assertions_tag_key", table_name="knowledge_entity_tag_assertions")
    op.drop_index("ix_knowledge_entity_tag_assertions_entity_id", table_name="knowledge_entity_tag_assertions")
    op.drop_table("knowledge_entity_tag_assertions")
    op.drop_index("ix_knowledge_tag_runs_status", table_name="knowledge_tag_runs")
    op.drop_table("knowledge_tag_runs")
    op.drop_index("ix_knowledge_tags_tag_group", table_name="knowledge_tags")
    op.drop_table("knowledge_tags")
