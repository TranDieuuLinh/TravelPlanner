"""normalize long-term traveler profiles and preference signals

Revision ID: 20260805_0033
Revises: 20260805_0032
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0033"
down_revision: str | None = "20260805_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traveler_profiles",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "traveler_preference_signals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "first_observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_evidence_intake_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "score >= -1 AND score <= 1", name="ck_traveler_signal_score"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_traveler_signal_confidence",
        ),
        sa.CheckConstraint(
            "scope IN ('global','destination')",
            name="ck_traveler_signal_scope",
        ),
        sa.CheckConstraint(
            "origin IN ('explicit','inferred')",
            name="ck_traveler_signal_origin",
        ),
        sa.CheckConstraint(
            "status IN ('active','rejected')",
            name="ck_traveler_signal_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["traveler_profiles.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_evidence_intake_id"],
            ["explorer_intakes.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "user_id",
            "dimension",
            "value",
            "scope",
            "destination",
            name="uq_traveler_signal_identity",
        ),
    )
    op.create_index(
        "ix_traveler_preference_signals_user_id",
        "traveler_preference_signals",
        ["user_id"],
    )
    op.create_table(
        "traveler_preference_signal_sources",
        sa.Column("signal_id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=40), primary_key=True),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["traveler_preference_signals.id"],
            ondelete="CASCADE",
        ),
    )

    # Preserve the legacy JSON values once, then make the relational model the
    # only source of truth.
    op.execute(
        """
        INSERT INTO traveler_profiles
            (user_id, version, observation_count, created_at, updated_at)
        SELECT
            id,
            COALESCE(
                CASE WHEN json_typeof(travel_preferences) = 'object'
                     THEN (travel_preferences ->> 'version')::integer END,
                1
            ),
            COALESCE(
                CASE WHEN json_typeof(travel_preferences) = 'object'
                     THEN (travel_preferences ->> 'observationCount')::integer END,
                0
            ),
            created_at,
            COALESCE(
                CASE WHEN json_typeof(travel_preferences) = 'object'
                     THEN (travel_preferences ->> 'updatedAt')::timestamptz END,
                updated_at
            )
        FROM users
        """
    )
    op.execute(
        """
        INSERT INTO traveler_preference_signals
            (id, user_id, dimension, value, label, score, confidence,
             observations, position, scope, destination, origin, status,
             first_observed_at, last_observed_at)
        SELECT
            md5(u.id::text || ':explicit:' || preference.value),
            u.id,
            'explicit',
            lower(replace(replace(trim(preference.value), '-', '_'), ' ', '_')),
            trim(preference.value),
            1.0,
            1.0,
            1,
            preference.position - 1,
            'global',
            '',
            'explicit',
            'active',
            u.created_at,
            u.updated_at
        FROM users AS u
        CROSS JOIN LATERAL json_array_elements_text(
            CASE
                WHEN json_typeof(u.travel_preferences) = 'array'
                    THEN u.travel_preferences
                WHEN json_typeof(u.travel_preferences) = 'object'
                     AND json_typeof(u.travel_preferences -> 'explicit') = 'array'
                    THEN u.travel_preferences -> 'explicit'
                ELSE '[]'::json
            END
        ) WITH ORDINALITY AS preference(value, position)
        WHERE trim(preference.value) <> ''
        ON CONFLICT ON CONSTRAINT uq_traveler_signal_identity DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO traveler_preference_signals
            (id, user_id, dimension, value, label, score, confidence,
             observations, position, scope, destination, origin, status,
             first_observed_at, last_observed_at)
        SELECT
            md5(u.id::text || ':inferred:' || score_entry.key),
            u.id,
            split_part(score_entry.key, ':', 1),
            split_part(score_entry.key, ':', 2),
            replace(split_part(score_entry.key, ':', 2), '_', ' '),
            COALESCE((score_entry.value ->> 'score')::double precision, 0),
            COALESCE((score_entry.value ->> 'confidence')::double precision, 0),
            COALESCE((score_entry.value ->> 'observations')::integer, 1),
            0,
            'global',
            '',
            'inferred',
            'active',
            COALESCE(
                (score_entry.value ->> 'lastObservedAt')::timestamptz,
                u.created_at
            ),
            COALESCE(
                (score_entry.value ->> 'lastObservedAt')::timestamptz,
                u.updated_at
            )
        FROM users AS u
        CROSS JOIN LATERAL json_each(
            CASE
                WHEN json_typeof(u.travel_preferences) = 'object'
                     AND json_typeof(u.travel_preferences -> 'scores') = 'object'
                    THEN u.travel_preferences -> 'scores'
                ELSE '{}'::json
            END
        ) AS score_entry(key, value)
        WHERE position(':' in score_entry.key) > 1
        ON CONFLICT ON CONSTRAINT uq_traveler_signal_identity DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO traveler_preference_signal_sources (signal_id, source_type)
        SELECT
            md5(u.id::text || ':inferred:' || score_entry.key),
            source.value
        FROM users AS u
        CROSS JOIN LATERAL json_each(
            CASE
                WHEN json_typeof(u.travel_preferences) = 'object'
                     AND json_typeof(u.travel_preferences -> 'scores') = 'object'
                    THEN u.travel_preferences -> 'scores'
                ELSE '{}'::json
            END
        ) AS score_entry(key, value)
        CROSS JOIN LATERAL json_array_elements_text(
            CASE
                WHEN json_typeof(score_entry.value -> 'sourceTypes') = 'array'
                    THEN score_entry.value -> 'sourceTypes'
                ELSE '[]'::json
            END
        ) AS source(value)
        ON CONFLICT DO NOTHING
        """
    )
    op.drop_column("users", "travel_preferences")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "travel_preferences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.execute(
        """
        UPDATE users AS u
        SET travel_preferences = json_build_object(
            'version', p.version,
            'explicit', COALESCE((
                SELECT json_agg(s.label ORDER BY s.label)
                FROM traveler_preference_signals AS s
                WHERE s.user_id = u.id AND s.dimension = 'explicit'
                  AND s.status = 'active'
            ), '[]'::json),
            'scores', COALESCE((
                SELECT json_object_agg(
                    s.dimension || ':' || s.value,
                    json_build_object(
                        'score', s.score,
                        'confidence', s.confidence,
                        'observations', s.observations,
                        'origin', s.origin,
                        'sourceTypes', COALESCE((
                            SELECT json_agg(src.source_type)
                            FROM traveler_preference_signal_sources AS src
                            WHERE src.signal_id = s.id
                        ), '[]'::json),
                        'lastObservedAt', s.last_observed_at
                    )
                )
                FROM traveler_preference_signals AS s
                WHERE s.user_id = u.id AND s.dimension <> 'explicit'
                  AND s.status = 'active'
            ), '{}'::json),
            'observationCount', p.observation_count,
            'updatedAt', p.updated_at
        )
        FROM traveler_profiles AS p
        WHERE p.user_id = u.id
        """
    )
    op.alter_column("users", "travel_preferences", server_default=None)
    op.drop_table("traveler_preference_signal_sources")
    op.drop_index(
        "ix_traveler_preference_signals_user_id",
        table_name="traveler_preference_signals",
    )
    op.drop_table("traveler_preference_signals")
    op.drop_table("traveler_profiles")
