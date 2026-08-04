"""add visited places and user posts for the profile showcase

Revision ID: 20260730_0013
Revises: 20260730_0012
Create Date: 2026-07-30 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0013"
down_revision: str | None = "20260730_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_visited_places",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.String(length=36), nullable=False),
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
            "user_id",
            "place_id",
            name="uq_user_visited_places_user_place",
        ),
    )
    op.create_index(
        "ix_user_visited_places_user_id",
        "user_visited_places",
        ["user_id"],
    )
    op.create_index(
        "ix_user_visited_places_place_id",
        "user_visited_places",
        ["place_id"],
    )

    op.create_table(
        "user_posts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("media_url", sa.String(length=1000), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_posts_user_id", "user_posts", ["user_id"])
    op.create_index("ix_user_posts_created_at", "user_posts", ["created_at"])

    # Seed a small, deterministic showcase for the account shown in the profile
    # mockup. The INSERTs are idempotent and only attach private profile data when
    # that exact account already exists.
    op.execute(
        sa.text(
            """
            INSERT INTO places (
                id, name, place_type, address, city, country, country_code,
                region_key, primary_area, latitude, longitude, status,
                opening_hours, data_confidence, revision, metadata
            ) VALUES
                (
                    'demo-visited-hoi-an', 'Phố cổ Hội An', 'historic_area',
                    'Phường Minh An, Hội An', 'Hội An', 'Việt Nam', 'VN',
                    'vn:quang-nam:hoi-an', 'Hội An', 15.8800584, 108.3380469,
                    'active', '[]', 'high', 1, '{"seed": "profile-showcase"}'
                ),
                (
                    'demo-visited-da-lat', 'Quảng trường Lâm Viên', 'landmark',
                    'Đường Trần Quốc Toản, Đà Lạt', 'Đà Lạt', 'Việt Nam', 'VN',
                    'vn:lam-dong:da-lat', 'Đà Lạt', 11.9404192, 108.4383124,
                    'active', '[]', 'high', 1, '{"seed": "profile-showcase"}'
                ),
                (
                    'demo-visited-ha-noi', 'Hồ Hoàn Kiếm', 'lake',
                    'Hoàn Kiếm, Hà Nội', 'Hà Nội', 'Việt Nam', 'VN',
                    'vn:ha-noi:hoan-kiem', 'Hà Nội', 21.0286669, 105.8521484,
                    'active', '[]', 'high', 1, '{"seed": "profile-showcase"}'
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
    op.execute(
        sa.text(
            """
            INSERT INTO user_posts (
                id, user_id, caption, media_url, location_name, created_at
            )
            SELECT seed.id, users.id, seed.caption, seed.media_url, seed.location_name, seed.created_at
            FROM users
            CROSS JOIN (
                VALUES
                    (
                        'post-dieulinh-hoi-an',
                        'Một buổi chiều đi chậm giữa những mái nhà vàng và đèn lồng Hội An.',
                        'https://images.unsplash.com/photo-1559592413-7cec4d0cae2b',
                        'Phố cổ Hội An',
                        TIMESTAMPTZ '2026-06-15 09:30:00+07'
                    ),
                    (
                        'post-dieulinh-da-lat',
                        'Đà Lạt sáng sớm, trời lạnh vừa đủ để tìm một quán cà phê thật lâu.',
                        'https://images.unsplash.com/photo-1506744038136-46273834b3fb',
                        'Đà Lạt',
                        TIMESTAMPTZ '2026-03-23 08:15:00+07'
                    ),
                    (
                        'post-dieulinh-ha-noi',
                        'Hà Nội mùa đông và một vòng food tour quanh phố cổ.',
                        'https://images.unsplash.com/photo-1509030450996-939a26352132',
                        'Hồ Hoàn Kiếm, Hà Nội',
                        TIMESTAMPTZ '2025-12-09 19:45:00+07'
                    )
            ) AS seed(id, caption, media_url, location_name, created_at)
            WHERE users.email = 'dieulinh268268@gmail.com'
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_posts_created_at", table_name="user_posts")
    op.drop_index("ix_user_posts_user_id", table_name="user_posts")
    op.drop_table("user_posts")
    op.drop_index("ix_user_visited_places_place_id", table_name="user_visited_places")
    op.drop_index("ix_user_visited_places_user_id", table_name="user_visited_places")
    op.drop_table("user_visited_places")
