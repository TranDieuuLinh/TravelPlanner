import json
from typing import Callable
import re
import unicodedata
from collections.abc import Callable
from typing import Protocol

from app.modules.plans.chat_model import TripChat
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_schema import TripChatRead, TripChatSummaryRead
from app.modules.plans.domain.entities import Plan, PlanItem
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    ExploreTripSpecInput,
    ExplorerContextResponse,
    ExplorerTimingReport,
    PlaceCandidateReview,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    ReorderItemsRequest,
    SelectTransportOptionRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.schema import MainPlanFromTripIntentCreate, SelectedPlaceCreate
from app.modules.plans.timing import PlanTimingReport
from app.modules.plans.service import PlanService
from app.modules.plans.trip_intent import TripIntent
from app.modules.plans.trip_theme_planner.region_context import (
    canonical_destination_name,
)
from app.modules.preferences.repository import TravelerProfileRepository
from app.modules.users.model import User
from app.shared.errors import AppError


class _PlaceImage(Protocol):
    image_url: str


class _AddressedPlace(Protocol):
    address: str | None
    images: list[_PlaceImage]


class _PlaceAddressRepository(Protocol):
    def get(self, place_id: str) -> _AddressedPlace | None: ...


def _is_confirmed_destination(value: str) -> bool:
    return value.strip().casefold() not in {"", "unspecified"}


