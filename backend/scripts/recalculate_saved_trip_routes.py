"""Recalculate missing saved trip routes with the configured routing stack."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.plans.chat_model import TripChat
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.dependencies import _get_route_optimizer
from app.modules.plans.domain.entities import Plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist recalculated routes and create plan revisions.",
    )
    args = parser.parse_args()

    refreshed = 0
    with SessionLocal() as db:
        chats = list(
            db.scalars(
                select(TripChat)
                .where(TripChat.current_plan.is_not(None))
                .order_by(TripChat.updated_at, TripChat.id)
            )
        )
        repository = TripChatRepository(db)
        optimizer = _get_route_optimizer()

        for chat in chats:
            plan = Plan.model_validate(chat.current_plan)
            if any(day.transport_legs for day in plan.days):
                continue

            trip_intent = repository.load_trip_intent(chat)
            if trip_intent is None:
                print(f"{chat.id}: skipped because no persisted TripIntent exists")
                continue
            transport = trip_intent.preferences.transport
            start_date = trip_intent.timing.start_date
            preferred_modes = {mode.value for mode in transport.preferred_modes}
            avoid_modes = {mode.value for mode in transport.avoid_modes}

            refreshed_days = []
            for day in plan.days:
                _, legs = optimizer.optimize(
                    day.items,
                    preserve_order=True,
                    day=day.day,
                    trip_start_date=start_date,
                    preferred_modes=preferred_modes,
                    avoid_modes=avoid_modes,
                )
                refreshed_days.append(
                    day.model_copy(update={"transport_legs": legs})
                )

            refreshed_plan = plan.model_copy(update={"days": refreshed_days})
            leg_count = sum(
                len(day.transport_legs) for day in refreshed_plan.days
            )
            print(f"{chat.id}: {leg_count} recalculated route legs")
            if not args.apply:
                continue

            repository.save_plan_mutation(
                chat,
                action_summary=(
                    "Đã làm mới tuyến đường bằng hệ thống routing hiện tại."
                ),
                plan_payload=refreshed_plan.model_dump(
                    mode="json",
                    by_alias=True,
                ),
                revision=chat.revision + 1,
            )
            refreshed += 1

    if args.apply:
        print(f"Updated {refreshed} saved trips.")


if __name__ == "__main__":
    main()
