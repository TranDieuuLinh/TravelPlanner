import asyncio
import math
import time
from uuid import uuid4

from app.modules.plans.domain.entities import Plan
from app.modules.places.resolver import PlaceResolver, ProvisionalPlaceResolver
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.explorer.place_candidate_aggregator import (
    PlaceCandidateAggregator,
)
from app.modules.plans.explorer.place_policy import (
    has_url_source,
    is_schedulable_place,
)
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    PlaceCandidateSourceType,
    ExploreTripSpecInput,
    FullExploreRequest,
)
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService, ImageUploadPayload
from app.modules.plans.explorer.tools.url_reels.schema import (
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.explorer.timing import (
    ExplorerTimingLogger,
    ExplorerTimingTrace,
)
from app.modules.plans.repository import PlanRepository
from app.modules.plans.timing import PlanTimingReport
from app.modules.plans.schema import (
    BackupPlanCreate,
    FeatureMapItem,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanBundleRead,
    PlanningContextCreate,
    SelectedPlaceCreate,
)
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.preferences.service import PreferenceLearningService
from app.modules.users.repository import UserRepository


DEFAULT_TRIP_DAYS = 3


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
        explorer_timing_logger: ExplorerTimingLogger | None = None,
        planning_runs: PlanningRunRepository | None = None,
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
        self.explorer_timing_logger = explorer_timing_logger
        self.planning_runs = planning_runs

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
        intake_id = str(uuid4())
        run_id = self._start_explorer_run(
            intake_id=intake_id,
            destination=payload.destination,
            user_id=payload.user_state.user_id,
            input_data=payload,
        )
        trace = ExplorerTimingTrace(
            intake_id,
            url_count=len(payload.urls),
            image_count=len(payload.image_contexts),
        )
        try:
            extraction_start = time.perf_counter()
            url_reel_results = await self._extract_urls(
                payload.urls,
                destination=payload.destination,
            )
            trace.record_stage(
                "urlExtractionWall",
                "URL extractor (wall)",
                extraction_start,
                details={"urlCount": len(payload.urls)},
            )
            trace.add_url_results(url_reel_results)
            result = await self._format_resolve_and_persist(
                payload,
                url_reel_results=url_reel_results,
                intake_id=intake_id,
                trace=trace,
            )
            self._complete_explorer_run(run_id, payload, result)
            return result
        except Exception as exc:
            self._write_timing_report(trace, status="failed")
            self._fail_explorer_run(run_id, payload, exc)
            raise

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
        intake_id = str(uuid4())
        run_input = {
            "rawRequest": raw_request,
            "destination": destination,
            "urls": urls,
            "imageContexts": [
                {"fileName": image.file_name, "mimeType": image.mime_type}
                for image in images
            ],
            "tripSpec": trip_spec,
            "userState": user_state,
        }
        run_id = self._start_explorer_run(
            intake_id=intake_id,
            destination=destination,
            user_id=(user_state.user_id if user_state is not None else None),
            input_data=run_input,
        )
        trace = ExplorerTimingTrace(
            intake_id,
            url_count=len(urls),
            image_count=len(images),
        )
        try:
            if images and self.image_ocr is None:
                raise RuntimeError("Image OCR is not configured.")

            async def extract_images():
                started_at = time.perf_counter()
                try:
                    return (
                        await self.image_ocr.extract_many(
                            images,
                            destination=destination,
                        )
                        if images and self.image_ocr is not None
                        else []
                    )
                finally:
                    if images:
                        trace.record_stage(
                            "imageExtractionWall",
                            "Image OCR (wall)",
                            started_at,
                            details={"imageCount": len(images)},
                        )

            async def extract_urls():
                started_at = time.perf_counter()
                try:
                    return await self._extract_urls(
                        urls,
                        destination=destination,
                    )
                finally:
                    if urls:
                        trace.record_stage(
                            "urlExtractionWall",
                            "URL extractor (wall)",
                            started_at,
                            details={"urlCount": len(urls)},
                        )

            image_contexts, url_reel_results = await asyncio.gather(
                extract_images(),
                extract_urls(),
            )
            trace.add_url_results(url_reel_results)

            payload = FullExploreRequest(
                rawRequest=raw_request,
                destination=destination,
                urls=urls,
                userState=user_state or UserPlanningState(),
                tripSpec=trip_spec or ExploreTripSpecInput(),
                imageContexts=image_contexts,
            )
            result = await self._format_resolve_and_persist(
                payload,
                url_reel_results=url_reel_results,
                intake_id=intake_id,
                trace=trace,
            )
            self._complete_explorer_run(run_id, run_input, result)
            return result
        except Exception as exc:
            self._write_timing_report(trace, status="failed")
            self._fail_explorer_run(run_id, run_input, exc)
            raise
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
        intake_id: str,
        trace: ExplorerTimingTrace,
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
            payload.trip_spec.days = max(
                DEFAULT_TRIP_DAYS,
                provisional_reference_days,
            )
        if payload.urls:
            aggregation_start = time.perf_counter()
            candidates = self.place_candidate_aggregator.aggregate(
                destination=payload.destination,
                generated=[],
                explicit=payload.place_candidates,
                url_results=url_reel_results,
            )
            trace.record_stage(
                "candidateAggregation",
                "Gộp và dedupe candidate",
                aggregation_start,
            )
        else:
            formatter_start = time.perf_counter()
            draft = await self.explore_formatter.format(
                payload,
                url_reel_results=url_reel_results,
            )
            trace.record_stage(
                "formatter",
                "Formatter",
                formatter_start,
            )
            aggregation_start = time.perf_counter()
            candidates = self.place_candidate_aggregator.aggregate(
                destination=payload.destination,
                generated=draft.places.place_candidates,
                explicit=payload.place_candidates,
                url_results=url_reel_results,
            )
            trace.record_stage(
                "candidateAggregation",
                "Gộp và dedupe candidate",
                aggregation_start,
            )
        trace.candidate_count = len(candidates)
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
        if payload.urls:
            async def format_context():
                started_at = time.perf_counter()
                try:
                    return await self.explore_formatter.format_context(
                        payload,
                        url_reel_results=url_reel_results,
                    )
                finally:
                    trace.record_stage(
                        "formatter",
                        "Formatter intent/trip spec",
                        started_at,
                    )

            async def resolve_places():
                started_at = time.perf_counter()
                try:
                    return await self.place_resolver.resolve_many(
                        candidates,
                        destination=payload.destination,
                    )
                finally:
                    trace.record_stage(
                        "placeResolution",
                        "Resolve địa điểm",
                        started_at,
                        details={"candidateCount": len(candidates)},
                    )

            explorer, resolutions = await asyncio.gather(
                format_context(),
                resolve_places(),
            )
        else:
            explorer = draft.explorer
            resolution_start = time.perf_counter()
            try:
                resolutions = await self.place_resolver.resolve_many(
                    candidates,
                    destination=explorer.intent.destination,
                )
            finally:
                trace.record_stage(
                    "placeResolution",
                    "Resolve địa điểm",
                    resolution_start,
                    details={"candidateCount": len(candidates)},
                )
        trace.resolved_count = sum(
            resolution.status == "resolved"
            for resolution in resolutions
        )
        for resolution in resolutions:
            provider = resolution.provider or "unknown"
            trace.provider_counts[provider] = (
                trace.provider_counts.get(provider, 0) + 1
            )
        post_processing_start = time.perf_counter()
        schedulable_candidates = [
            resolution.candidate
            for resolution in resolutions
            if resolution.status == "resolved"
            and is_schedulable_place(
                is_url_source=has_url_source(resolution.candidate),
                resolution_status=resolution.status,
                latitude=resolution.latitude,
                longitude=resolution.longitude,
                resolved_name=resolution.name,
                city=resolution.city,
                destination=explorer.intent.destination,
                country=resolution.country,
            )
        ]
        source_coverage_days = _candidate_coverage_days(
            schedulable_candidates,
            pace=explorer.intent.pace.value,
        )
        effective_days = (
            explicitly_requested_days
            or (
                max(DEFAULT_TRIP_DAYS, source_coverage_days)
                if has_reference_input
                else None
            )
            or explorer.trip_spec.days
            or DEFAULT_TRIP_DAYS
        )
        explorer.trip_spec.days = effective_days
        if (
            explicitly_requested_days is None
            and source_coverage_days > DEFAULT_TRIP_DAYS
        ):
            explorer.assumptions = [
                *explorer.assumptions,
                (
                    f"Trip duration was inferred as {effective_days} days "
                    "from URL/OCR itinerary coverage because the user did "
                    "not specify a duration."
                ),
            ]
        elif explicitly_requested_days is None and has_reference_input:
            explorer.assumptions = [
                *explorer.assumptions,
                (
                    f"The default {DEFAULT_TRIP_DAYS}-day duration was kept. "
                    "Finder may add catalog Places to empty or sparse days "
                    "in the URL/OCR itinerary."
                ),
            ]
        preference_snapshot = self.preference_learning.enrich_snapshot(
            explorer.preference_snapshot,
            destination=explorer.intent.destination,
            candidates=schedulable_candidates,
            interests=explorer.intent.interests,
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
        explorer = explorer.model_copy(
            update={"preference_snapshot": preference_snapshot}
        )
        trace.record_stage(
            "postProcessing",
            "Policy, coverage và preference",
            post_processing_start,
        )
        persistence_start = time.perf_counter()
        if self.explorer_persistence is not None:
            self.explorer_persistence.save(
                intake_id=intake_id,
                user_id=payload.user_state.user_id,
                destination=explorer.intent.destination,
                resolutions=resolutions,
            )
            trace.persisted_count = len(schedulable_candidates)
        if preference_user is not None and self.user_repository is not None:
            preference_user.travel_preferences = effective_profile.model_dump(
                mode="json",
                by_alias=True,
            )
            self.user_repository.commit()
        trace.record_stage(
            "persistence",
            "Lưu Explorer intake",
            persistence_start,
            details={"persistedPlaceCount": trace.persisted_count},
        )
        timing_report = self._write_timing_report(
            trace,
            status="completed",
        )
        return ExploreIntakeResponse(
            intakeId=intake_id,
            userId=payload.user_state.user_id,
            explorer=explorer,
            allowFinderSuggestions=(
                not has_reference_input
                or _source_days_need_finder(
                    schedulable_candidates,
                    days=effective_days,
                    pace=explorer.intent.pace.value,
                )
            ),
            timingReport=timing_report,
        )

    def _write_timing_report(
        self,
        trace: ExplorerTimingTrace,
        *,
        status: str,
    ):
        report = trace.finish(
            status=status,
            log_file=(
                self.explorer_timing_logger.display_path
                if self.explorer_timing_logger is not None
                else None
            ),
        )
        if self.explorer_timing_logger is not None:
            self.explorer_timing_logger.write(report)
        return report

    def _start_explorer_run(
        self,
        *,
        intake_id: str,
        destination: str,
        user_id: str | None,
        input_data: object,
    ) -> str | None:
        if self.planning_runs is None:
            return None
        return self.planning_runs.start(
            source="explorer_intake",
            destination=destination,
            user_id=(int(user_id) if user_id and user_id.isdigit() else None),
            intake_id=intake_id,
            summary={"input": input_data},
        )

    def _complete_explorer_run(
        self,
        run_id: str | None,
        input_data: object,
        result: ExploreIntakeResponse,
    ) -> None:
        if self.planning_runs is None or run_id is None:
            return
        self.planning_runs.add_stage(
            run_id,
            stage="explorer",
            status="completed",
            input_data=input_data,
            output_data=result,
            metadata={"timing": result.timing_report},
        )
        self.planning_runs.complete(
            run_id,
            status="completed",
            summary={
                "intakeId": result.intake_id,
                "destination": result.explorer.intent.destination,
                "days": result.explorer.trip_spec.days,
                "allowFinderSuggestions": result.allow_finder_suggestions,
                "candidateCount": (
                    result.timing_report.candidate_count
                    if result.timing_report is not None
                    else 0
                ),
                "persistedPlaceCount": (
                    result.timing_report.persisted_count
                    if result.timing_report is not None
                    else 0
                ),
            },
        )

    def _fail_explorer_run(
        self,
        run_id: str | None,
        input_data: object,
        exc: Exception,
    ) -> None:
        if self.planning_runs is None or run_id is None:
            return
        self.planning_runs.add_stage(
            run_id,
            stage="explorer",
            status="failed",
            input_data=input_data,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        self.planning_runs.complete(
            run_id,
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )

    async def create_main_plan(self, payload: MainPlanCreate) -> Plan:
        plan = await self.main_workflow.run(payload)
        self.repository.save(plan)
        return plan

    async def create_main_plan_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        plan, _ = await self.create_main_plan_from_explorer_with_timing(payload)
        return plan

    async def create_main_plan_from_explorer_with_timing(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> tuple[Plan, PlanTimingReport]:
        selected_places = list(payload.selected_places)
        if payload.intake_id and self.explorer_persistence is not None:
            selected_places = _merge_selected_places(
                selected_places,
                self.explorer_persistence.load_must_places(
                    payload.intake_id,
                    payload.user_id,
                ),
            )
        if payload.expand_days_to_fit_selected_places:
            required_days = _required_days_for_selected_places(
                selected_places,
                pace=payload.intent.pace.value,
            )
            if required_days > payload.trip_spec.days:
                payload = payload.model_copy(
                    update={
                        "trip_spec": payload.trip_spec.model_copy(
                            update={"days": required_days}
                        )
                    }
                )
        plan, timing_report = await self.main_workflow.run_from_explorer_with_timing(
            payload.model_copy(update={"selected_places": selected_places})
        )
        self.repository.save(plan)
        return plan, timing_report

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


def _source_days_need_finder(
    candidates,
    *,
    days: int,
    pace: str,
) -> bool:
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
    minimum_activity_count = {
        "relaxed": 2,
        "balanced": 3,
        "packed": 4,
    }.get(pace, 3)
    explicit_counts = {day: 0 for day in range(1, days + 1)}
    unassigned_count = 0
    for candidate in source_candidates:
        if (
            candidate.source_day is None
            or candidate.source_day not in explicit_counts
        ):
            unassigned_count += 1
            continue
        explicit_counts[candidate.source_day] += 1

    missing_slots = sum(
        max(0, minimum_activity_count - count)
        for count in explicit_counts.values()
    )
    return unassigned_count < missing_slots


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


def _required_days_for_selected_places(
    selected_places: list[SelectedPlaceCreate],
    *,
    pace: str,
) -> int:
    capacity = {
        "relaxed": 2,
        "balanced": 3,
        "packed": 5,
    }.get(pace, 3)
    count_based_days = math.ceil(len(selected_places) / capacity)
    latest_source_day = max(
        (
            place.source_day
            for place in selected_places
            if place.source_day is not None
        ),
        default=0,
    )
    return min(30, max(1, count_based_days, latest_source_day))