class TripChatService:
    def __init__(
        self,
        repository: TripChatRepository,
        plan_service: PlanService,
        mutation_service: PlanMutationService | None = None,
        place_repository: _PlaceAddressRepository | None = None,
    ) -> None:
        self.repository = repository
        self.plan_service = plan_service
        self.mutation_service = mutation_service or PlanMutationService()
        self.place_repository = place_repository

    def create(self, user: User, title: str | None = None) -> TripChatRead:
        normalized_title = (title or "").strip() or "Chuyến đi mới"
        chat = self.repository.create(user.id, normalized_title)
        return self._read(chat)

    def list_for_user(self, user: User) -> list[TripChatSummaryRead]:
        return [self._summary(chat) for chat in self.repository.list_for_user(user.id)]

    def get(self, chat_id: str, user: User) -> TripChatRead:
        return self._read(self.repository.get(chat_id, user.id))

    def enrich_routes(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã thay đổi trước khi hoàn tất tuyến đường.",
            )
        if chat.current_plan is None:
            raise AppError(409, "PLAN_NOT_READY", "Lịch trình chưa sẵn sàng.")
        plan = Plan.model_validate(chat.current_plan)
        if plan.route_enrichment_status == "completed":
            return self._read(chat)
        enriched = self.plan_service.enrich_plan_routes(plan)
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=enriched.model_dump(mode="json", by_alias=True),
            revision=chat.revision + 1,
        )
        return self._read(saved)

    def delete(self, chat_id: str, user: User) -> None:
        self.repository.delete(chat_id, user.id)

    def delete_all_for_user(self, user: User) -> None:
        self.repository.delete_all_for_user(user.id)

    def update_trip_intent(
        self,
        chat_id: str,
        user: User,
        *,
        trip_intent: TripIntent,
        expected_revision: int,
        expected_trip_intent_version: int,
    ) -> TripChatRead:
        """Persist a canonical edit immediately; the durable worker replans."""
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        destination = trip_intent.destination.strip()
        if not _is_confirmed_destination(destination):
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Điểm đến không được để trống.",
                {"tripIntent.destination": "Chọn một điểm đến cụ thể."},
            )
        if chat.current_plan is None or chat.current_trip_intent is None:
            raise AppError(
                409,
                "TRIP_INTENT_NOT_READY",
                "Hãy tạo lịch trình đầu tiên trước khi chỉnh trực tiếp thông tin chuyến đi.",
            )

        normalized_intent = trip_intent.model_copy(update={"destination": destination})
        title = (
            f"Chuyến đi {destination}"[:255]
            if chat.title == "Chuyến đi mới"
            else chat.title
        )
        saved = self.repository.save_trip_intent_update(
            chat,
            trip_intent=normalized_intent,
            expected_revision=expected_revision,
            expected_trip_intent_version=expected_trip_intent_version,
            destination=destination,
            title=title,
        )
        return self._read(saved)

    async def regenerate_trip_intent_plan(
        self,
        chat_id: str,
        user: User,
        *,
        trip_intent: TripIntent,
        expected_revision: int,
        expected_trip_intent_version: int,
    ) -> TripChatRead:
        """Run the expensive Planner stage for one persisted intent version."""
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã thay đổi trong lúc Planner đang chạy.",
            )
        if chat.trip_intent_version != expected_trip_intent_version:
            raise AppError(
                409,
                "TRIP_INTENT_SUPERSEDED",
                "Thông tin chuyến đi mới hơn đang chờ được xử lý.",
            )
        current_plan = Plan.model_validate(chat.current_plan)
        destination = trip_intent.destination.strip()
        normalized_intent = trip_intent.model_copy(update={"destination": destination})
        destination_changed = (
            current_plan.destination.strip().casefold() != destination.casefold()
        )
        candidate_reviews = (
            [] if destination_changed else self.repository.load_candidate_reviews(chat)
        )
        selected_places = (
            []
            if destination_changed
            else self._selected_places_from(current_plan, candidate_reviews)
        )
        intake_id = None if destination_changed else chat.current_intake_id
        preference_profile = TravelerProfileRepository(self.repository.db).get(user.id)
        current_context = self._current_context(chat)

        next_plan, planner_timing = (
            await self.plan_service.create_main_plan_from_trip_intent_with_timing(
                MainPlanFromTripIntentCreate(
                    tripIntent=normalized_intent,
                    intakeId=intake_id,
                    userId=str(user.id),
                    selectedPlaces=selected_places,
                    candidateReviews=candidate_reviews,
                    preferenceProfile=preference_profile,
                    allowFinderGapFill=True,
                    allowReplaceSourcePlaces=False,
                    expandDaysToFitSelectedPlaces=False,
                ),
                reuse_theme_plan=(
                    current_plan
                    if _theme_inputs_unchanged(
                        current_context.trip_intent if current_context else None,
                        normalized_intent,
                    )
                    else None
                ),
            )
        )
        next_plan = next_plan.model_copy(update={"id": current_plan.id})
        self.plan_service.repository.save(next_plan)
        revision = chat.revision + 1
        title = (
            f"Chuyến đi {destination}"[:255]
            if chat.title == "Chuyến đi mới"
            else chat.title
        )
        saved = self.repository.save_trip_intent_revision(
            chat,
            trip_intent=normalized_intent,
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            planner_timing_payload=planner_timing.model_dump(
                mode="json", by_alias=True
            ),
            intake_id=intake_id,
            destination=destination,
            title=title,
            revision=revision,
            expected_trip_intent_version=expected_trip_intent_version,
        )
        return self._read(saved, latest_planner_timing=planner_timing)

    async def amend(
        self,
        chat_id: str,
        user: User,
        *,
        content: str,
        expected_revision: int,
        initial_destination: str,
        urls: list[str],
        images: list[ImageUploadPayload],
        initial_trip_days: int | None = None,
        force_url_refresh: bool = False,
        turn_id: str | None = None,
        on_explore_complete: Callable[[ExplorerTimingReport | None], None]
        | None = None,
        on_planner_timing: Callable[[PlanTimingReport], None] | None = None,
    ) -> TripChatRead:
        """Generate (or regenerate) a plan from a free-form prompt + attachments.

        This is the legacy path used by the URL import job worker and by
        callers that pre-date the conversation supervisor. Production traffic
        now flows through :class:`ConversationTurnService` (see ``chat_router``)
        which gives the user the supervisor's confirmation / cancel semantics.
        The two paths share :meth:`generate_plan_revision` so the persisted
        plan revisions look identical regardless of which entrypoint wrote
        them.
        """
        return await self.generate_plan_revision(
            chat_id=chat_id,
            user=user,
            content=content,
            expected_revision=expected_revision,
            initial_destination=initial_destination,
            urls=urls,
            images=images,
            initial_trip_days=initial_trip_days,
            force_url_refresh=force_url_refresh,
            turn_id=turn_id,
            on_explore_complete=on_explore_complete,
            on_planner_timing=on_planner_timing,
        )

    async def generate_plan_revision(
        self,
        *,
        chat_id: str,
        user: User,
        content: str,
        expected_revision: int,
        initial_destination: str,
        urls: list[str],
        images: list[ImageUploadPayload],
        initial_trip_days: int | None = None,
        force_url_refresh: bool = False,
        turn_id: str | None = None,
        on_explore_complete: Callable[[ExplorerTimingReport | None], None]
        | None = None,
        on_planner_timing: Callable[[PlanTimingReport], None] | None = None,
    ) -> TripChatRead:
        """Core entrypoint that the supervisor (and the legacy ``amend`` flow)
        both invoke to produce a new plan revision.

        The caller is responsible for authorization; this method only checks
        the optimistic revision token and orchestrates the explore → plan
        pipeline. It is safe to call from inside another service as long as
        the chat is owned by ``user``.
        """
        if not content.strip():
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Nội dung yêu cầu không được để trống.",
                {"content": "Nhập yêu cầu tạo hoặc sửa lịch trình."},
            )
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi gửi.",
            )

        current_plan = (
            Plan.model_validate(chat.current_plan)
            if chat.current_plan is not None
            else None
        )
        current_context = self._current_context(chat)
        raw_request = self._contextual_request(chat, content, current_context)
        destination = (
            current_plan.destination
            if current_plan is not None
            else initial_destination
        )
        trip_spec = (
            ExploreTripSpecInput.model_validate(
                current_context.trip_spec.model_dump(mode="json", by_alias=True)
            )
            if current_context is not None
            else ExploreTripSpecInput()
        )
        requested_days = initial_trip_days or _explicit_day_count(content)
        requests_more_days = requested_days is None and _requests_more_days(content)
        if requested_days is not None:
            trip_spec.days = requested_days
        elif requests_more_days:
            # Let the new intake infer initial URL coverage. The planning service
            # expands again after old and newly imported Places are merged.
            trip_spec.days = None
        profile = TravelerProfileRepository(self.repository.db).get(user.id)
        user_state = UserPlanningState(
            userId=str(user.id),
            travelPreferences=profile.explicit,
            preferenceProfile=profile,
        )
        explore = await self.plan_service.explore_from_intake(
            raw_request=raw_request,
            destination=destination,
            urls=urls,
            images=images,
            trip_spec=trip_spec,
            user_state=user_state,
            force_url_refresh=force_url_refresh,
        )
        self._canonicalize_explorer_destination(explore)
        if current_context is not None:
            explore.explorer.candidate_reviews = _merge_candidate_reviews(
                current_context.candidate_reviews,
                explore.explorer.candidate_reviews,
            )
        if not _is_confirmed_destination(explore.explorer.trip_intent.destination):
            question = _missing_destination_question(explore.explorer.trip_intent)
            saved = self.repository.save_intent_draft(
                chat,
                user_content=content,
                attachment_names=[image.file_name for image in images],
                assistant_content=question,
                trip_intent=explore.explorer.trip_intent,
                candidate_reviews=explore.explorer.candidate_reviews,
                explorer_timing_payload=(
                    explore.timing_report.model_dump(mode="json", by_alias=True)
                    if explore.timing_report is not None
                    else None
                ),
                intake_id=explore.intake_id,
                turn_id=turn_id,
            )
            return self._read(saved, latest_timing=explore.timing_report)
        if on_explore_complete is not None:
            on_explore_complete(explore.timing_report)
        duration_is_fixed = not requests_more_days and (
            requested_days is not None
            or _contains_explicit_trip_dates(content)
            or _chat_has_fixed_trip_duration(chat, current_context)
            or bool(
                explore.explorer.trip_spec.start_date
                and explore.explorer.trip_spec.end_date
            )
        )
        planner_input = MainPlanFromTripIntentCreate(
                tripIntent=explore.explorer.trip_intent,
                intakeId=explore.intake_id,
                userId=str(user.id),
                selectedPlaces=self._selected_places_from(
                    current_plan,
                    (
                        current_context.candidate_reviews
                        if current_context is not None
                        else []
                    ),
                ),
                candidateReviews=explore.explorer.candidate_reviews,
                preferenceProfile=(
                    explore.explorer.preference_snapshot.effective_profile
                ),
                allowFinderGapFill=True,
                allowReplaceSourcePlaces=False,
                expandDaysToFitSelectedPlaces=not duration_is_fixed,
        )
        planner_kwargs = (
            {"on_timing_update": on_planner_timing}
            if on_planner_timing is not None
            else {}
        )
        (
            next_plan,
            planner_timing,
        ) = await self.plan_service.create_main_plan_from_trip_intent_with_timing(
            planner_input,
            reuse_theme_plan=(
                current_plan
                if current_plan is not None
                and _theme_inputs_unchanged(
                    current_context.trip_intent if current_context else None,
                    explore.explorer.trip_intent,
                )
                else None
            ),
            **planner_kwargs,
        )
        if current_plan is not None:
            next_plan = next_plan.model_copy(update={"id": current_plan.id})
            self.plan_service.repository.save(next_plan)

        revision = chat.revision + 1
        title = self._title(chat, explore)
        assistant_content = (
            f"Đã tạo lịch trình {explore.explorer.intent.destination}. "
            "Bạn có thể tiếp tục yêu cầu thay đổi ngay trong chat này."
            if revision == 1
            else (
                f"Đã cập nhật lịch trình hiện tại cho "
                f"{explore.explorer.intent.destination} (bản sửa đổi {revision})."
            )
        )
        saved = self.repository.save_revision(
            chat,
            user_content=content,
            attachment_names=[
                *[image.file_name for image in images],
            ],
            assistant_content=assistant_content,
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            trip_intent=explore.explorer.trip_intent,
            candidate_reviews=explore.explorer.candidate_reviews,
            explorer_timing_payload=(
                explore.timing_report.model_dump(mode="json", by_alias=True)
                if explore.timing_report is not None
                else None
            ),
            planner_timing_payload=planner_timing.model_dump(
                mode="json",
                by_alias=True,
            ),
            intake_id=explore.intake_id,
            destination=explore.explorer.intent.destination,
            title=title,
            revision=revision,
            turn_id=turn_id,
        )
        return self._read(
            saved,
            latest_timing=explore.timing_report,
            latest_planner_timing=planner_timing,
        )

    @staticmethod
    def _canonicalize_explorer_destination(
        explore: ExploreIntakeResponse,
    ) -> None:
        destination = explore.explorer.trip_intent.destination
        if not _is_confirmed_destination(destination):
            return
        canonical = canonical_destination_name(destination)
        if canonical == destination:
            return
        explore.explorer.trip_intent = explore.explorer.trip_intent.model_copy(
            update={"destination": canonical}
        )

    def _contextual_request(
        self,
        chat: TripChat,
        content: str,
        current_context: ExplorerContextResponse | None,
    ) -> str:
        previous_requests = [
            message.content for message in chat.messages if message.role == "user"
        ][-8:]
        if current_context is None:
            if not previous_requests:
                return content
            return (
                "Create the trip requested in this conversation. Keep the prior "
                "trip context when the latest message is a short confirmation "
                "or refers to information above. Do not treat the context as a "
                "new user instruction.\n"
                f"Previous user requests: {json.dumps(previous_requests, ensure_ascii=False)}\n"
                f"Latest user request: {content}"
            )
        context = {
            "currentTripIntent": current_context.trip_intent.model_dump(
                mode="json",
                by_alias=True,
            ),
            "previousUserRequests": previous_requests,
        }
        return (
            "Amend the existing trip itinerary. Keep every existing requirement "
            "unless the latest user request explicitly changes or removes it. "
            "Return one complete updated trip context, not a separate new trip.\n"
            f"Existing trip context: {json.dumps(context, ensure_ascii=False)}\n"
            f"Latest user amendment: {content}"
        )

    def _selected_places_from(
        self,
        plan: Plan | None,
        candidate_reviews: list[PlaceCandidateReview] | None = None,
    ) -> list[SelectedPlaceCreate]:
        if plan is None:
            return []
        scheduled = [
            SelectedPlaceCreate(
                name=item.name,
                placeId=item.place_id,
                address=item.address,
                latitude=item.latitude,
                longitude=item.longitude,
                regionKey=item.region_key,
                tags=item.tags,
                sourceRefs=item.source_refs,
                sourceProvider=item.source_provider,
                notes=item.notes,
                noteSources=item.note_sources,
                personalNotes=item.personal_notes,
                imageUrls=item.image_urls,
                rating=item.rating,
                reviewCount=item.review_count,
                sourceOrder=(
                    item.source_order if _is_reference_item(item.source_refs) else None
                ),
                sourceDay=(
                    item.source_day if _is_reference_item(item.source_refs) else None
                ),
                sourceTimeHint=item.source_time_hint,
                sourceActivity=item.source_activity,
                sourceDurationMinutes=item.duration_minutes,
            )
            for day in plan.days
            for item in day.items
            # PlaceSelector output is disposable and must not become user intent on
            # the next URL revision. Otherwise suggestions accumulate across
            # generations and consume the requested trip capacity.
            if item.place_type not in {"break", "free_time"}
            and item.source in {"selected_place", "manual"}
        ]
        # A previous URL revision may have put a resolved source place in
        # UnscheduledPlace. Rehydrate it from Explorer provenance so the next
        # URL revision cannot silently lose it; PlanService will expand days
        # and dedupe it against already scheduled items.
        resolved_url_places = [
            _selected_place_from_review(review)
            for review in (candidate_reviews or [])
            if review.status == "resolved" and review.source_urls
        ]
        return [*scheduled, *resolved_url_places]

    def _title(self, chat: TripChat, explore: ExploreIntakeResponse) -> str:
        if chat.title != "Chuyến đi mới":
            return chat.title
        return f"Chuyến đi {explore.explorer.intent.destination}"[:255]

    def _summary(self, chat: TripChat) -> TripChatSummaryRead:
        return TripChatSummaryRead(
            id=chat.id,
            title=chat.title,
            destination=chat.destination,
            revision=chat.revision,
            hasPlan=chat.current_plan is not None,
            createdAt=chat.created_at,
            updatedAt=chat.updated_at,
        )

    def _read(
        self,
        chat: TripChat,
        *,
        latest_timing: ExplorerTimingReport | None = None,
        latest_planner_timing: PlanTimingReport | None = None,
    ) -> TripChatRead:
        if latest_timing is None and chat.latest_explorer_timing is not None:
            latest_timing = ExplorerTimingReport.model_validate(
                chat.latest_explorer_timing
            )
        if latest_planner_timing is None and chat.latest_planner_timing is not None:
            latest_planner_timing = PlanTimingReport.model_validate(
                chat.latest_planner_timing
            )
        summary = self._summary(chat)
        current_context = self._current_context(chat)
        current_plan = (
            self._with_missing_addresses(
                Plan.model_validate(chat.current_plan),
                current_context,
            )
            if chat.current_plan is not None
            else None
        )
        return TripChatRead(
            **summary.model_dump(),
            currentPlan=current_plan,
            currentIntakeId=chat.current_intake_id,
            currentTripIntent=(
                current_context.trip_intent if current_context is not None else None
            ),
            tripIntentVersion=chat.trip_intent_version,
            tripIntentPlanStatus=chat.trip_intent_plan_status,
            candidateReviews=(
                current_context.candidate_reviews if current_context is not None else []
            ),
            latestExplorerTiming=latest_timing,
            latestPlannerTiming=latest_planner_timing,
            messages=chat.messages,
            turns=self.repository.list_recent_turns(chat.id, chat.user_id),
        )

    def _with_missing_addresses(
        self,
        plan: Plan,
        explorer: ExplorerContextResponse | None,
    ) -> Plan:
        hydrated = plan.model_copy(deep=True)
        reviews = [
            review
            for review in (explorer.candidate_reviews if explorer else [])
            if review.status == "resolved" and review.address
        ]
        for day in hydrated.days:
            for item in day.items:
                stored = None
                if (
                    item.place_id
                    and self.place_repository is not None
                    and (not item.address or not item.image_urls)
                ):
                    stored = self.place_repository.get(item.place_id)
                    if stored is not None and not item.address and stored.address:
                        item.address = stored.address
                    if stored is not None and not item.image_urls:
                        item.image_urls = list(
                            dict.fromkeys(
                                image.image_url
                                for image in stored.images
                                if image.image_url
                            )
                        )
                if item.address:
                    continue
                matching_review = next(
                    (
                        review
                        for review in reviews
                        if _review_matches_plan_item(review, item)
                    ),
                    None,
                )
                if matching_review is not None:
                    item.address = matching_review.address
        return hydrated

    def _current_context(
        self,
        chat: TripChat,
    ) -> ExplorerContextResponse | None:
        trip_intent = self.repository.load_trip_intent(chat)
        if trip_intent is None:
            return None
        reviews: list[PlaceCandidateReview] = []
        for review in self.repository.load_candidate_reviews(chat):
            reviews = _merge_candidate_reviews(
                reviews,
                [review],
            )
        return ExplorerContextResponse(
            tripIntent=trip_intent,
            candidateReviews=reviews,
        )

    async def retry_candidate_resolutions(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại trước khi thử lại địa điểm.",
            )
        if chat.current_trip_intent is None or chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_EXPLORER",
                "Chưa có kết quả Explorer để thử resolve lại.",
            )
        explorer = self._current_context(chat)
        if explorer is None:
            raise AppError(
                400,
                "NO_ACTIVE_TRIP_INTENT",
                "Chưa có Trip Intent đã lưu cho cuộc trò chuyện này.",
            )
        pending_before = {
            review.candidate_id
            for review in explorer.candidate_reviews
            if review.status == "needs_review"
        }
        if not pending_before:
            raise AppError(
                409,
                "NO_CANDIDATES_TO_RETRY",
                "Không còn địa điểm nào cần resolve lại.",
            )
        reviews = await self.plan_service.retry_candidate_reviews(
            explorer.candidate_reviews,
            destination=explorer.intent.destination,
        )
        newly_resolved = [
            review
            for review in reviews
            if review.candidate_id in pending_before and review.status == "resolved"
        ]
        updated_explorer = explorer.model_copy(update={"candidate_reviews": reviews})
        current_plan = Plan.model_validate(chat.current_plan)
        next_plan = current_plan
        planner_timing: PlanTimingReport | None = None
        if newly_resolved:
            selected_places = [
                *self._selected_places_from(current_plan),
                *[_selected_place_from_review(review) for review in newly_resolved],
            ]
            (
                next_plan,
                planner_timing,
            ) = await self.plan_service.create_main_plan_from_trip_intent_with_timing(
                MainPlanFromTripIntentCreate(
                    tripIntent=updated_explorer.trip_intent,
                    intakeId=chat.current_intake_id,
                    userId=str(user.id),
                    selectedPlaces=selected_places,
                    candidateReviews=updated_explorer.candidate_reviews,
                    preferenceProfile=(
                        updated_explorer.preference_snapshot.effective_profile
                    ),
                    allowFinderGapFill=True,
                    allowReplaceSourcePlaces=False,
                ),
                reuse_theme_plan=current_plan,
            )
            next_plan = next_plan.model_copy(update={"id": current_plan.id})
            self.plan_service.repository.save(next_plan)

        revision = chat.revision + 1
        still_pending = sum(review.status == "needs_review" for review in reviews)
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=(
                f"Đã xác minh thêm {len(newly_resolved)} địa điểm; "
                f"còn {still_pending} địa điểm cần xem lại "
                f"(bản sửa đổi {revision}). Video, STT và OCR không chạy lại."
            ),
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            planner_timing_payload=(
                planner_timing.model_dump(mode="json", by_alias=True)
                if planner_timing is not None
                else None
            ),
            revision=revision,
        )
        self.repository.replace_candidate_reviews(saved, reviews)
        self.repository.db.commit()
        return self._read(saved)

    async def confirm_candidate_resolution(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        candidate_id: str,
        match_rank: int,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại trước khi chọn địa điểm.",
            )
        if chat.current_trip_intent is None or chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_EXPLORER",
                "Chưa có kết quả Explorer để xác nhận địa điểm.",
            )
        explorer = self._current_context(chat)
        if explorer is None:
            raise AppError(
                400,
                "NO_ACTIVE_TRIP_INTENT",
                "Chưa có Trip Intent đã lưu cho cuộc trò chuyện này.",
            )
        review = next(
            (
                item
                for item in explorer.candidate_reviews
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if review is None or review.status != "needs_review":
            raise AppError(
                404,
                "CANDIDATE_NOT_REVIEWABLE",
                "Địa điểm này không còn cần xác nhận.",
            )
        match = next(
            (item for item in review.top_matches if item.rank == match_rank),
            None,
        )
        if match is None:
            raise AppError(
                404,
                "MATCH_NOT_FOUND",
                "Không tìm thấy kết quả khớp đã chọn cho địa điểm này.",
            )
        if match.latitude is None or match.longitude is None:
            raise AppError(
                422,
                "MATCH_MISSING_LOCATION",
                "Kết quả này chưa có tọa độ nên chưa thể thêm vào lịch trình.",
            )

        confirmed_review = review.model_copy(
            update={
                "status": "resolved",
                "resolution_reason": "user_confirmed_top_match",
                "provider": match.provider,
                "resolved_name": match.name,
                "address": match.address,
                "latitude": match.latitude,
                "longitude": match.longitude,
                "has_representative_location": True,
                "resolution_confidence": max(review.resolution_confidence, match.score),
                "confidence": max(review.confidence, match.score),
                "top_matches": [
                    candidate.model_copy(
                        update={"selected": candidate.rank == match.rank}
                    )
                    for candidate in review.top_matches
                ],
            }
        )
        reviews = [
            confirmed_review if item.candidate_id == candidate_id else item
            for item in explorer.candidate_reviews
        ]
        updated_explorer = explorer.model_copy(update={"candidate_reviews": reviews})
        current_plan = Plan.model_validate(chat.current_plan)
        selected_places = [
            *self._selected_places_from(current_plan),
            _selected_place_from_review(confirmed_review),
        ]
        next_plan, planner_timing = (
            await self.plan_service.create_main_plan_from_trip_intent_with_timing(
                MainPlanFromTripIntentCreate(
                    tripIntent=updated_explorer.trip_intent,
                    intakeId=chat.current_intake_id,
                    userId=str(user.id),
                    selectedPlaces=selected_places,
                    candidateReviews=updated_explorer.candidate_reviews,
                    preferenceProfile=(
                        updated_explorer.preference_snapshot.effective_profile
                    ),
                    allowFinderGapFill=True,
                    allowReplaceSourcePlaces=False,
                ),
                reuse_theme_plan=current_plan,
            )
        )
        next_plan = next_plan.model_copy(update={"id": current_plan.id})
        self.plan_service.repository.save(next_plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=(
                f"Đã chọn {match.name} cho {review.name} "
                f"(bản sửa đổi {revision})."
            ),
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            planner_timing_payload=planner_timing.model_dump(
                mode="json",
                by_alias=True,
            ),
            revision=revision,
        )
        self.repository.replace_candidate_reviews(saved, reviews)
        self.repository.db.commit()
        return self._read(saved)

    async def add_item(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        payload: AddItemRequest,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )
        plan = Plan.model_validate(chat.current_plan)
        result = await self.mutation_service.add_item(plan, payload)
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            # Direct editor actions are persisted as plan revisions, not chat
            # messages. The client acknowledges them with a transient toast.
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    async def update_item(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        day: int,
        item_id: str,
        payload: UpdateItemRequest,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )
        plan = Plan.model_validate(chat.current_plan)
        result = await self.mutation_service.update_item(plan, day, item_id, payload)
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    def remove_item(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        day: int,
        item_id: str,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )
        plan = Plan.model_validate(chat.current_plan)
        result = self.mutation_service.remove_item(plan, day, item_id)
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    def remove_unscheduled_place(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        name: str,
        place_id: str | None = None,
        candidate_id: str | None = None,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )

        plan = Plan.model_validate(chat.current_plan)
        result = self.mutation_service.remove_unscheduled_place(
            plan,
            name=name,
            place_id=place_id,
            candidate_id=candidate_id,
        )
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    def reorder_items(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        day: int,
        payload: ReorderItemsRequest,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )
        plan = Plan.model_validate(chat.current_plan)
        result = self.mutation_service.reorder_items(plan, day, payload)
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    def select_transport_option(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        day: int,
        leg_index: int,
        payload: SelectTransportOptionRequest,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )
        plan = Plan.model_validate(chat.current_plan)
        result = self.mutation_service.select_transport_option(
            plan,
            day,
            leg_index,
            payload,
        )
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            # Route-option clicks are direct UI state changes. Persist their
            # revisions without flooding the conversational Planner history.
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)

    def retry_transport_leg(
        self,
        chat_id: str,
        user: User,
        *,
        expected_revision: int,
        day: int,
        leg_index: int,
    ) -> TripChatRead:
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        if chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình nào được tạo trong cuộc trò chuyện này.",
            )

        plan = Plan.model_validate(chat.current_plan)
        result = self.mutation_service.retry_transport_leg(
            plan,
            day,
            leg_index,
        )
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=None,
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self._read(saved)


