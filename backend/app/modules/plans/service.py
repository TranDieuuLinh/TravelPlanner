import asyncio
import math
from uuid import uuid4

from app.modules.plans.domain.entities import Plan
from app.modules.places.resolver import PlaceResolver, ProvisionalPlaceResolver
from app.modules.plans.explorer.place_candidate_aggregator import (
    PlaceCandidateAggregator,
)
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    PlaceCandidateSourceType,
    ExploreTripSpecInput,
    FullExploreRequest,
    PlaceCandidatesResponse,
)
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService, ImageUploadPayload
from app.modules.plans.explorer.tools.url_reels.schema import (
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.repository import PlanRepository
from app.modules.plans.schema import (
    BackupPlanCreate,
    FeatureMapItem,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanBundleRead,
    PlanBundleRead,
    PlanningContextCreate,
    SelectedPlaceCreate,
)
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.preferences.service import PreferenceLearningService
from app.modules.users.repository import UserRepository


class PlanService:
    def __init__(
        self,
        repository: PlanRepository,
        explore_formatter: ExploreResponseFormatter,
        main_workflow: MainPlanWorkflow,
        backup_workflow: BackupPlanWorkflow,
        image_ocr: ImageOcrService | None = None,
        url_reels: UrlReelExtractionService | None = None,
        place_candidate_aggregator: PlaceCandidateAggregator | None = None,
        place_resolver: PlaceResolver | None = None,
        explorer_persistence: ExplorerPersistenceRepository | None = None,
        preference_learning: PreferenceLearningService | None = None,
        user_repository: UserRepository | None = None,
    ) -> None:
        self.repository = repository
        self.explore_formatter = explore_formatter
        self.main_workflow = main_workflow
        self.backup_workflow = backup_workflow
        self.image_ocr = image_ocr
        self.url_reels = url_reels or UrlReelExtractionService()
        self.place_candidate_aggregator = (
            place_candidate_aggregator or PlaceCandidateAggregator()
        )
        self.place_resolver = place_resolver or ProvisionalPlaceResolver()
        self.explorer_persistence = explorer_persistence
        self.preference_learning = (
            preference_learning or PreferenceLearningService()
        )
        self.user_repository = user_repository

    def feature_map(self) -> list[FeatureMapItem]:
        return [
            FeatureMapItem(stage="explore", feature="Explorer", description="Clarify destination, budget, pace, interests, and constraints."),
            FeatureMapItem(stage="create", feature="Planner", description="Generate MacroPlan and DayBriefs for the main itinerary."),
            FeatureMapItem(stage="fill", feature="Finder", description="Choose day windows, fill places, and commit each day."),
            FeatureMapItem(stage="backup", feature="Backup Planner", description="Create a separate backup plan without mutating the locked main plan."),
        ]

    async def explore_full(
        self,
        payload: FullExploreRequest,
    ) -> ExploreIntakeResponse:
        url_reel_results = await self._extract_urls(
            payload.urls,
            destination=payload.destination,
        )
        return await self._format_resolve_and_persist(
            payload,
            url_reel_results=url_reel_results,
        )

    async def explore_from_intake(
        self,
        *,
        raw_request: str,
        destination: str,
        urls: list[str],
        images: list[ImageUploadPayload],
        trip_spec: ExploreTripSpecInput | None = None,
        user_state: UserPlanningState | None = None,
    ) -> ExploreIntakeResponse:
        try:
            if images and self.image_ocr is None:
                raise RuntimeError("Image OCR is not configured.")
            image_task = (
                self.image_ocr.extract_many(
                    images,
                    destination=destination,
                )
                if images and self.image_ocr is not None
                else _empty_list()
            )
            image_contexts, url_reel_results = await asyncio.gather(
                image_task,
                self._extract_urls(urls, destination=destination),
            )

            payload = FullExploreRequest(
                rawRequest=raw_request,
                destination=destination,
                urls=urls,
                userState=user_state or UserPlanningState(),
                tripSpec=trip_spec or ExploreTripSpecInput(),
                imageContexts=image_contexts,
            )
            return await self._format_resolve_and_persist(
                payload,
                url_reel_results=url_reel_results,
            )
        finally:
            for image in images:
                image.clear_data()

    async def _extract_urls(
        self,
        urls: list[str],
        *,
        destination: str,
    ) -> list[UrlReelExtractionResult]:
        return list(
            await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self.url_reels.extract,
                        UrlReelInput(
                            url=url,
                            destination=destination,
                        ),
                    )
                    for url in urls
                )
            )
        )

    async def _format_resolve_and_persist(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[UrlReelExtractionResult],
    ) -> ExploreIntakeResponse:
        explicitly_requested_days = payload.trip_spec.days
        has_reference_input = bool(
            payload.urls or payload.image_contexts
        )
        provisional_reference_days = _url_result_coverage_days(
            url_reel_results
        )
        if payload.trip_spec.days is None and has_reference_input:
            payload = payload.model_copy(deep=True)
            payload.trip_spec.days = provisional_reference_days or 3
        draft = await self.explore_formatter.format(
            payload,
            url_reel_results=url_reel_results,
        )
        candidates = self.place_candidate_aggregator.aggregate(
            destination=payload.destination,
            generated=draft.places.place_candidates,
            explicit=payload.place_candidates,
            url_results=url_reel_results,
        )
        if (
            payload.urls
            and not candidates
            and url_reel_results
        ):
            raise RuntimeError(
                "No evidenced locations could be extracted from the URL. "
                "The media may be unavailable or OCR/STT may have failed. "
                "Retry later, upload screenshots, or paste the caption instead "
                "of generating an empty itinerary."
            )
        draft.places = PlaceCandidatesResponse(placeCandidates=candidates)
        source_coverage_days = _candidate_coverage_days(
            candidates,
            pace=draft.explorer.intent.pace.value,
        )
        effective_days = (
            explicitly_requested_days
            or source_coverage_days
            or draft.explorer.trip_spec.days
            or 3
        )
        draft.explorer.trip_spec.days = effective_days
        if explicitly_requested_days is None and source_coverage_days:
            draft.explorer.assumptions = [
                *draft.explorer.assumptions,
                (
                    f"Trip duration was inferred as {effective_days} days "
                    "from URL/OCR itinerary coverage because the user did "
                    "not specify a duration."
                ),
            ]
        preference_snapshot = self.preference_learning.enrich_snapshot(
            draft.explorer.preference_snapshot,
            destination=draft.explorer.intent.destination,
            candidates=candidates,
            interests=draft.explorer.intent.interests,
        )
        stored_profile: object = payload.user_state.preference_profile
        preference_user = None
        if payload.user_state.user_id and self.user_repository is not None:
            try:
                preference_user = self.user_repository.get_by_id(
                    int(payload.user_state.user_id)
                )
            except ValueError:
                preference_user = None
            if preference_user is not None:
                stored_profile = preference_user.travel_preferences
        effective_profile = self.preference_learning.merge(
            stored_profile,
            preference_snapshot,
        )
        preference_snapshot = preference_snapshot.model_copy(
            update={"effective_profile": effective_profile}
        )
        draft.explorer = draft.explorer.model_copy(
            update={"preference_snapshot": preference_snapshot}
        )
        resolutions = await self.place_resolver.resolve_many(
            candidates,
            destination=draft.explorer.intent.destination,
        )
        intake_id = str(uuid4())
        if self.explorer_persistence is not None:
            self.explorer_persistence.save(
                intake_id=intake_id,
                user_id=payload.user_state.user_id,
                destination=draft.explorer.intent.destination,
                resolutions=resolutions,
            )
        if preference_user is not None and self.user_repository is not None:
            preference_user.travel_preferences = effective_profile.model_dump(
                mode="json",
                by_alias=True,
            )
            self.user_repository.commit()
        return ExploreIntakeResponse(
            intakeId=intake_id,
            userId=payload.user_state.user_id,
            explorer=draft.explorer,
            allowFinderSuggestions=(
                not has_reference_input
                or (
                    explicitly_requested_days is not None
                    and source_coverage_days > 0
                    and explicitly_requested_days > source_coverage_days
                )
            ),
        )

    async def create_main_plan(self, payload: MainPlanCreate) -> Plan:
        plan = await self.main_workflow.run(payload)
        self.repository.save(plan)
        return plan

    async def create_main_plan_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        selected_places = list(payload.selected_places)
        if payload.intake_id and self.explorer_persistence is not None:
            selected_places = _merge_selected_places(
                selected_places,
                self.explorer_persistence.load_must_places(
                    payload.intake_id,
                    payload.user_id,
                ),
            )
        plan = await self.main_workflow.run_from_explorer(
            payload.model_copy(update={"selected_places": selected_places})
        )
        self.repository.save(plan)
        return plan

    async def create_main_plan_from_context(
        self,
        payload: PlanningContextCreate,
    ) -> Plan:
        plan = await self.main_workflow.run_from_context(payload)
        self.repository.save(plan)
        return plan

    async def create_backup_plan(self, plan_id: str, payload: BackupPlanCreate) -> PlanBundleRead:
        main_plan = self.repository.get(plan_id)
        backup_plan, validation = await self.backup_workflow.run(main_plan, payload)
        self.repository.save(backup_plan)
        return PlanBundleRead(
            mainPlan=main_plan.model_dump(by_alias=True),
            backupPlan=backup_plan.model_dump(by_alias=True),
            validation=validation.model_dump(by_alias=True),
        )


