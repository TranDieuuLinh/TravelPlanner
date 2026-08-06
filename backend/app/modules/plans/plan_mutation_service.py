import logging
import unicodedata
from typing import Any
from uuid import uuid4

from app.modules.knowledge_graph.place_search import (
    KnowledgeGraphPlaceSearchRepository,
)
from app.modules.places.resolver import (
    GoogleMapsSearchClient,
    PlaceResolver,
    ProvisionalPlaceResolver,
)
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import (
    Plan,
    PlanDay,
    PlanItem,
    PlanTransportLeg,
    PlanTransportOption,
)
from app.modules.plans.domain.enums import PlanStatus
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    MutationResponse,
    PlaceSuggestion,
    ReorderItemsRequest,
    SelectTransportOptionRequest,
    UpdateItemRequest,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.shared.errors import AppError

logger = logging.getLogger(__name__)


class PlanMutationService:
    def __init__(
        self,
        place_resolver: PlaceResolver | None = None,
        graph_place_repository: KnowledgeGraphPlaceSearchRepository | None = None,
        route_optimizer: GeographicRouteOptimizer | None = None,
        checker: OverallChecker | None = None,
        gmaps_client: GoogleMapsSearchClient | None = None,
    ) -> None:
        self.place_resolver = place_resolver or ProvisionalPlaceResolver()
        self.graph_place_repository = graph_place_repository
        self.route_optimizer = route_optimizer or GeographicRouteOptimizer()
        self.checker = checker or OverallChecker()
        self.gmaps_client = gmaps_client

    async def search_place_suggestions(
        self,
        query: str,
        destination: str | None = None,
        *,
        top_k: int = 5,
    ) -> list[PlaceSuggestion]:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        cleaned = query.strip()
        if not cleaned:
            return []
        dest = (destination or "").strip()

        graph_results = self._search_knowledge_graph(
            cleaned,
            dest,
            limit=top_k,
        )
        if len(graph_results) >= top_k:
            return graph_results[:top_k]

        # Google Maps is an external fallback only. Its normalized response is
        # returned as a provisional suggestion and is never promoted into the
        # canonical Knowledge Graph by this read path.
        if self.gmaps_client is not None:
            gmaps_results = await self._search_google_maps_fallback(
                cleaned,
                dest,
                limit=top_k,
            )
            graph_results = _merge_place_suggestions(
                graph_results,
                gmaps_results,
                limit=top_k,
            )
            if graph_results:
                return graph_results

        if graph_results:
            return graph_results
        return []

    async def _search_google_maps_fallback(
        self,
        query: str,
        destination: str,
        *,
        limit: int = 8,
    ) -> list[PlaceSuggestion]:
        """Fallback to Google Maps when the canonical graph is insufficient."""
        try:
            results = await self.gmaps_client.search(
                query,
                region=destination or None,
                limit=limit,
            )
            suggestions: list[PlaceSuggestion] = []
            for result in results:
                lat = result.get("latitude") or result.get("y")
                lng = result.get("longitude") or result.get("x")
                if lat is None or lng is None:
                    continue

                address = result.get("address") or result.get("complete_address")
                if isinstance(address, dict):
                    address = address.get("formatted") or str(address)

                # Ensure correct types
                rating_val = result.get("review_rating") or result.get("rating")
                if rating_val is not None:
                    try:
                        rating_val = float(rating_val)
                    except (ValueError, TypeError):
                        rating_val = None

                review_count_val = result.get("review_count")
                if review_count_val is not None:
                    try:
                        review_count_val = int(float(review_count_val))
                    except (ValueError, TypeError):
                        review_count_val = None

                price_level_val = result.get("price_level")
                if price_level_val is not None:
                    try:
                        price_level_val = int(price_level_val)
                    except (ValueError, TypeError):
                        price_level_val = None

                suggestions.append(
                    PlaceSuggestion(
                        name=result.get("title") or result.get("name") or query,
                        address=address,
                        latitude=float(lat),
                        longitude=float(lng),
                        placeId=result.get("place_id") or result.get("data_id"),
                        imageUrl=result.get("thumbnail") or result.get("image_url"),
                        rating=rating_val,
                        reviewCount=review_count_val,
                        priceLevel=price_level_val,
                        placeType=result.get("category") or result.get("place_type"),
                        phone=result.get("phone"),
                        website=result.get("website"),
                        openingHours=self._format_opening_hours(result.get("opening_hours")),
                        isVerified=False,
                        source="google_maps_scraper",
                    )
                )
            return suggestions
        except Exception as e:
            logger.warning(f"Google Maps fallback search failed: {e}")
            return []

    def _format_opening_hours(
        self, hours: Any
    ) -> list[str] | None:
        """Format opening hours from various formats to list of strings."""
        if hours is None:
            return None
        if isinstance(hours, list):
            result = []
            for h in hours:
                if isinstance(h, str):
                    result.append(h)
                elif isinstance(h, dict):
                    # Format: {dayName: "Thứ Hai", rawTimeSlots: "08:00-22:00"}
                    day = h.get("dayName", "")
                    slots = h.get("rawTimeSlots", "")
                    if day and slots:
                        result.append(f"{day}: {slots}")
                    elif slots:
                        result.append(slots)
            return result if result else None
        return None

    def _search_knowledge_graph(
        self,
        query: str,
        destination: str,
        *,
        limit: int,
    ) -> list[PlaceSuggestion]:
        if self.graph_place_repository is None:
            return []
        records = self.graph_place_repository.search(
            query,
            destination or None,
            limit=limit,
        )
        return [
            PlaceSuggestion(
                name=record.name,
                address=record.address,
                latitude=record.latitude,
                longitude=record.longitude,
                placeId=record.entity_id,
                imageUrl=record.image_url,
                rating=record.rating,
                reviewCount=record.review_count,
                priceLevel=record.price_level,
                placeType=record.entity_type,
                phone=record.phone,
                website=record.website,
                openingHours=record.opening_hours,
                isVerified=record.status == "verified",
                source="knowledge_graph",
            )
            for record in records
        ]

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
            placeId=request.place_id or place_id,
            name=request.name,
            address=address,
            timeWindow=time_window,
            placeType=request.place_type,
            source="manual",
            durationMinutes=request.duration_minutes,
            tags=request.tags,
            latitude=lat,
            longitude=lng,
            personalNotes=request.personal_notes,
            rating=request.rating,
            reviewCount=request.review_count,
            imageUrls=request.image_urls or [],
        )

        items = list(day.items)
        if request.position is not None and 0 <= request.position <= len(items):
            items.insert(request.position, new_item)
        else:
            items.append(new_item)

        updated_day = self._reoptimize_day(day, items)
        added_name_key = _search_key(request.name)
        remaining_unscheduled = [
            item
            for item in plan.unscheduled_places
            if not (
                request.place_id is not None
                and item.place_id == request.place_id
            )
            and _search_key(item.name) != added_name_key
        ]
        normalized_plan = plan.model_copy(
            update={"unscheduled_places": remaining_unscheduled}
        )
        return self._finalize_mutation(normalized_plan, [updated_day])

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

    def remove_unscheduled_place(
        self,
        plan: Plan,
        *,
        name: str,
        place_id: str | None = None,
    ) -> MutationResponse:
        name_key = _search_key(name)
        remaining = [
            item
            for item in plan.unscheduled_places
            if not (
                (place_id is not None and item.place_id == place_id)
                or _search_key(item.name) == name_key
            )
        ]
        if len(remaining) == len(plan.unscheduled_places):
            raise AppError(
                404,
                "UNSCHEDULED_PLACE_NOT_FOUND",
                "Không tìm thấy địa điểm trong danh sách chưa xếp lịch.",
            )

        updated_plan = plan.model_copy(update={"unscheduled_places": remaining})
        return self._finalize_mutation(updated_plan, [])

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

        updated_day = self._reoptimize_day(
            day,
            reordered_items,
            reuse_transport_legs=True,
        )
        return self._finalize_mutation(plan, [updated_day])

    def select_transport_option(
        self,
        plan: Plan,
        day_number: int,
        leg_index: int,
        request: SelectTransportOptionRequest,
    ) -> MutationResponse:
        day = self._get_day(plan, day_number)
        if leg_index < 0 or leg_index >= len(day.transport_legs):
            raise AppError(
                404,
                "TRANSPORT_LEG_NOT_FOUND",
                f"Không tìm thấy chặng di chuyển trong Ngày {day_number}.",
            )

        current_leg = day.transport_legs[leg_index]
        candidates = [_option_from_leg(current_leg), *current_leg.alternatives]
        selected = next(
            (
                option
                for option in candidates
                if request.option_key
                and _transport_option_selection_key(option) == request.option_key
            ),
            None,
        )
        mode_matches = [
            option
            for option in candidates
            if option.mode.casefold() == request.mode.casefold()
        ]
        selected = selected or next(
            (
                option
                for option in mode_matches
                if _transport_option_matches_request(option, request)
            ),
            None,
        ) or (mode_matches[0] if mode_matches else None)
        if selected is None:
            raise AppError(
                400,
                "TRANSPORT_OPTION_NOT_AVAILABLE",
                "Phương tiện này không có trong các lựa chọn của chặng.",
            )

        next_alternatives: list[PlanTransportOption] = []
        alternative_keys: set[tuple[str, str, int, int]] = set()
        for option in candidates:
            if option is selected:
                continue
            key = _transport_option_key(option)
            if key in alternative_keys:
                continue
            alternative_keys.add(key)
            next_alternatives.append(option)

        updated_leg = current_leg.model_copy(
            update={
                "mode": selected.mode,
                "distance_meters": selected.distance_meters,
                "estimated_duration_minutes": selected.estimated_duration_minutes,
                "geometry_coordinates": selected.geometry_coordinates,
                "source": selected.source,
                "verified": selected.verified,
                "fetched_at": selected.fetched_at,
                "details": selected.details,
                "alternatives": next_alternatives,
            }
        )
        updated_legs = list(day.transport_legs)
        updated_legs[leg_index] = updated_leg
        updated_day = day.model_copy(update={"transport_legs": updated_legs})
        return self._finalize_mutation(plan, [updated_day])

    def retry_transport_leg(
        self,
        plan: Plan,
        day_number: int,
        leg_index: int,
    ) -> MutationResponse:
        """Recalculate one persisted leg without changing itinerary order."""
        day = self._get_day(plan, day_number)
        if leg_index < 0 or leg_index >= len(day.transport_legs):
            raise AppError(
                404,
                "TRANSPORT_LEG_NOT_FOUND",
                f"Không tìm thấy chặng di chuyển trong Ngày {day_number}.",
            )

        current_leg = day.transport_legs[leg_index]
        origin = _leg_endpoint_item(
            day.items,
            item_id=current_leg.from_item_id,
            place_name=current_leg.from_place,
        )
        destination = _leg_endpoint_item(
            day.items,
            item_id=current_leg.to_item_id,
            place_name=current_leg.to_place,
        )
        if origin is None or destination is None:
            raise AppError(
                400,
                "TRANSPORT_LEG_ENDPOINT_NOT_FOUND",
                "Không tìm thấy hai địa điểm của chặng cần tính lại.",
            )
        if any(
            coordinate is None
            for coordinate in (
                origin.latitude,
                origin.longitude,
                destination.latitude,
                destination.longitude,
            )
        ):
            raise AppError(
                400,
                "TRANSPORT_LEG_COORDINATES_REQUIRED",
                "Chưa có đủ tọa độ để tính lại chặng này.",
            )

        retried = self.route_optimizer.calculate_leg(origin, destination)
        has_car_option = any(
            _is_car_mode(option.mode)
            for option in [_option_from_leg(retried), *retried.alternatives]
        )
        if (
            _is_walking_mode(retried.mode)
            and retried.distance_meters
            > self.route_optimizer.max_walking_distance_meters
            and not has_car_option
        ):
            walking_choice = _option_from_leg(retried)
            car_choice = self.route_optimizer.calculate_leg(
                origin,
                destination,
                requested_mode="car",
            )
            car_choice = car_choice.model_copy(
                update={
                    "alternatives": _deduplicate_transport_options(
                        [walking_choice, *retried.alternatives]
                    )
                }
            )
            retried = car_choice

        updated_legs = list(day.transport_legs)
        updated_legs[leg_index] = retried
        updated_day = day.model_copy(update={"transport_legs": updated_legs})
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

    def _reoptimize_day(
        self,
        day: PlanDay,
        items: list[PlanItem],
        *,
        reuse_transport_legs: bool = False,
    ) -> PlanDay:
        first_time_window = day.items[0].time_window if day.items else None
        adjusted_items = self._readjust_time_windows(
            items,
            first_time_window=first_time_window,
        )
        reusable_legs: list[PlanTransportLeg] | None = None
        if reuse_transport_legs:
            original_windows = {
                item.item_id: item.time_window
                for item in day.items
                if item.item_id
            }
            adjusted_windows = {
                item.item_id: item.time_window
                for item in adjusted_items
                if item.item_id
            }
            # Transit routes are departure-time dependent. Only reuse a leg
            # when its origin keeps the same slot after the reorder.
            reusable_legs = [
                leg
                for leg in day.transport_legs
                if leg.from_item_id
                and original_windows.get(leg.from_item_id)
                == adjusted_windows.get(leg.from_item_id)
            ]
        optimized_items, transport_legs = self.route_optimizer.optimize(
            adjusted_items,
            preserve_order=True,
            day=day.day,
            reusable_legs=reusable_legs,
        )
        return day.model_copy(
            update={
                "items": optimized_items,
                "transport_legs": transport_legs,
            }
        )

    def _readjust_time_windows(
        self,
        items: list[PlanItem],
        *,
        first_time_window: str | None = None,
    ) -> list[PlanItem]:
        if not items:
            return items

        start_min = 9 * 60
        starting_window = first_time_window or items[0].time_window
        if starting_window and "-" in starting_window:
            try:
                sh, sm = map(int, starting_window.split("-")[0].split(":"))
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