def _explicit_day_count(content: str) -> int | None:
    match = re.search(r"\b([1-9]|[12]\d|30)\s*(?:ngày|days?)\b", content.casefold())
    return int(match.group(1)) if match is not None else None


def _contains_explicit_trip_dates(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    date_pattern = (
        r"(?:\b\d{4}-\d{1,2}-\d{1,2}\b|"
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b)"
    )
    return len(re.findall(date_pattern, normalized)) >= 2


def _chat_has_fixed_trip_duration(
    chat: TripChat,
    current_context: ExplorerContextResponse | None,
) -> bool:
    if current_context is not None and (
        current_context.trip_spec.start_date and current_context.trip_spec.end_date
    ):
        return True
    return any(
        message.role == "user"
        and (
            _explicit_day_count(message.content) is not None
            or _contains_explicit_trip_dates(message.content)
        )
        for message in chat.messages
    )


def _merge_candidate_reviews(
    current: list[PlaceCandidateReview],
    incoming: list[PlaceCandidateReview],
) -> list[PlaceCandidateReview]:
    """Keep candidate provenance across sequential URL import jobs."""
    merged = [review.model_copy(deep=True) for review in current]
    for next_review in incoming:
        matching_index = next(
            (
                index
                for index, saved_review in enumerate(merged)
                if _same_candidate(saved_review, next_review)
            ),
            None,
        )
        if matching_index is None:
            merged.append(next_review.model_copy(deep=True))
            continue

        saved_review = merged[matching_index]
        source_urls = list(
            dict.fromkeys([*saved_review.source_urls, *next_review.source_urls])
        )
        incoming_is_better = (
            next_review.status == "resolved" and saved_review.status != "resolved"
        ) or (
            next_review.has_representative_location
            and not saved_review.has_representative_location
        )
        preferred = next_review if incoming_is_better else saved_review
        merged[matching_index] = preferred.model_copy(
            update={
                "candidate_id": saved_review.candidate_id,
                "source_urls": source_urls,
                "confidence": max(
                    saved_review.confidence,
                    next_review.confidence,
                ),
                "extraction_confidence": max(
                    saved_review.extraction_confidence,
                    next_review.extraction_confidence,
                ),
                "resolution_confidence": max(
                    saved_review.resolution_confidence,
                    next_review.resolution_confidence,
                ),
                "retryable": (
                    saved_review.retryable and next_review.retryable
                    if preferred.status != "resolved"
                    else False
                ),
            }
        )
    return merged


