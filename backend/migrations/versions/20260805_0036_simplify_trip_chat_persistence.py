"""collapse trip intent snapshots and conversation turns

Revision ID: 20260805_0036
Revises: 20260805_0035
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0036"
down_revision: str | None = "20260805_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _intent_payloads(bind) -> dict[str, dict]:
    versions = sa.table(
        "trip_intent_versions",
        sa.column("id"), sa.column("destination"), sa.column("days"),
        sa.column("start_date"), sa.column("end_date"),
        sa.column("date_flexibility"), sa.column("party_type"),
        sa.column("adults"), sa.column("children"), sa.column("infants"),
        sa.column("pets"), sa.column("rooms"), sa.column("budget_amount"),
        sa.column("budget_currency"), sa.column("budget_level"),
        sa.column("travel_style"), sa.column("pace"),
        sa.column("accommodation_required"), sa.column("hotel_area"),
        sa.column("check_in_date"), sa.column("check_out_date"),
        sa.column("transport_required"), sa.column("include_between_places"),
        sa.column("include_arrival_departure"), sa.column("geographic_scope"),
    )
    values_table = sa.table(
        "trip_intent_values", sa.column("trip_intent_id"), sa.column("kind"),
        sa.column("value"), sa.column("position"),
    )
    stays_table = sa.table(
        "trip_intent_destination_stays", sa.column("trip_intent_id"),
        sa.column("name"), sa.column("duration_days"), sa.column("start_day"),
        sa.column("end_day"), sa.column("position"),
    )
    values: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in bind.execute(
        sa.select(values_table).order_by(
            values_table.c.trip_intent_id, values_table.c.kind,
            values_table.c.position,
        )
    ).mappings():
        values[row["trip_intent_id"]][row["kind"]].append(row["value"])
    stays: dict[str, list[dict]] = defaultdict(list)
    for row in bind.execute(
        sa.select(stays_table).order_by(
            stays_table.c.trip_intent_id, stays_table.c.position
        )
    ).mappings():
        stays[row["trip_intent_id"]].append({
            "name": row["name"], "durationDays": row["duration_days"],
            "startDay": row["start_day"], "endDay": row["end_day"],
            "sourceRefs": [],
        })

    payloads: dict[str, dict] = {}
    for row in bind.execute(sa.select(versions)).mappings():
        grouped = values[row["id"]]
        amount = row["budget_amount"]
        payloads[row["id"]] = {
            "destination": row["destination"],
            "timing": {
                "days": row["days"], "startDate": row["start_date"],
                "endDate": row["end_date"],
                "flexibility": row["date_flexibility"],
                "destinationStays": stays[row["id"]],
            },
            "travelParty": {
                "type": row["party_type"], "adults": row["adults"],
                "children": row["children"], "infants": row["infants"],
                "pets": row["pets"], "rooms": row["rooms"],
            },
            "budget": {
                "targetAmount": int(amount) if amount is not None else None,
                "currency": row["budget_currency"], "level": row["budget_level"],
            },
            "notes": grouped["note"],
            "preferences": {
                "travelStyle": row["travel_style"], "pace": row["pace"],
                "interests": grouped["interest"],
                "mustVisitPlaces": grouped["must_visit"],
                "avoidPlaces": grouped["avoid_place"],
                "accommodation": {
                    "required": row["accommodation_required"],
                    "hotelArea": row["hotel_area"],
                    "checkInDate": row["check_in_date"],
                    "checkOutDate": row["check_out_date"],
                    "roomCount": row["rooms"],
                    "guestCount": row["adults"] + row["children"] + row["infants"],
                    "preferences": grouped["accommodation_preference"],
                },
                "transport": {
                    "required": row["transport_required"],
                    "preferredModes": grouped["preferred_transport"],
                    "avoidModes": grouped["avoided_transport"],
                    "includeBetweenPlaces": row["include_between_places"],
                    "includeArrivalDeparture": row["include_arrival_departure"],
                },
            },
            "constraints": {
                "items": grouped["constraint"],
                "policy": {
                    "excludedPlaceTypes": grouped["excluded_place_type"],
                    "geographicScope": {"type": row["geographic_scope"]},
                },
            },
            "clarifyingQuestions": grouped["clarifying_question"],
        }
    return payloads


def upgrade() -> None:
    bind = op.get_bind()
    evidence_fk = next(
        (
            foreign_key
            for foreign_key in sa.inspect(bind).get_foreign_keys(
                "traveler_preference_signals"
            )
            if foreign_key.get("constrained_columns")
            == ["last_evidence_intake_id"]
        ),
        None,
    )
    if evidence_fk is not None and evidence_fk.get("name"):
        with op.batch_alter_table("traveler_preference_signals") as batch:
            batch.drop_constraint(evidence_fk["name"], type_="foreignkey")
    op.add_column("trip_chats", sa.Column("current_trip_intent", sa.JSON(), nullable=True))
    op.add_column(
        "trip_chat_plan_revisions",
        sa.Column("trip_intent_payload", sa.JSON(), nullable=True),
    )
    lifecycle_columns = (
        sa.Column("client_turn_id", sa.String(72), nullable=True),
        sa.Column("base_revision", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("proposed_operations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("assistant_blocks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in lifecycle_columns:
        op.add_column("trip_chat_messages", column)

    payloads = _intent_payloads(bind)
    chats = sa.table(
        "trip_chats", sa.column("id"), sa.column("current_trip_intent_id"),
        sa.column("current_trip_intent"),
    )
    revisions = sa.table(
        "trip_chat_plan_revisions", sa.column("id"), sa.column("trip_intent_id"),
        sa.column("trip_intent_payload"),
    )
    for row in bind.execute(sa.select(chats.c.id, chats.c.current_trip_intent_id)).mappings():
        payload = payloads.get(row["current_trip_intent_id"])
        if payload is not None:
            bind.execute(
                chats.update().where(chats.c.id == row["id"]).values(current_trip_intent=payload)
            )
    for row in bind.execute(sa.select(revisions.c.id, revisions.c.trip_intent_id)).mappings():
        payload = payloads.get(row["trip_intent_id"])
        if payload is not None:
            bind.execute(
                revisions.update().where(revisions.c.id == row["id"]).values(trip_intent_payload=payload)
            )

    messages = sa.table(
        "trip_chat_messages", sa.column("id"), sa.column("chat_id"),
        sa.column("role"), sa.column("content"), sa.column("sequence"),
        sa.column("attachment_names"), sa.column("plan_revision"),
        sa.column("turn_id"), sa.column("message_kind"), sa.column("content_blocks"),
        sa.column("created_at"), sa.column("updated_at"),
        sa.column("client_turn_id"), sa.column("base_revision"),
        sa.column("status"), sa.column("intent"), sa.column("confidence"),
        sa.column("requires_confirmation"), sa.column("proposed_operations"),
        sa.column("assistant_blocks"), sa.column("result_summary"),
        sa.column("error_code"), sa.column("error_message"),
        sa.column("processing_started_at"),
    )
    turns = sa.table(
        "trip_chat_turns", sa.column("id"), sa.column("chat_id"),
        sa.column("client_turn_id"), sa.column("content"),
        sa.column("attachment_names"), sa.column("base_revision"),
        sa.column("status"), sa.column("intent"), sa.column("confidence"),
        sa.column("requires_confirmation"), sa.column("proposed_operations"),
        sa.column("assistant_blocks"), sa.column("result_summary"),
        sa.column("error_code"), sa.column("error_message"),
        sa.column("created_at"), sa.column("updated_at"),
        sa.column("processing_started_at"),
    )
    max_sequence = defaultdict(int)
    for row in bind.execute(sa.select(messages.c.chat_id, messages.c.sequence)).mappings():
        max_sequence[row["chat_id"]] = max(max_sequence[row["chat_id"]], row["sequence"])
    for turn in bind.execute(sa.select(turns)).mappings():
        existing = bind.execute(
            sa.select(messages.c.id).where(
                messages.c.chat_id == turn["chat_id"],
                messages.c.role == "user",
                messages.c.turn_id == turn["id"],
            ).limit(1)
        ).scalar_one_or_none()
        lifecycle = {
            "client_turn_id": turn["client_turn_id"],
            "base_revision": turn["base_revision"], "status": turn["status"],
            "intent": turn["intent"], "confidence": turn["confidence"],
            "requires_confirmation": turn["requires_confirmation"],
            "proposed_operations": turn["proposed_operations"] or [],
            "assistant_blocks": turn["assistant_blocks"] or [],
            "result_summary": turn["result_summary"] or {},
            "error_code": turn["error_code"], "error_message": turn["error_message"],
            "processing_started_at": turn["processing_started_at"],
            "updated_at": turn["updated_at"],
        }
        if existing is not None:
            bind.execute(messages.update().where(messages.c.id == existing).values(**lifecycle))
            continue
        max_sequence[turn["chat_id"]] += 1
        bind.execute(messages.insert().values(
            id=str(uuid4()), chat_id=turn["chat_id"], role="user",
            content=turn["content"], sequence=max_sequence[turn["chat_id"]],
            attachment_names=turn["attachment_names"] or [], plan_revision=None,
            turn_id=turn["id"], message_kind="turn_request", content_blocks=[],
            created_at=turn["created_at"], **lifecycle,
        ))

    with op.batch_alter_table("trip_chats") as batch:
        batch.drop_constraint("fk_trip_chats_current_trip_intent", type_="foreignkey")
        batch.drop_column("current_trip_intent_id")
    with op.batch_alter_table("trip_chat_plan_revisions") as batch:
        batch.drop_constraint("fk_trip_chat_revisions_trip_intent", type_="foreignkey")
        batch.drop_column("trip_intent_id")
    with op.batch_alter_table("trip_chat_messages") as batch:
        batch.create_unique_constraint(
            "uq_trip_chat_message_client_turn", ["chat_id", "client_turn_id"]
        )
        batch.create_index("ix_trip_chat_messages_status", ["status"])
        batch.create_index(
            "ix_trip_chat_messages_processing_started_at",
            ["processing_started_at"],
        )
    op.drop_table("trip_chat_turns")
    op.drop_table("trip_intent_destination_stays")
    op.drop_table("trip_intent_values")
    op.drop_table("trip_intent_versions")
    op.drop_index(
        "ix_trip_chat_plan_revisions_chat_id",
        table_name="trip_chat_plan_revisions",
    )
    op.drop_index(
        "ix_trip_chat_plan_revisions_intake_id",
        table_name="trip_chat_plan_revisions",
    )
    op.rename_table("trip_chat_plan_revisions", "trip_revisions")
    op.create_index("ix_trip_revisions_chat_id", "trip_revisions", ["chat_id"])
    op.create_index("ix_trip_revisions_intake_id", "trip_revisions", ["intake_id"])


def downgrade() -> None:
    raise RuntimeError(
        "20260805_0036 is an intentional data-model cutover; restore from backup "
        "instead of downgrading normalized TripIntent/turn tables."
    )