def _search_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(without_marks.replace("đ", "d").split())


def _option_from_leg(leg: PlanTransportLeg) -> PlanTransportOption:
    return PlanTransportOption(
        mode=leg.mode,
        distanceMeters=leg.distance_meters,
        estimatedDurationMinutes=leg.estimated_duration_minutes,
        geometryCoordinates=leg.geometry_coordinates,
        source=leg.source,
        verified=leg.verified,
        fetchedAt=leg.fetched_at,
        details=leg.details,
    )


def _leg_endpoint_item(
    items: list[PlanItem],
    *,
    item_id: str | None,
    place_name: str,
) -> PlanItem | None:
    if item_id:
        matched = next((item for item in items if item.item_id == item_id), None)
        if matched is not None:
            return matched
    normalized_name = place_name.strip().casefold()
    return next(
        (item for item in items if item.name.strip().casefold() == normalized_name),
        None,
    )


def _is_walking_mode(mode: str) -> bool:
    normalized = mode.casefold()
    return any(token in normalized for token in ("walk", "pedestrian"))


def _is_car_mode(mode: str) -> bool:
    normalized = mode.casefold()
    return any(
        token in normalized
        for token in ("car", "auto", "drive", "ride", "hailing", "taxi")
    )


def _deduplicate_transport_options(
    options: list[PlanTransportOption],
) -> list[PlanTransportOption]:
    unique: list[PlanTransportOption] = []
    seen: set[tuple[str, str, int, int]] = set()
    for option in options:
        key = _transport_option_key(option)
        if key in seen:
            continue
        seen.add(key)
        unique.append(option)
    return unique


