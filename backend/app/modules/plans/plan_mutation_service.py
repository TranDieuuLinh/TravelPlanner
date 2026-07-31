from uuid import uuid4

from app.modules.places.resolver import PlaceResolver, ProvisionalPlaceResolver
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import Plan, PlanDay, PlanItem
from app.modules.plans.domain.enums import PlanStatus
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    MutationResponse,
    PlaceSuggestion,
    ReorderItemsRequest,
    UpdateItemRequest,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.shared.errors import AppError


class PlanMutationService:
    def __init__(
        self,
        place_resolver: PlaceResolver | None = None,
        route_optimizer: GeographicRouteOptimizer | None = None,
        checker: OverallChecker | None = None,
    ) -> None:
        self.place_resolver = place_resolver or ProvisionalPlaceResolver()
        self.route_optimizer = route_optimizer or GeographicRouteOptimizer()
        self.checker = checker or OverallChecker()

    async def search_place_suggestions(
        self,
        query: str,
        destination: str | None = None,
    ) -> list[PlaceSuggestion]:
        cleaned = query.strip()
        if not cleaned:
            return []
        dest = (destination or "").strip()
        candidate = UnifiedPlaceCandidate(
            name=cleaned,
            search_region=dest,
        )
        suggestions: list[PlaceSuggestion] = []
        try:
            resolution = await self.place_resolver.resolve(candidate, destination=dest)
            if resolution.name and resolution.latitude is not None and resolution.longitude is not None:
                suggestions.append(
                    PlaceSuggestion(
                        name=resolution.name,
                        address=resolution.address,
                        latitude=float(resolution.latitude),
                        longitude=float(resolution.longitude),
                        placeId=resolution.external_id,
                    )
                )
        except Exception:
            pass
        return suggestions

    async def add_item(self, plan: Plan, request: AddItemRequest) -> MutationResponse:
        day = self._get_day(plan, request.day)
        time_window = request.time_window or self._calculate_next_time_window(
            day, request.duration_minutes
        )

        lat = request.latitude
        lng = request.longitude
        address = request.address
        place_id = None

        # Auto-resolve coordinates if missing
        if lat is None or lng is None:
            candidate = UnifiedPlaceCandidate(
                name=request.name,
                address_hint=request.address,
                search_region=plan.destination,
            )
            try:
                resolved = await self.place_resolver.resolve(
                    candidate, destination=plan.destination
                )
                if resolved.latitude is not None and resolved.longitude is not None:
                    lat = float(resolved.latitude)
                    lng = float(resolved.longitude)
                if resolved.address:
                    address = resolved.address
                if resolved.external_id:
                    place_id = resolved.external_id
            except Exception:
                pass  # Keep fallback if resolver fails or unavailable

        new_item = PlanItem(
            itemId=str(uuid4()),
            placeId=place_id,
            name=request.name,
            address=address,
            timeWindow=time_window,
            placeType=request.place_type,
            source="manual",
            durationMinutes=request.duration_minutes,
            tags=request.tags,
            latitude=lat,
            longitude=lng,
            notes=request.notes,
        )

        items = list(day.items)
        if request.position is not None and 0 <= request.position <= len(items):
            items.insert(request.position, new_item)
        else:
            items.append(new_item)

        updated_day = self._reoptimize_day(day, items)
        return self._finalize_mutation(plan, [updated_day])

    async def update_item(
        self,
        plan: Plan,
        day_number: int,
        item_id: str,
        request: UpdateItemRequest,
    ) -> MutationResponse:
        day = self._get_day(plan, day_number)
        item_index = self._find_item_index(day, item_id)

        existing_item = day.items[item_index]
        updates = request.model_dump(exclude_unset=True, by_alias=False)

        # If name updated and no coordinates provided, try auto-resolving again
        if (
            "name" in updates
            and updates["name"] != existing_item.name
            and updates.get("latitude") is None
        ):
            candidate = UnifiedPlaceCandidate(
                name=updates["name"],
                address_hint=updates.get("address") or existing_item.address,
                search_region=plan.destination,
            )
            try:
                resolved = await self.place_resolver.resolve(
                    candidate, destination=plan.destination
                )
                if resolved.latitude is not None and resolved.longitude is not None:
                    updates["latitude"] = float(resolved.latitude)
                    updates["longitude"] = float(resolved.longitude)
                if resolved.address and not updates.get("address"):
                    updates["address"] = resolved.address
            except Exception:
                pass

        updated_item = existing_item.model_copy(update=updates)

        items = list(day.items)
        items[item_index] = updated_item

        updated_day = self._reoptimize_day(day, items)
        return self._finalize_mutation(plan, [updated_day])

    def remove_item(
        self,
        plan: Plan,
        day_number: int,
        item_id: str,
    ) -> MutationResponse:
        day = self._get_day(plan, day_number)
        item_index = self._find_item_index(day, item_id)

        items = [item for idx, item in enumerate(day.items) if idx != item_index]

        updated_day = self._reoptimize_day(day, items)
        return self._finalize_mutation(plan, [updated_day])

    def move_item(
        self,
        plan: Plan,
        from_day_number: int,
        item_id: str,
        request: MoveItemRequest,
    ) -> MutationResponse:
        from_day = self._get_day(plan, from_day_number)
        to_day = self._get_day(plan, request.to_day)

        item_index = self._find_item_index(from_day, item_id)
        item_to_move = from_day.items[item_index]

        from_items = [
            item for idx, item in enumerate(from_day.items) if idx != item_index
        ]
        updated_from_day = self._reoptimize_day(from_day, from_items)

        to_items = list(to_day.items)
        if request.position is not None and 0 <= request.position <= len(to_items):
            to_items.insert(request.position, item_to_move)
        else:
            to_items.append(item_to_move)
        updated_to_day = self._reoptimize_day(to_day, to_items)

        return self._finalize_mutation(plan, [updated_from_day, updated_to_day])

    def reorder_items(
        self,
        plan: Plan,
        day_number: int,
        request: ReorderItemsRequest,
    ) -> MutationResponse:
        day = self._get_day(plan, day_number)
        items_by_id = {item.item_id: item for item in day.items if item.item_id}

        reordered_items: list[PlanItem] = []
        for item_id in request.item_ids:
            if item_id in items_by_id:
                reordered_items.append(items_by_id.pop(item_id))

        reordered_items.extend(items_by_id.values())

        updated_day = self._reoptimize_day(day, reordered_items)
        return self._finalize_mutation(plan, [updated_day])

    def _get_day(self, plan: Plan, day_number: int) -> PlanDay:
        for day in plan.days:
            if day.day == day_number:
                return day
        raise AppError(
            404,
            "PLAN_DAY_NOT_FOUND",
            f"Không tìm thấy Ngày {day_number} trong lịch trình.",
        )

    def _find_item_index(self, day: PlanDay, item_id: str) -> int:
        for idx, item in enumerate(day.items):
            if item.item_id == item_id:
                return idx
        raise AppError(
            404,
            "PLAN_ITEM_NOT_FOUND",
            f"Không tìm thấy địa điểm trong Ngày {day.day}.",
        )

    def _reoptimize_day(self, day: PlanDay, items: list[PlanItem]) -> PlanDay:
        adjusted_items = self._readjust_time_windows(items)
        optimized_items, transport_legs = self.route_optimizer.optimize(
            adjusted_items,
            preserve_order=True,
            day=day.day,
        )
        return day.model_copy(
            update={
                "items": optimized_items,
                "transport_legs": transport_legs,
            }
        )

    def _readjust_time_windows(self, items: list[PlanItem]) -> list[PlanItem]:
        if not items:
            return items

        start_min = 9 * 60
        first_item = items[0]
        if first_item.time_window and "-" in first_item.time_window:
            try:
                sh, sm = map(int, first_item.time_window.split("-")[0].split(":"))
                start_min = sh * 60 + sm
            except ValueError:
                pass

        adjusted: list[PlanItem] = []
        current_min = start_min
        for item in items:
            dur = item.duration_minutes or 60
            end_min = min(23 * 60 + 59, current_min + dur)
            sh, sm = divmod(current_min, 60)
            eh, em = divmod(end_min, 60)
            window_str = f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
            adjusted.append(item.model_copy(update={"time_window": window_str}))
            current_min = min(23 * 60 + 44, end_min + 15)

        return adjusted

    def _finalize_mutation(
        self,
        plan: Plan,
        updated_days: list[PlanDay],
    ) -> MutationResponse:
        updated_days_map = {day.day: day for day in updated_days}
        new_days = [
            updated_days_map.get(day.day, day) for day in plan.days
        ]
        updated_plan = plan.model_copy(update={"days": new_days})

        check_report = self.checker.check(updated_plan)
        final_status = (
            PlanStatus.locked
            if check_report.status == "passed"
            else PlanStatus.draft
        )

        final_plan = updated_plan.model_copy(
            update={
                "status": final_status,
                "check_report": check_report,
            }
        )

        return MutationResponse(
            plan=final_plan,
            affected_days=sorted(updated_days_map.keys()),
            check_report=check_report,
        )

    def _calculate_next_time_window(
        self,
        day: PlanDay,
        duration_minutes: int,
    ) -> str:
        if not day.items:
            start_min = 9 * 60  # 09:00
        else:
            last_item = day.items[-1]
            parts = last_item.time_window.split("-")
            if len(parts) == 2:
                try:
                    h, m = map(int, parts[1].split(":"))
                    start_min = h * 60 + m + 15
                except ValueError:
                    start_min = 9 * 60
            else:
                start_min = 9 * 60

        end_min = min(23 * 60 + 59, start_min + duration_minutes)
        start_h, start_m = divmod(start_min, 60)
        end_h, end_m = divmod(end_min, 60)
        return f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"