async def _empty_list() -> list:
    return []


def _url_result_coverage_days(
    results: list[UrlReelExtractionResult],
) -> int:
    details = [
        detail
        for result in results
        for detail in (
            result.extracted_context.extracted_place_details
            if isinstance(result, UrlReelExtractionResult)
            else []
        )
    ]
    if not details:
        return 0
    source_days = [
        detail.source_day
        for detail in details
        if detail.source_day is not None
    ]
    if source_days and len(source_days) == len(details):
        return max(source_days)
    return max(
        math.ceil(len(details) / 3),
        max(source_days, default=0),
    )


def _candidate_coverage_days(
    candidates,
    *,
    pace: str,
) -> int:
    source_candidates = [
        candidate
        for candidate in candidates
        if any(
            source.type in {
                PlaceCandidateSourceType.url,
                PlaceCandidateSourceType.ocr,
            }
            for source in candidate.sources
        )
    ]
    if not source_candidates:
        return 0
    capacity = {
        "relaxed": 2,
        "balanced": 3,
        "packed": 5,
    }.get(pace, 3)
    source_days = [
        candidate.source_day
        for candidate in source_candidates
        if candidate.source_day is not None
    ]
    if source_days and len(source_days) == len(source_candidates):
        return max(source_days)
    inferred = math.ceil(len(source_candidates) / capacity)
    return max([inferred, *source_days])


def _merge_selected_places(
    explicit: list[SelectedPlaceCreate],
    persisted: list[SelectedPlaceCreate],
) -> list[SelectedPlaceCreate]:
    merged = list(explicit)
    seen = {
        (place.place_id or place.name).strip().casefold()
        for place in merged
    }
    for place in persisted:
        key = (place.place_id or place.name).strip().casefold()
        if key in seen:
            continue
        merged.append(place)
        seen.add(key)
    return merged