def _same_candidate(
    left: PlaceCandidateReview,
    right: PlaceCandidateReview,
) -> bool:
    if (
        left.latitude is not None
        and left.longitude is not None
        and right.latitude is not None
        and right.longitude is not None
    ):
        return (
            round(left.latitude, 5),
            round(left.longitude, 5),
        ) == (
            round(right.latitude, 5),
            round(right.longitude, 5),
        )

    left_names = {
        key
        for value in (left.name, left.resolved_name)
        if value and (key := _candidate_name_key(value))
    }
    right_names = {
        key
        for value in (right.name, right.resolved_name)
        if value and (key := _candidate_name_key(value))
    }
    if not left_names.intersection(right_names):
        return False
    left_region = _candidate_name_key(left.address or left.search_region or "")
    right_region = _candidate_name_key(right.address or right.search_region or "")
    return not left_region or not right_region or left_region == right_region


def _candidate_name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def _review_matches_plan_item(
    review: PlaceCandidateReview,
    item: PlanItem,
) -> bool:
    if (
        review.latitude is not None
        and review.longitude is not None
        and item.latitude is not None
        and item.longitude is not None
        and (round(review.latitude, 5), round(review.longitude, 5))
        == (round(item.latitude, 5), round(item.longitude, 5))
    ):
        return True
    item_name = _candidate_name_key(item.name)
    review_names = {
        _candidate_name_key(name)
        for name in (review.name, review.resolved_name)
        if name
    }
    return bool(item_name and item_name in review_names)