def _transport_option_matches_request(
    option: PlanTransportOption,
    request: SelectTransportOptionRequest,
) -> bool:
    if request.source is not None and option.source != request.source:
        return False
    if (
        request.distance_meters is not None
        and round(option.distance_meters) != round(request.distance_meters)
    ):
        return False
    if (
        request.estimated_duration_minutes is not None
        and option.estimated_duration_minutes != request.estimated_duration_minutes
    ):
        return False
    return True


def _transport_option_key(option: PlanTransportOption) -> tuple[str, str, int, int]:
    return (
        option.mode.casefold(),
        option.source,
        round(option.distance_meters),
        option.estimated_duration_minutes,
    )


def _transport_option_selection_key(option: PlanTransportOption) -> str:
    details = option.details if isinstance(option.details, dict) else {}
    lines = details.get("lines") if isinstance(details.get("lines"), list) else []
    segments = (
        details.get("segments")
        if isinstance(details.get("segments"), list)
        else []
    )
    segment_key = "|".join(
        ":".join(
            [
                str(segment.get("mode", "")),
                str(segment.get("line") or ""),
                str(segment.get("estimatedDurationMinutes", "")),
                str(round(float(segment.get("distanceMeters", 0) or 0))),
            ]
        )
        for segment in segments
        if isinstance(segment, dict)
    )
    return "::".join(
        [
            option.mode.casefold(),
            option.source,
            str(option.estimated_duration_minutes),
            str(round(option.distance_meters)),
            ",".join(str(line) for line in lines),
            segment_key,
        ]
    )


def _merge_place_suggestions(
    primary: list[PlaceSuggestion],
    fallback: list[PlaceSuggestion],
    *,
    limit: int,
) -> list[PlaceSuggestion]:
    merged: list[PlaceSuggestion] = []
    identities: set[str] = set()
    names: set[str] = set()
    for suggestion in [*primary, *fallback]:
        identity = suggestion.place_id.strip() if suggestion.place_id else ""
        name = _search_key(suggestion.name)
        if (identity and identity in identities) or name in names:
            continue
        merged.append(suggestion)
        if identity:
            identities.add(identity)
        names.add(name)
        if len(merged) >= limit:
            break
    return merged
