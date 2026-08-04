import json
import re
import unicodedata
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
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.schema import MainPlanFromExplorerCreate, SelectedPlaceCreate
from app.modules.plans.timing import PlanTimingReport
from app.modules.plans.service import PlanService
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.users.model import User
from app.shared.errors import AppError


class _AddressedPlace(Protocol):
    address: str | None


class _PlaceAddressRepository(Protocol):
    def get(self, place_id: str) -> _AddressedPlace | None: ...


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

    def delete(self, chat_id: str, user: User) -> None:
        self.repository.delete(chat_id, user.id)

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
        force_url_refresh: bool = False,
    ) -> TripChatRead:
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
        current_explorer = (
            self._explorer_with_revision_sources(chat)
            if chat.current_explorer is not None
            else None
        )
        raw_request = self._contextual_request(chat, content, current_explorer)
        destination = (
            current_plan.destination
            if current_plan is not None
            else initial_destination
        )
        trip_spec = (
            ExploreTripSpecInput.model_validate(
                current_explorer.trip_spec.model_dump(mode="json", by_alias=True)
            )
            if current_explorer is not None
            else ExploreTripSpecInput()
        )
        requested_days = _explicit_day_count(content)
        requests_more_days = requested_days is None and _requests_more_days(content)
        if requested_days is not None:
            trip_spec.days = requested_days
        elif requests_more_days:
            # Let the new intake infer initial URL coverage. The planning service
            # expands again after old and newly imported Places are merged.
            trip_spec.days = None
        profile = LongTermPreferenceProfile.from_storage(user.travel_preferences)
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
        if current_explorer is not None:
            explore.explorer.candidate_reviews = _merge_candidate_reviews(
                current_explorer.candidate_reviews,
                explore.explorer.candidate_reviews,
            )
        duration_is_fixed = (
            not requests_more_days
            and (
                requested_days is not None
                or _contains_explicit_trip_dates(content)
                or _chat_has_fixed_trip_duration(chat, current_explorer)
                or bool(
                    explore.explorer.trip_spec.start_date
                    and explore.explorer.trip_spec.end_date
                )
            )
        )
        next_plan, planner_timing = await (
            self.plan_service.create_main_plan_from_explorer_with_timing(
                MainPlanFromExplorerCreate(
                    intent=explore.explorer.intent,
                    tripSpec=explore.explorer.trip_spec,
                    intakeId=explore.intake_id,
                    userId=str(user.id),
                    selectedPlaces=self._selected_places_from(
                        current_plan,
                        (
                            current_explorer.candidate_reviews
                            if current_explorer is not None
                            else []
                        ),
                    ),
                    candidateReviews=explore.explorer.candidate_reviews,
                    preferenceProfile=(
                        explore.explorer.preference_snapshot.effective_profile
                    ),
                    allowPlaceSuggestions=explore.allow_place_suggestions,
                    expandDaysToFitSelectedPlaces=not duration_is_fixed,
                )
            )
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
            explorer_payload=explore.explorer.model_dump(mode="json", by_alias=True),
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
        )
        return self._read(
            saved,
            latest_timing=explore.timing_report,
            latest_planner_timing=planner_timing,
        )

    def _contextual_request(
        self,
        chat: TripChat,
        content: str,
        current_explorer: ExplorerContextResponse | None,
    ) -> str:
        if current_explorer is None:
            return content
        previous_requests = [
            message.content
            for message in chat.messages
            if message.role == "user"
        ][-8:]
        context = {
            "currentIntent": current_explorer.intent.model_dump(
                mode="json",
                by_alias=True,
            ),
            "currentTripSpec": current_explorer.trip_spec.model_dump(
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
                personalNotes=item.personal_notes,
                imageUrls=item.image_urls,
                rating=item.rating,
                reviewCount=item.review_count,
                sourceOrder=(
                    item.source_order
                    if _is_reference_item(item.source_refs)
                    else None
                ),
                sourceDay=(
                    item.source_day
                    if _is_reference_item(item.source_refs)
                    else None
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
        if (
            latest_planner_timing is None
            and chat.latest_planner_timing is not None
        ):
            latest_planner_timing = PlanTimingReport.model_validate(
                chat.latest_planner_timing
            )
        summary = self._summary(chat)
        current_explorer = self._explorer_with_revision_sources(chat)
        current_plan = (
            self._with_missing_addresses(
                Plan.model_validate(chat.current_plan),
                current_explorer,
            )
            if chat.current_plan is not None
            else None
        )
        return TripChatRead(
            **summary.model_dump(),
            currentPlan=current_plan,
            currentIntakeId=chat.current_intake_id,
            currentExplorer=current_explorer,
            latestExplorerTiming=latest_timing,
            latestPlannerTiming=latest_planner_timing,
            messages=chat.messages,
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
                if item.address:
                    continue
                if item.place_id and self.place_repository is not None:
                    stored = self.place_repository.get(item.place_id)
                    if stored is not None and stored.address:
                        item.address = stored.address
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

    def _explorer_with_revision_sources(
        self,
        chat: TripChat,
    ) -> ExplorerContextResponse | None:
        if chat.current_explorer is None:
            return None
        current = ExplorerContextResponse.model_validate(chat.current_explorer)
        reviews: list[PlaceCandidateReview] = []
        for revision in chat.plan_revisions:
            revision_explorer = ExplorerContextResponse.model_validate(
                revision.explorer_payload
            )
            reviews = _merge_candidate_reviews(
                reviews,
                revision_explorer.candidate_reviews,
            )
        reviews = _merge_candidate_reviews(reviews, current.candidate_reviews)
        return current.model_copy(update={"candidate_reviews": reviews})

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
        if chat.current_explorer is None or chat.current_plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_EXPLORER",
                "Chưa có kết quả Explorer để thử resolve lại.",
            )
        explorer = ExplorerContextResponse.model_validate(chat.current_explorer)
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
            if review.candidate_id in pending_before
            and review.status == "resolved"
        ]
        updated_explorer = explorer.model_copy(
            update={"candidate_reviews": reviews}
        )
        current_plan = Plan.model_validate(chat.current_plan)
        next_plan = current_plan
        planner_timing: PlanTimingReport | None = None
        if newly_resolved:
            selected_places = [
                *self._selected_places_from(current_plan),
                *[_selected_place_from_review(review) for review in newly_resolved],
            ]
            next_plan, planner_timing = await (
                self.plan_service.create_main_plan_from_explorer_with_timing(
                    MainPlanFromExplorerCreate(
                        intent=updated_explorer.intent,
                        tripSpec=updated_explorer.trip_spec,
                        intakeId=chat.current_intake_id,
                        userId=str(user.id),
                        selectedPlaces=selected_places,
                        candidateReviews=updated_explorer.candidate_reviews,
                        preferenceProfile=(
                            updated_explorer.preference_snapshot.effective_profile
                        ),
                        allowPlaceSuggestions=not any(
                            review.source_urls for review in reviews
                        ),
                    )
                )
            )
            next_plan = next_plan.model_copy(update={"id": current_plan.id})
            self.plan_service.repository.save(next_plan)

        revision = chat.revision + 1
        still_pending = sum(
            review.status == "needs_review" for review in reviews
        )
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=(
                f"Đã xác minh thêm {len(newly_resolved)} địa điểm; "
                f"còn {still_pending} địa điểm cần xem lại "
                f"(bản sửa đổi {revision}). Video, STT và OCR không chạy lại."
            ),
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            explorer_payload=updated_explorer.model_dump(
                mode="json",
                by_alias=True,
            ),
            planner_timing_payload=(
                planner_timing.model_dump(mode="json", by_alias=True)
                if planner_timing is not None
                else None
            ),
            revision=revision,
        )
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
        summary = f"Đã thêm địa điểm '{payload.name}' vào Ngày {payload.day} (bản sửa đổi {revision})."
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=summary,
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
        summary = f"Đã cập nhật thông tin địa điểm trong Ngày {day} (bản sửa đổi {revision})."
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=summary,
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
        summary = f"Đã xóa địa điểm khỏi Ngày {day} (bản sửa đổi {revision})."
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=summary,
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
        )
        self.plan_service.repository.save(result.plan)

        revision = chat.revision + 1
        summary = f"Đã xóa địa điểm '{name}' khỏi danh sách chưa xếp lịch (bản sửa đổi {revision})."
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=summary,
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
        summary = f"Đã sắp xếp lại thứ tự địa điểm Ngày {day} (bản sửa đổi {revision})."
        saved = self.repository.save_plan_mutation(
            chat,
            action_summary=summary,
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
    current_explorer: ExplorerContextResponse | None,
) -> bool:
    if current_explorer is not None and (
        current_explorer.trip_spec.start_date
        and current_explorer.trip_spec.end_date
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
            next_review.status == "resolved"
            and saved_review.status != "resolved"
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
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
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


def _is_reference_item(source_refs: list[str]) -> bool:
    return any(
        ref == "ocr" or ref.startswith(("http://", "https://"))
        for ref in source_refs
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
