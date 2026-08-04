"""replace places with google-maps derived csv_relational dataset

Revision ID: 20260731_0002
Revises: 20260731_0001
Create Date: 2026-07-31 22:00:00

This migration replaces the schema-13 ``places`` table and the
``reviews`` table that was used for marketplace plan reviews with a new
shape driven by the ``csv_relational/`` dataset harvested from Google
Maps.

The new layout is:

* ``marketplace_reviews`` keeps the marketplace review contract. The
  old ``reviews`` table is renamed so we can reuse the ``reviews`` name
  for Google Maps place reviews.
* ``places`` is recreated with ``id`` widened to ``VARCHAR(96)`` so it
  can store Google Maps Place IDs as the primary key, plus two new
  provenance columns (``source_platform``, ``source_link``) and a
  numeric ``rating``/``review_count`` pair lifted out of the previous
  metadata JSON for query convenience.
* Four child tables are added to model the relational CSVs:
  ``place_amenities``, ``place_opening_hours``, ``place_images`` and
  ``reviews`` (Google Maps place reviews).
* ``place_region_snapshots`` and ``place_region_catalog_state`` are
  rebuilt around the new ``places`` shape so the existing snapshot
  service can keep working.
* ``user_visited_places`` is dropped and recreated so its foreign key
  targets the new ``places`` primary key.

The schema was reviewed against ``docs/13-database-schema.md`` and the
importer in ``backend/scripts/import_google_places_to_postgres.py`` is
the only consumer that depends on the new column types.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260731_0002"
down_revision: str | None = "20260731_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


PLACE_ID_LENGTH = 96  # Google Maps Place IDs are ~27 chars; 96 leaves room
NAME_LENGTH = 255
PLACE_TYPE_LENGTH = 96
SHORT_STRING = 160
SHORT_CODE = 8
SHORT_LABEL = 64


def _drop_user_visited_places() -> None:
    op.drop_index(
        "ix_user_visited_places_place_id",
        table_name="user_visited_places",
        if_exists=True,
    )
    op.drop_index(
        "ix_user_visited_places_user_id",
        table_name="user_visited_places",
        if_exists=True,
    )
    op.drop_table("user_visited_places")


def _create_user_visited_places() -> None:
    op.create_table(
        "user_visited_places",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.String(length=PLACE_ID_LENGTH), nullable=False),
        sa.Column("visited_at", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "place_id", name="uq_user_visited_places_user_place"
        ),
    )
    op.create_index(
        "ix_user_visited_places_user_id", "user_visited_places", ["user_id"]
    )
    op.create_index(
        "ix_user_visited_places_place_id", "user_visited_places", ["place_id"]
    )


def _reseed_demo_visited_places() -> None:
    # The previous migration seeded three demo places tied to the showcase
    # account. Because we recreate the table, the place ids need to be
    # re-inserted with the new primary-key shape (we keep the original id
    # strings so the showcase stays stable).
    op.execute(
        sa.text(
            """
            INSERT INTO places (
                id, name, place_type, address, city, country, country_code,
                region_key, primary_area, latitude, longitude, status,
                opening_hours, data_confidence, source_platform, source_link,
                rating, review_count, revision, metadata
            ) VALUES
                (
                    'demo-visited-hoi-an', 'Phố cổ Hội An', 'historic_area',
                    'Phường Minh An, Hội An', 'Hội An', 'Việt Nam', 'VN',
                    'vn:quang-nam:hoi-an', 'Hội An', 15.8800584, 108.3380469,
                    'active', '[]', 'high', 'seed', NULL,
                    NULL, 0, 1, '{"seed": "profile-showcase"}'
                ),
                (
                    'demo-visited-da-lat', 'Quảng trường Lâm Viên', 'landmark',
                    'Đường Trần Quốc Toản, Đà Lạt', 'Đà Lạt', 'Việt Nam', 'VN',
                    'vn:lam-dong:da-lat', 'Đà Lạt', 11.9404192, 108.4383124,
                    'active', '[]', 'high', 'seed', NULL,
                    NULL, 0, 1, '{"seed": "profile-showcase"}'
                ),
                (
                    'demo-visited-ha-noi', 'Hồ Hoàn Kiếm', 'lake',
                    'Hoàn Kiếm, Hà Nội', 'Hà Nội', 'Việt Nam', 'VN',
                    'vn:ha-noi:hoan-kiem', 'Hà Nội', 21.0286669, 105.8521484,
                    'active', '[]', 'high', 'seed', NULL,
                    NULL, 0, 1, '{"seed": "profile-showcase"}'
                )
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_visited_places (id, user_id, place_id, visited_at, note)
            SELECT seed.id, users.id, seed.place_id, seed.visited_at, seed.note
            FROM users
            CROSS JOIN (
                VALUES
                    (
                        'visit-dieulinh-hoi-an', 'demo-visited-hoi-an',
                        DATE '2026-06-14', 'Một chiều thong thả trong phố cổ và ngắm đèn lồng.'
                    ),
                    (
                        'visit-dieulinh-da-lat', 'demo-visited-da-lat',
                        DATE '2026-03-22', 'Sáng se lạnh, cà phê và một vòng quanh hồ Xuân Hương.'
                    ),
                    (
                        'visit-dieulinh-ha-noi', 'demo-visited-ha-noi',
                        DATE '2025-12-08', 'Food tour phố cổ rồi đi bộ quanh hồ.'
                    )
            ) AS seed(id, place_id, visited_at, note)
            WHERE users.email = 'dieulinh268268@gmail.com'
            ON CONFLICT (user_id, place_id) DO NOTHING
            """
        )
    )


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ---- A: rename marketplace reviews so we can reuse ``reviews`` ----
    op.rename_table("reviews", "marketplace_reviews")
    op.execute(
        "ALTER INDEX IF EXISTS ix_reviews_reviewer_id "
        "RENAME TO ix_marketplace_reviews_reviewer_id"
    )
    op.execute(
        "ALTER TABLE marketplace_reviews "
        "RENAME CONSTRAINT uq_reviews_reviewer_plan "
        "TO uq_marketplace_reviews_reviewer_plan"
    )

    # ---- B: drop user_visited_places (FK will be re-added later) ----
    _drop_user_visited_places()

    # ---- F: drop place_region_snapshots + place_region_catalog_state ----
    op.drop_index(
        "ix_place_region_catalog_refresh",
        table_name="place_region_catalog_state",
        if_exists=True,
    )
    op.drop_table("place_region_catalog_state")
    op.drop_index(
        "ix_place_region_snapshots_fingerprint",
        table_name="place_region_snapshots",
        if_exists=True,
    )
    op.drop_index(
        "ix_place_region_snapshots_region_generated",
        table_name="place_region_snapshots",
        if_exists=True,
    )
    op.drop_table("place_region_snapshots")

    # ---- C: drop + recreate places ----
    op.drop_index(
        "ix_places_source_fetched_at", table_name="places", if_exists=True
    )
    op.drop_index(
        "ix_places_region_type_status", table_name="places", if_exists=True
    )
    op.drop_index(
        "ix_places_region_status", table_name="places", if_exists=True
    )
    op.drop_table("places")

    op.create_table(
        "places",
        sa.Column("id", sa.String(length=PLACE_ID_LENGTH), primary_key=True),
        sa.Column("name", sa.String(length=NAME_LENGTH), nullable=False),
        sa.Column("place_type", sa.String(length=PLACE_TYPE_LENGTH), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=SHORT_STRING), nullable=True),
        sa.Column("country", sa.String(length=SHORT_STRING), nullable=True),
        sa.Column("country_code", sa.String(length=SHORT_CODE), nullable=True),
        sa.Column(
            "region_key",
            sa.String(length=SHORT_STRING),
            nullable=False,
            server_default="vn,unmapped",
        ),
        sa.Column("primary_area", sa.String(length=SHORT_STRING), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "opening_hours",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "typical_duration_minutes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "data_confidence",
            sa.String(length=16),
            nullable=False,
            server_default="low",
        ),
        sa.Column("source_platform", sa.String(length=SHORT_LABEL), nullable=True),
        sa.Column(
            "source_link",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "plus_code",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'temporarily_closed', 'permanently_closed', 'unverified')",
            name="ck_places_status",
        ),
        sa.CheckConstraint(
            "data_confidence IN ('low', 'medium', 'high')",
            name="ck_places_data_confidence",
        ),
        sa.CheckConstraint(
            "typical_duration_minutes IS NULL OR typical_duration_minutes > 0",
            name="ck_places_positive_duration",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_places_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_places_longitude",
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 5)",
            name="ck_places_rating_range",
        ),
        sa.CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name="ck_places_review_count_nonnegative",
        ),
    )
    op.create_index("ix_places_region_status", "places", ["region_key", "status"])
    op.create_index(
        "ix_places_region_type_status",
        "places",
        ["region_key", "place_type", "status"],
    )
    op.create_index(
        "ix_places_source_fetched_at", "places", ["source_fetched_at"]
    )
    op.create_index("ix_places_city", "places", ["city"])
    op.create_index("ix_places_source_platform", "places", ["source_platform"])

    # ---- D: child tables for amenities, opening_hours, images, reviews ----
    op.create_table(
        "place_amenities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "place_id",
            sa.String(length=PLACE_ID_LENGTH),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_group", sa.String(length=SHORT_LABEL), nullable=False),
        sa.Column("amenity_name", sa.String(length=NAME_LENGTH), nullable=False),
        sa.UniqueConstraint(
            "place_id",
            "category_group",
            "amenity_name",
            name="uq_place_amenities_unique",
        ),
    )
    op.create_index(
        "ix_place_amenities_place_id", "place_amenities", ["place_id"]
    )
    op.create_index(
        "ix_place_amenities_category",
        "place_amenities",
        ["category_group"],
    )

    op.create_table(
        "place_opening_hours",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "place_id",
            sa.String(length=PLACE_ID_LENGTH),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_of_week", sa.String(length=16), nullable=False),
        sa.Column("time_slots", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "place_id", "day_of_week", name="uq_place_opening_hours_place_day"
        ),
    )
    op.create_index(
        "ix_place_opening_hours_place_id",
        "place_opening_hours",
        ["place_id"],
    )

    op.create_table(
        "place_images",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "place_id",
            sa.String(length=PLACE_ID_LENGTH),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_title", sa.String(length=SHORT_LABEL), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "place_id", "image_url", name="uq_place_images_place_url"
        ),
    )
    op.create_index(
        "ix_place_images_place_id", "place_images", ["place_id"]
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=PLACE_ID_LENGTH), primary_key=True),
        sa.Column(
            "place_id",
            sa.String(length=PLACE_ID_LENGTH),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_name", sa.String(length=NAME_LENGTH), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("when_text", sa.String(length=SHORT_LABEL), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating BETWEEN 1 AND 5)",
            name="ck_reviews_rating_range",
        ),
    )
    op.create_index("ix_reviews_place_id", "reviews", ["place_id"])
    op.create_index(
        "ix_reviews_published_at", "reviews", ["published_at"]
    )

    # ---- F (cont): recreate region snapshot tables ----
    op.create_table(
        "place_region_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("region_key", sa.String(length=SHORT_STRING), nullable=False),
        sa.Column("catalog_version", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("place_count", sa.Integer(), nullable=False),
        sa.Column("active_place_count", sa.Integer(), nullable=False),
        sa.Column("source_max_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "place_count >= 0 AND active_place_count >= 0 AND active_place_count <= place_count",
            name="ck_place_region_snapshot_counts",
        ),
        sa.UniqueConstraint(
            "region_key",
            "catalog_version",
            "algorithm_version",
            name="uq_place_region_snapshot_version",
        ),
    )
    op.create_index(
        "ix_place_region_snapshots_region_generated",
        "place_region_snapshots",
        ["region_key", "generated_at"],
    )
    op.create_index(
        "ix_place_region_snapshots_fingerprint",
        "place_region_snapshots",
        ["source_fingerprint"],
    )

    op.create_table(
        "place_region_catalog_state",
        sa.Column(
            "region_key",
            sa.String(length=SHORT_STRING),
            primary_key=True,
        ),
        sa.Column(
            "catalog_version",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey(
                "place_region_snapshots.id",
                ondelete="SET NULL",
                name="fk_place_region_state_current_snapshot",
            ),
            nullable=True,
        ),
        sa.Column("dirty_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refresh_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "refresh_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "refresh_status IN ('clean', 'pending', 'running', 'failed')",
            name="ck_place_region_catalog_refresh_status",
        ),
        sa.CheckConstraint(
            "catalog_version >= 0 AND refresh_attempts >= 0",
            name="ck_place_region_catalog_nonnegative",
        ),
    )
    op.create_index(
        "ix_place_region_catalog_refresh",
        "place_region_catalog_state",
        ["refresh_status", "next_retry_at"],
    )

    # ---- E: restore user_visited_places + seed demo places ----
    _create_user_visited_places()
    _reseed_demo_visited_places()


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # user_visited_places will be re-created by an older migration; remove the
    # FK rows so the demo seed can be re-applied from 20260730_0013.
    op.execute(
        "DELETE FROM user_visited_places WHERE place_id LIKE 'demo-visited-%'"
    )
    _drop_user_visited_places()

    op.drop_index(
        "ix_place_region_catalog_refresh",
        table_name="place_region_catalog_state",
        if_exists=True,
    )
    op.drop_table("place_region_catalog_state")
    op.drop_index(
        "ix_place_region_snapshots_fingerprint",
        table_name="place_region_snapshots",
        if_exists=True,
    )
    op.drop_index(
        "ix_place_region_snapshots_region_generated",
        table_name="place_region_snapshots",
        if_exists=True,
    )
    op.drop_table("place_region_snapshots")

    op.drop_index("ix_reviews_published_at", table_name="reviews", if_exists=True)
    op.drop_index("ix_reviews_place_id", table_name="reviews", if_exists=True)
    op.drop_table("reviews")

    op.drop_index(
        "ix_place_images_place_id", table_name="place_images", if_exists=True
    )
    op.drop_table("place_images")

    op.drop_index(
        "ix_place_opening_hours_place_id",
        table_name="place_opening_hours",
        if_exists=True,
    )
    op.drop_table("place_opening_hours")

    op.drop_index(
        "ix_place_amenities_category", table_name="place_amenities", if_exists=True
    )
    op.drop_index(
        "ix_place_amenities_place_id", table_name="place_amenities", if_exists=True
    )
    op.drop_table("place_amenities")

    op.drop_index("ix_places_source_platform", table_name="places", if_exists=True)
    op.drop_index("ix_places_city", table_name="places", if_exists=True)
    op.drop_index(
        "ix_places_source_fetched_at", table_name="places", if_exists=True
    )
    op.drop_index(
        "ix_places_region_type_status", table_name="places", if_exists=True
    )
    op.drop_index("ix_places_region_status", table_name="places", if_exists=True)
    op.drop_table("places")

    op.rename_table("marketplace_reviews", "reviews")
    op.execute(
        "ALTER INDEX IF EXISTS ix_marketplace_reviews_reviewer_id "
        "RENAME TO ix_reviews_reviewer_id"
    )
    op.execute(
        "ALTER TABLE reviews "
        "RENAME CONSTRAINT uq_marketplace_reviews_reviewer_plan "
        "TO uq_reviews_reviewer_plan"
    )
