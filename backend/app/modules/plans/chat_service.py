import json

from app.modules.plans.chat_model import TripChat
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_schema import TripChatRead, TripChatSummaryRead
from app.modules.plans.domain.entities import Plan
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    ExploreTripSpecInput,
    ExplorerContextResponse,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.schema import MainPlanFromExplorerCreate, SelectedPlaceCreate
from app.modules.plans.service import PlanService
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.users.model import User
from app.shared.errors import AppError


class TripChatService:
    def __init__(
        self,
        repository: TripChatRepository,
        plan_service: PlanService,
    ) -> None:
        self.repository = repository
        self.plan_service = plan_service

    def create(self, user: User, title: str | None = None) -> TripChatRead:
        normalized_title = (title or "").strip() or "Chuyến đi mới"
        chat = self.repository.create(user.id, normalized_title)
        return self._read(chat)

    def list_for_user(self, user: User) -> list[TripChatSummaryRead]:
        return [self._summary(chat) for chat in self.repository.list_for_user(user.id)]

    def get(self, chat_id: str, user: User) -> TripChatRead:
        return self._read(self.repository.get(chat_id, user.id))

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
            ExplorerContextResponse.model_validate(chat.current_explorer)
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
        )
        next_plan = await self.plan_service.create_main_plan_from_explorer(
            MainPlanFromExplorerCreate(
                intent=explore.explorer.intent,
                tripSpec=explore.explorer.trip_spec,
                intakeId=explore.intake_id,
                userId=str(user.id),
                selectedPlaces=self._selected_places_from(current_plan),
                preferenceProfile=explore.explorer.preference_snapshot.effective_profile,
                allowFinderSuggestions=explore.allow_finder_suggestions,
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
            attachment_names=[image.file_name for image in images],
            assistant_content=assistant_content,
            plan_payload=next_plan.model_dump(mode="json", by_alias=True),
            explorer_payload=explore.explorer.model_dump(mode="json", by_alias=True),
            intake_id=explore.intake_id,
            destination=explore.explorer.intent.destination,
            title=title,
            revision=revision,
        )
        return self._read(saved)

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

    def _selected_places_from(self, plan: Plan | None) -> list[SelectedPlaceCreate]:
        if plan is None:
            return []
        return [
            SelectedPlaceCreate(
                name=item.name,
                placeId=item.place_id,
                address=item.address,
                latitude=item.latitude,
                longitude=item.longitude,
                regionKey=item.region_key,
                tags=item.tags,
                sourceRefs=item.source_refs,
                notes=item.notes,
                sourceOrder=item.source_order,
                sourceTimeHint=item.source_time_hint,
                sourceActivity=item.source_activity,
                sourceDurationMinutes=item.duration_minutes,
            )
            for day in plan.days
            for item in day.items
            if item.place_type not in {"break", "free_time"}
        ]

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

    def _read(self, chat: TripChat) -> TripChatRead:
        summary = self._summary(chat)
        return TripChatRead(
            **summary.model_dump(),
            currentPlan=(
                Plan.model_validate(chat.current_plan)
                if chat.current_plan is not None
                else None
            ),
            currentExplorer=(
                ExplorerContextResponse.model_validate(chat.current_explorer)
                if chat.current_explorer is not None
                else None
            ),
            messages=chat.messages,
        )