def _requests_more_days(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    return any(
        phrase in normalized
        for phrase in (
            "more day",
            "more days",
            "additional day",
            "additional days",
            "extend the trip",
            "thêm ngày",
            "nhiều ngày hơn",
            "tăng số ngày",
            "kéo dài chuyến",
        )
    )


def _theme_inputs_unchanged(
    current: TripIntent | None,
    incoming: TripIntent,
) -> bool:
    """Compare the canonical intent/spec inputs consumed by TripThemePlanner."""
    if current is None:
        return False
    return (
        current.to_planning_intent().model_dump(mode="json", by_alias=True)
        == incoming.to_planning_intent().model_dump(mode="json", by_alias=True)
        and current.to_trip_spec().model_dump(mode="json", by_alias=True)
        == incoming.to_trip_spec().model_dump(mode="json", by_alias=True)
    )


def _missing_destination_question(trip_intent: TripIntent) -> str:
    must_visit = list(trip_intent.preferences.must_visit_places or [])
    if must_visit:
        places = ", ".join(must_visit[:2])
        if len(must_visit) > 2:
            places += " và một số điểm khác"
        return (
            f"Mình đã ghi nhận bạn muốn ghé {places}. "
            "Bạn muốn đi ở tỉnh hoặc thành phố nào?"
        )
    return "Bạn muốn đi du lịch ở tỉnh hoặc thành phố nào?"


def _is_reference_item(source_refs: list[str]) -> bool:
    return any(
        ref == "ocr" or ref.startswith(("http://", "https://")) for ref in source_refs
    )


def _selected_place_from_review(
    review: PlaceCandidateReview,
) -> SelectedPlaceCreate:
    return SelectedPlaceCreate(
        name=review.resolved_name or review.name,
        address=review.address,
        priority=1,
        mustVisit=True,
        preferenceLevel="must_visit",
        latitude=review.latitude,
        longitude=review.longitude,
        tags=[review.category.value],
        sourceRefs=review.source_urls,
        sourceProvider=review.provider,
        sourceOrder=review.source_order,
        sourceDay=review.source_day,
        sourceTimeHint=review.source_time_hint,
        sourceActivity=review.source_activity,
        sourceDurationMinutes=review.source_duration_minutes,
    )
