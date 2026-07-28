"""add person c marketplace tables

Revision ID: 20260727_0003
Revises: 20260727_0002
Create Date: 2026-07-27 17:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260727_0003"
down_revision: str | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketplace_plans",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("current_published_version_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_plans_creator_id", "marketplace_plans", ["creator_id"])
    op.create_index("ix_marketplace_plans_current_published_version_id", "marketplace_plans", ["current_published_version_id"])
    op.create_index("ix_marketplace_plans_status", "marketplace_plans", ["status"])

    op.create_table(
        "marketplace_plan_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_plan_id", sa.String(length=128), nullable=False),
        sa.Column("source_plan_version_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("destination", sa.String(length=160), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("price_amount", sa.Integer(), nullable=False),
        sa.Column("price_currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("media_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("preview_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("moderation_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marketplace_plan_id", "version", name="uq_marketplace_plan_versions_plan_version"),
    )
    op.create_index("ix_marketplace_plan_versions_category", "marketplace_plan_versions", ["category"])
    op.create_index("ix_marketplace_plan_versions_destination", "marketplace_plan_versions", ["destination"])
    op.create_index("ix_marketplace_plan_versions_marketplace_plan_id", "marketplace_plan_versions", ["marketplace_plan_id"])
    op.create_index("ix_marketplace_plan_versions_moderation_status", "marketplace_plan_versions", ["moderation_status"])
    op.create_index("ix_marketplace_plan_versions_price_amount", "marketplace_plan_versions", ["price_amount"])
    op.create_index("ix_marketplace_plan_versions_source_plan_id", "marketplace_plan_versions", ["source_plan_id"])
    op.create_index("ix_marketplace_plan_versions_source_plan_version_id", "marketplace_plan_versions", ["source_plan_version_id"])

    op.create_table(
        "favorites",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "marketplace_plan_id"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("provider_request_id"),
    )
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_version_id", sa.String(length=64), nullable=False),
        sa.Column("unit_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["marketplace_plan_version_id"], ["marketplace_plan_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_marketplace_plan_id", "order_items", ["marketplace_plan_id"])
    op.create_index("ix_order_items_marketplace_plan_version_id", "order_items", ["marketplace_plan_version_id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("transaction_id", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("transaction_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_payment_events_provider_event"),
    )
    op.create_index("ix_payment_events_order_id", "payment_events", ["order_id"])
    op.create_index("ix_payment_events_request_id", "payment_events", ["request_id"])
    op.create_index("ix_payment_events_transaction_id", "payment_events", ["transaction_id"])

    op.create_table(
        "entitlements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("order_item_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_version_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("copied_plan_id", sa.String(length=128), nullable=True),
        sa.Column("copied_plan_version_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["marketplace_plan_version_id"], ["marketplace_plan_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_item_id", name="uq_entitlements_order_item"),
    )
    op.create_index("ix_entitlements_marketplace_plan_version_id", "entitlements", ["marketplace_plan_version_id"])
    op.create_index("ix_entitlements_order_id", "entitlements", ["order_id"])
    op.create_index("ix_entitlements_status", "entitlements", ["status"])
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_version_id", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marketplace_plan_version_id"], ["marketplace_plan_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reviewer_id", "marketplace_plan_id", name="uq_reviews_reviewer_plan"),
    )
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("marketplace_plan_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace_plan_version_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["marketplace_plan_id"], ["marketplace_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marketplace_plan_version_id"], ["marketplace_plan_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_reason", "reports", ["reason"])
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_status", "reports", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_reporter_id", table_name="reports")
    op.drop_index("ix_reports_reason", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_reviews_reviewer_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_entitlements_user_id", table_name="entitlements")
    op.drop_index("ix_entitlements_status", table_name="entitlements")
    op.drop_index("ix_entitlements_order_id", table_name="entitlements")
    op.drop_index("ix_entitlements_marketplace_plan_version_id", table_name="entitlements")
    op.drop_table("entitlements")

    op.drop_index("ix_payment_events_transaction_id", table_name="payment_events")
    op.drop_index("ix_payment_events_request_id", table_name="payment_events")
    op.drop_index("ix_payment_events_order_id", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_index("ix_order_items_marketplace_plan_version_id", table_name="order_items")
    op.drop_index("ix_order_items_marketplace_plan_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_table("orders")

    op.drop_table("favorites")

    op.drop_index("ix_marketplace_plan_versions_source_plan_version_id", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_source_plan_id", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_price_amount", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_moderation_status", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_marketplace_plan_id", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_destination", table_name="marketplace_plan_versions")
    op.drop_index("ix_marketplace_plan_versions_category", table_name="marketplace_plan_versions")
    op.drop_table("marketplace_plan_versions")

    op.drop_index("ix_marketplace_plans_status", table_name="marketplace_plans")
    op.drop_index("ix_marketplace_plans_current_published_version_id", table_name="marketplace_plans")
    op.drop_index("ix_marketplace_plans_creator_id", table_name="marketplace_plans")
    op.drop_table("marketplace_plans")
