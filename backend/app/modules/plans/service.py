import asyncio
import hashlib
import math
import re
import time
import unicodedata
from uuid import uuid4

from app.modules.plans.domain.entities import DestinationStay, Plan, UnscheduledPlace
from app.modules.plans.destination_inference import (
    infer_destination_from_place_names,
    infer_destination_from_text,
    usable_destination,
)
from app.modules.places.resolver import (
    PlaceResolution,
    PlaceResolutionAttempt,
    PlaceResolver,
    ProvisionalPlaceResolver,
)
from app.modules.places.alias_enricher import PlaceAliasEnricher
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.explorer.place_candidate_aggregator import (
    PlaceCandidateAggregator,
)
from app.modules.plans.explorer.destination_guardrail import (
    enforce_url_destination,
    infer_url_destination_hint,
)
from app.modules.plans.explorer.place_policy import (
    has_url_source,
    is_schedulable_place,
)
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    PlaceCandidateReview,
    PlaceCandidateSource,
    PlaceCandidateSourceType,
    ExploreTripSpecInput,
    FullExploreRequest,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService, ImageUploadPayload
from app.modules.plans.explorer.tools.url_reels.schema import (
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.explorer.tools.url_reels.utils import canonicalize_url
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
from app.shared.errors import AppError


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
        place_alias_enricher: PlaceAliasEnricher | None = None,
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
        self.place_alias_enricher = place_alias_enricher
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
        force_url_refresh: bool = False,
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
                        bypass_cache=force_url_refresh,
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
        bypass_cache: bool = False,
    ) -> list[UrlReelExtractionResult]:
        async def extract_or_load(url: str) -> UrlReelExtractionResult:
            cache_lookup_started = time.perf_counter()
            if self.explorer_persistence is not None and not bypass_cache:
                cached = self.explorer_persistence.load_cached_url_result(url)
                if cached is not None:
                    return _with_url_cache_timing(
                        cached,
                        status="hit",
                        duration_seconds=(
                            time.perf_counter() - cache_lookup_started
                        ),
                    )
            cache_status = "bypassed" if bypass_cache else "miss"
            cache_lookup_seconds = time.perf_counter() - cache_lookup_started
            extracted = await asyncio.to_thread(
                self.url_reels.extract,
                UrlReelInput(url=url, destination=destination),
            )
            return _with_url_cache_timing(
                extracted,
                status=cache_status,
                duration_seconds=cache_lookup_seconds,
            )

        return list(await asyncio.gather(*(extract_or_load(url) for url in urls)))

    async def _resolve_places(
        self,
        candidates,
        *,
        destination: str,
    ):
        resolutions = [None] * len(candidates)
        missing_candidates = []
        missing_indexes = []
        for index, candidate in enumerate(candidates):
            cached = (
                self.explorer_persistence.find_cached_resolution(
                    candidate,
                    destination=destination,
                )
                if self.explorer_persistence is not None
                else None
            )
            if cached is not None:
                resolutions[index] = cached.model_copy(
                    update={
                        "provider_attempts": [
                            PlaceResolutionAttempt(
                                candidate=candidate.name,
                                provider="cache",
                                outcome="cache_hit",
                            )
                        ]
                    }
                )
            else:
                missing_indexes.append(index)
                missing_candidates.append(candidate)
        if missing_candidates:
            fresh = await self.place_resolver.resolve_many(
                missing_candidates,
                destination=destination,
            )
            for index, resolution in zip(missing_indexes, fresh, strict=True):
                resolutions[index] = resolution
        return [resolution for resolution in resolutions if resolution is not None]

    async def retry_candidate_reviews(
        self,
        reviews: list[PlaceCandidateReview],
        *,
        destination: str,
    ) -> list[PlaceCandidateReview]:
        retry_reviews = [
            review
            for review in reviews
            if review.status == "needs_review" and review.retryable
        ]
        if not retry_reviews:
            return reviews
        candidates = [_candidate_from_review(review) for review in retry_reviews]
        if self.place_alias_enricher is not None:
            candidates = await self.place_alias_enricher.enrich(
                candidates,
                destination=destination,
            )
        resolutions = await self.place_resolver.resolve_many(
            candidates,
            destination=destination,
        )
        retried = {
            review.candidate_id: _place_candidate_review(
                resolution,
                destination=destination,
                candidate_id=review.candidate_id,
            )
            for review, resolution in zip(
                retry_reviews,
                resolutions,
                strict=True,
            )
        }
        return [retried.get(review.candidate_id, review) for review in reviews]

    async def _format_resolve_and_persist(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[UrlReelExtractionResult],
        intake_id: str,
        trace: ExplorerTimingTrace,
    ) -> ExploreIntakeResponse:
        explicitly_requested_days = payload.trip_spec.days
        destination_stays = _url_destination_stays(url_reel_results)
        has_reference_input = bool(
            payload.urls or payload.image_contexts
        )
        provisional_reference_days = _url_result_coverage_days(
            url_reel_results
        )
        if payload.trip_spec.days is None and destination_stays:
            payload = payload.model_copy(deep=True)
            payload.trip_spec.days = max(
                stay.end_day for stay in destination_stays
            )
        elif payload.trip_spec.days is None and has_reference_input:
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
        captionless_youtube_urls = [
            result.url
            for result in url_reel_results
            if (
                result.platform == "youtube"
                and result.speech_to_text.status == "no_captions"
            )
        ]
        if captionless_youtube_urls:
            raise AppError(
                422,
                "YOUTUBE_CAPTIONS_NOT_FOUND",
                (
                    "This YouTube video has no public captions, so it cannot "
                    "be imported. YouTube audio download and STT are disabled."
                ),
                details={"sourceCount": len(captionless_youtube_urls)},
            )
        unavailable_youtube_urls = [
            result.url
            for result in url_reel_results
            if (
                result.platform == "youtube"
                and result.speech_to_text.status in {"blocked", "unavailable"}
            )
        ]
        if unavailable_youtube_urls:
            raise AppError(
                503,
                "YOUTUBE_CAPTIONS_UNAVAILABLE",
                (
                    "YouTube captions are temporarily unavailable from both "
                    "the backend and the configured fallback worker. Retry later."
                ),
                details={"sourceCount": len(unavailable_youtube_urls)},
            )
        if (
            payload.urls
            and not candidates
            and url_reel_results
            and not destination_stays
        ):
            raise RuntimeError(
                "No evidenced locations could be extracted from the URL. "
                "The media may be unavailable or OCR/STT may have failed. "
                "Retry later or upload screenshots instead of generating an "
                "empty itinerary."
            )
        inferred_source_destination = (
            usable_destination(payload.destination)
            or infer_destination_from_text(
                *(
                    text
                    for result in url_reel_results
                    for text in (result.metadata.title, result.metadata.description)
                )
            )
            or infer_destination_from_place_names(
                [candidate.name for candidate in candidates]
            )
            or None
        )
        if inferred_source_destination:
            candidates = [
                candidate
                if usable_destination(candidate.search_region)
                else candidate.model_copy(
                    update={"search_region": inferred_source_destination}
                )
                for candidate in candidates
            ]
        if self.place_alias_enricher is not None:
            alias_start = time.perf_counter()
            candidates = await self.place_alias_enricher.enrich(
                candidates,
                destination=inferred_source_destination or payload.destination,
            )
            trace.record_stage(
                "placeAliasEnrichment",
                "Tạo alias địa điểm Anh–Việt",
                alias_start,
                details={"candidateCount": len(candidates)},
            )
        source_destination_hint = infer_url_destination_hint(candidates)
        resolution_destination = (
            source_destination_hint.destination
            or inferred_source_destination
            or payload.destination
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
                    return await self._resolve_places(
                        candidates,
                        destination=resolution_destination,
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
            explorer = enforce_url_destination(
                explorer,
                requested_destination=payload.destination,
                resolutions=resolutions,
                extraction_hint=source_destination_hint,
            )
        else:
            explorer = draft.explorer
            resolution_start = time.perf_counter()
            try:
                resolutions = await self._resolve_places(
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
        if destination_stays:
            inferred_destination = explorer.intent.destination.strip()
            if inferred_destination.casefold() in {"", "unspecified"}:
                inferred_destination = destination_stays[0].name
            explorer = explorer.model_copy(
                update={
                    "intent": explorer.intent.model_copy(
                        update={
                            "destination": inferred_destination,
                            "destination_stays": destination_stays,
                        }
                    )
                }
            )
        canonical_resolutions = _dedupe_place_resolutions(resolutions)
        trace.candidate_count = len(canonical_resolutions)
        trace.resolved_count = sum(
            resolution.status == "resolved"
            for resolution in canonical_resolutions
        )
        trace.add_resolution_attempts(
            resolutions,
            canonical_resolutions=canonical_resolutions,
        )
        trace.add_url_resolution_results(
            url_reel_results,
            resolutions,
            canonical_resolutions=canonical_resolutions,
        )
        post_processing_start = time.perf_counter()
        schedulable_candidates = [
            resolution.candidate
            for resolution in canonical_resolutions
            if resolution.status == "resolved"
            and is_schedulable_place(
                is_url_source=has_url_source(resolution.candidate),
                resolution_status=resolution.status,
                latitude=resolution.latitude,
                longitude=resolution.longitude,
                candidate_name=resolution.candidate.name,
                resolved_name=resolution.name,
                city=resolution.city,
                destination=explorer.intent.destination,
                country=resolution.country,
            )
        ]
        candidate_reviews = [
            _place_candidate_review(
                resolution,
                destination=explorer.intent.destination,
            )
            for resolution in canonical_resolutions
        ]
        source_coverage_days = _candidate_coverage_days(
            schedulable_candidates,
            pace=explorer.intent.pace.value,
        )
        effective_days = (
            explicitly_requested_days
            or (
                max(stay.end_day for stay in destination_stays)
                if destination_stays
                else None
            )
            or (
                max(DEFAULT_TRIP_DAYS, source_coverage_days)
                if has_reference_input
                else None
            )
            or explorer.trip_spec.days
            or DEFAULT_TRIP_DAYS
        )
        explorer.trip_spec.days = effective_days
        if explicitly_requested_days is None and destination_stays:
            explorer.assumptions = [
                *explorer.assumptions,
                (
                    f"Trip duration was inferred as {effective_days} days "
                    "from explicit city-stay headings in the URL."
                ),
            ]
        elif (
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
                    "Finder may add catalog Places only to empty days in the "
                    "URL/OCR itinerary."
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
            update={
                "preference_snapshot": preference_snapshot,
                "candidate_reviews": candidate_reviews,
            }
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
                resolutions=canonical_resolutions,
                url_results=url_reel_results,
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
                False
                if destination_stays and not schedulable_candidates
                else not has_reference_input
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
        # URL-backed places are source requirements, not optional suggestions.
        # Grow the plan until every resolved URL place has normal day capacity,
        # even when the original/requested duration was shorter.
        expand_for_url_places = any(
            _has_url_source_ref(place.source_refs)
            for place in selected_places
        )
        disable_suggestions_for_url_overflow = False
        if (
            payload.expand_days_to_fit_selected_places
            or expand_for_url_places
        ):
            required_days = _required_days_for_selected_places(
                selected_places,
                pace=payload.intent.pace.value,
            )
            if required_days > payload.trip_spec.days:
                disable_suggestions_for_url_overflow = expand_for_url_places
                payload = payload.model_copy(
                    update={
                        "trip_spec": payload.trip_spec.model_copy(
                            update={"days": required_days}
                        ),
                        "allow_finder_suggestions": (
                            False
                            if disable_suggestions_for_url_overflow
                            else payload.allow_finder_suggestions
                        ),
                    }
                )
        workflow_payload = payload.model_copy(
            update={"selected_places": selected_places}
        )
        plan, timing_report = await (
            self.main_workflow.run_from_explorer_with_timing(workflow_payload)
        )
        # Count-based capacity handles normal overflow. A route-aware timeline
        # can still push a URL stop past midnight; retry with extra days rather
        # than returning that source place as optional/unscheduled. Hard policy
        # rejections are intentionally not bypassed.
        for _ in range(3):
            retryable_url_overflow = _retryable_url_unscheduled_places(
                plan,
                selected_places,
            )
            if not retryable_url_overflow or workflow_payload.trip_spec.days >= 30:
                break
            extra_days = max(
                1,
                math.ceil(
                    len(retryable_url_overflow)
                    / _selected_place_capacity(payload.intent.pace.value)
                ),
            )
            next_days = min(
                30,
                workflow_payload.trip_spec.days + extra_days,
            )
            workflow_payload = workflow_payload.model_copy(
                update={
                    "trip_spec": workflow_payload.trip_spec.model_copy(
                        update={"days": next_days}
                    ),
                    "allow_finder_suggestions": False,
                }
            )
            plan, timing_report = await (
                self.main_workflow.run_from_explorer_with_timing(
                    workflow_payload
                )
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
    destination_stays = _url_destination_stays(results)
    if destination_stays:
        return max(stay.end_day for stay in destination_stays)
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


def _url_destination_stays(
    results: list[UrlReelExtractionResult],
) -> list[DestinationStay]:
    stays: list[DestinationStay] = []
    next_day = 1
    for result in results:
        for extracted in result.extracted_context.destination_stays:
            start_day = max(next_day, extracted.start_day)
            end_day = min(30, start_day + extracted.duration_days - 1)
            stays.append(
                DestinationStay(
                    name=extracted.name,
                    durationDays=end_day - start_day + 1,
                    startDay=start_day,
                    endDay=end_day,
                    sourceRefs=[result.url],
                )
            )
            next_day = end_day + 1
    return stays


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
    capacity = {
        "relaxed": 2,
        "balanced": 3,
        "packed": 5,
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

    # Pack candidates without a source day the same way Planner does. Finder
    # is needed only for requested days with no URL coverage; it must not pad
    # every sparse reference day up to a generic activity quota.
    for day in explicit_counts:
        assigned = min(
            max(0, capacity - explicit_counts[day]),
            unassigned_count,
        )
        explicit_counts[day] += assigned
        unassigned_count -= assigned
        if unassigned_count == 0:
            break
    return any(count == 0 for count in explicit_counts.values())


def _with_url_cache_timing(
    result: UrlReelExtractionResult,
    *,
    status: str,
    duration_seconds: float,
) -> UrlReelExtractionResult:
    """Attach safe cache telemetry without adding a source URL to the log."""
    return result.model_copy(
        update={
            "timings": {
                **result.timings,
                "urlCacheLookup": duration_seconds,
                "urlCacheHit": 1.0 if status == "hit" else 0.0,
                "urlCacheBypassed": 1.0 if status == "bypassed" else 0.0,
            }
        }
    )


def _merge_selected_places(
    explicit: list[SelectedPlaceCreate],
    persisted: list[SelectedPlaceCreate],
) -> list[SelectedPlaceCreate]:
    merged: list[SelectedPlaceCreate] = []
    for place in [*explicit, *persisted]:
        duplicate_index = next(
            (
                index
                for index, current in enumerate(merged)
                if _same_selected_place(current, place)
            ),
            None,
        )
        if duplicate_index is None:
            merged.append(place)
            continue
        merged[duplicate_index] = _prefer_selected_place(
            merged[duplicate_index],
            place,
        )
    return merged


def _dedupe_place_resolutions(
    resolutions: list[PlaceResolution],
) -> list[PlaceResolution]:
    """Collapse resolved spelling variants to the Planner's place identity."""
    unique: list[PlaceResolution] = []
    selected_places: list[SelectedPlaceCreate | None] = []
    for resolution in resolutions:
        selected = _selected_place_from_resolution(resolution)
        duplicate_index = next(
            (
                index
                for index, current in enumerate(selected_places)
                if selected is not None
                and current is not None
                and _same_selected_place(current, selected)
            ),
            None,
        )
        if duplicate_index is None:
            unique.append(resolution)
            selected_places.append(selected)
            continue

        current = selected_places[duplicate_index]
        assert current is not None and selected is not None
        preferred = _prefer_selected_place(current, selected)
        if _resolution_preference_score(resolution) > (
            _resolution_preference_score(unique[duplicate_index])
        ):
            unique[duplicate_index] = resolution
        selected_places[duplicate_index] = preferred
    return unique


def _selected_place_from_resolution(
    resolution: PlaceResolution,
) -> SelectedPlaceCreate | None:
    if resolution.status != "resolved":
        return None
    return SelectedPlaceCreate(
        placeId=resolution.place_id,
        name=resolution.name or resolution.candidate.name,
        latitude=(
            float(resolution.latitude)
            if resolution.latitude is not None
            else None
        ),
        longitude=(
            float(resolution.longitude)
            if resolution.longitude is not None
            else None
        ),
        sourceRefs=[
            source.url or source.type.value
            for source in resolution.candidate.sources
        ],
        sourceProvider=resolution.provider,
    )


def _resolution_preference_score(
    resolution: PlaceResolution,
) -> tuple[int, int, int]:
    return (
        1 if resolution.provider == "database" else 0,
        1 if resolution.place_id else 0,
        1
        if resolution.latitude is not None and resolution.longitude is not None
        else 0,
    )


def _has_url_source_ref(source_refs: list[str]) -> bool:
    return any(
        source.startswith(("http://", "https://"))
        for source in source_refs
    )


def _same_selected_place(
    left: SelectedPlaceCreate,
    right: SelectedPlaceCreate,
) -> bool:
    if left.place_id and right.place_id and left.place_id == right.place_id:
        return True

    left_tokens = set(_selected_place_tokens(left.name))
    right_tokens = set(_selected_place_tokens(right.name))
    if not left_tokens or not right_tokens:
        return False
    names_overlap = (
        left_tokens == right_tokens
        or (
            min(len(left_tokens), len(right_tokens)) >= 2
            and (
                left_tokens.issubset(right_tokens)
                or right_tokens.issubset(left_tokens)
            )
        )
    )
    if not names_overlap:
        return False

    shared_sources = set(left.source_refs) & set(right.source_refs)
    if any(source.startswith(("http://", "https://")) for source in shared_sources):
        return True
    if all(
        value is not None
        for value in (
            left.latitude,
            left.longitude,
            right.latitude,
            right.longitude,
        )
    ):
        return _coordinate_distance_meters(left, right) <= 250
    return left_tokens == right_tokens


def _selected_place_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.findall(r"[a-z0-9]+", without_marks)


def _coordinate_distance_meters(
    left: SelectedPlaceCreate,
    right: SelectedPlaceCreate,
) -> float:
    assert left.latitude is not None and left.longitude is not None
    assert right.latitude is not None and right.longitude is not None
    latitude_scale = 111_320
    mean_latitude = math.radians((left.latitude + right.latitude) / 2)
    longitude_scale = latitude_scale * math.cos(mean_latitude)
    latitude_delta = (left.latitude - right.latitude) * latitude_scale
    longitude_delta = (left.longitude - right.longitude) * longitude_scale
    return math.hypot(latitude_delta, longitude_delta)


def _prefer_selected_place(
    current: SelectedPlaceCreate,
    incoming: SelectedPlaceCreate,
) -> SelectedPlaceCreate:
    def score(place: SelectedPlaceCreate) -> tuple[int, int, int]:
        return (
            1 if place.source_provider == "database" else 0,
            1 if place.place_id else 0,
            1 if place.latitude is not None and place.longitude is not None else 0,
        )

    preferred = incoming if score(incoming) > score(current) else current
    return preferred.model_copy(
        update={
            "source_refs": list(dict.fromkeys([
                *current.source_refs,
                *incoming.source_refs,
            ])),
            "tags": list(dict.fromkeys([*current.tags, *incoming.tags])),
            "notes": preferred.notes or current.notes or incoming.notes,
            "source_order": current.source_order or incoming.source_order,
            "source_day": current.source_day or incoming.source_day,
        }
    )


def _required_days_for_selected_places(
    selected_places: list[SelectedPlaceCreate],
    *,
    pace: str,
) -> int:
    capacity = _selected_place_capacity(pace)
    occupancy: dict[int, int] = {}
    required_days = 1
    ordered_places = sorted(
        selected_places,
        key=lambda place: (
            place.source_day or 1,
            place.source_order or 10_000,
            place.name.casefold(),
        ),
    )
    for place in ordered_places:
        day = place.source_day or 1
        while day < 30 and occupancy.get(day, 0) >= capacity:
            day += 1
        occupancy[day] = occupancy.get(day, 0) + 1
        required_days = max(required_days, day)
    return min(30, required_days)


def _selected_place_capacity(pace: str) -> int:
    return {
        "relaxed": 2,
        "balanced": 3,
        "packed": 5,
    }.get(pace, 3)


def _retryable_url_unscheduled_places(
    plan: Plan,
    selected_places: list[SelectedPlaceCreate],
) -> list[UnscheduledPlace]:
    retryable_reasons = {
        "no_day_capacity",
        "no_available_slot",
        "planner_omitted_selected_place",
        "source_day_out_of_range",
        "timeline_overflow",
    }
    url_place_ids = {
        place.place_id
        for place in selected_places
        if place.place_id and _has_url_source_ref(place.source_refs)
    }
    url_place_names = {
        "".join(_selected_place_tokens(place.name))
        for place in selected_places
        if _has_url_source_ref(place.source_refs)
    }
    return [
        item
        for item in plan.unscheduled_places
        if item.reason_code in retryable_reasons
        and (
            (item.place_id is not None and item.place_id in url_place_ids)
            or "".join(_selected_place_tokens(item.name)) in url_place_names
        )
    ]


def _place_candidate_review(
    resolution: PlaceResolution,
    *,
    destination: str,
    candidate_id: str | None = None,
) -> PlaceCandidateReview:
    candidate = resolution.candidate
    source_urls = list(
        dict.fromkeys(
            canonicalize_url(source.url)
            for source in candidate.sources
            if source.url
        )
    )
    schedulable = (
        resolution.status == "resolved"
        and is_schedulable_place(
            is_url_source=has_url_source(candidate),
            resolution_status=resolution.status,
            latitude=resolution.latitude,
            longitude=resolution.longitude,
            candidate_name=candidate.name,
            resolved_name=resolution.name,
            city=resolution.city,
            destination=destination,
            country=resolution.country,
        )
    )
    identity = "|".join(
        [
            candidate.name.casefold(),
            str(candidate.source_order or ""),
            *source_urls,
        ]
    )
    return PlaceCandidateReview(
        candidateId=(
            candidate_id
            or hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        ),
        name=candidate.name,
        category=candidate.category,
        status="resolved" if schedulable else "needs_review",
        resolutionReason=(
            None
            if schedulable
            else resolution.resolution_reason
            or "identity_or_coordinates_unverified"
        ),
        provider=resolution.provider,
        resolvedName=resolution.name if schedulable else None,
        address=resolution.address if schedulable else candidate.address_hint,
        latitude=float(resolution.latitude) if schedulable else None,
        longitude=float(resolution.longitude) if schedulable else None,
        searchRegion=candidate.search_region,
        sourceUrls=source_urls,
        sourceOrder=candidate.source_order,
        sourceDay=candidate.source_day,
        confidence=candidate.confidence,
        extractionConfidence=candidate.confidence,
        resolutionConfidence=_resolution_confidence(
            resolution,
            schedulable=schedulable,
        ),
        retryable=not schedulable,
    )


def _resolution_confidence(
    resolution: PlaceResolution,
    *,
    schedulable: bool,
) -> float:
    if not schedulable:
        return 0.0
    base = {
        "database": 0.95,
        "google_maps_scraper": 0.82,
    }.get(resolution.provider or "", 0.75)
    if resolution.data_confidence == "low":
        base -= 0.12
    elif resolution.data_confidence == "high":
        base += 0.03
    if resolution.resolution_reason == "matched_route_context":
        base -= 0.1
    return min(1.0, max(0.0, base))


def _candidate_from_review(
    review: PlaceCandidateReview,
) -> UnifiedPlaceCandidate:
    return UnifiedPlaceCandidate(
        name=review.name,
        category=review.category,
        addressHint=review.address,
        searchRegion=review.search_region,
        sources=[
            PlaceCandidateSource(
                type=PlaceCandidateSourceType.url,
                url=url,
            )
            for url in review.source_urls
        ],
        confidence=(review.extraction_confidence or review.confidence),
        sourceOrder=review.source_order,
        sourceDay=review.source_day,
    )
