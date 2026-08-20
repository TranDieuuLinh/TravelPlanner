import asyncio
import logging
import re
import unicodedata
from datetime import date
from uuid import uuid4

from app.modules.explorer.adm_reconciliation import reconcile_adm_candidates
from app.modules.explorer.completeness import build_completeness
from app.modules.explorer.contract import ExplorerBudget, ExplorerInput, ExplorerOutput
from app.modules.explorer.draft_key import explorer_draft_cache_key
from app.modules.explorer.intake_policy import normalize_intake_items
from app.modules.explorer.models import (
    BatchCoverage,
    ExplorerDraft,
    SourceExtractionResult,
)
from app.modules.explorer.place_dedupe import deduplicate_places
from app.modules.explorer.ports import (
    ExplorerDraftCache,
    ExplorerDraftGenerator,
    ExplorerSnapshotRepository,
    ImageSourceExtractor,
    InsightCatalog,
    TagCatalog,
    UrlSourceCache,
    UrlSourceExtractor,
)
from app.modules.explorer.retry import run_with_one_retry
from app.modules.explorer.source_execution import mark_synthesis_timeout, safe_source
from app.modules.explorer.source_warnings import source_warnings
from app.modules.explorer.tools import normalize_budget_per_person
from app.modules.explorer.trip_defaults import (
    prompt_start_date,
    timezone_for_destination,
    tomorrow,
)
from app.shared.contracts.agent import AgentError

logger = logging.getLogger(__name__)


class ExplorerService:
    _DAY = re.compile(r"\b(\d{1,2})\s*(?:ngày|days?)\b", re.IGNORECASE)
    _URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)

    def __init__(
        self,
        drafts: ExplorerDraftGenerator,
        url_extractor: UrlSourceExtractor,
        image_extractor: ImageSourceExtractor,
        snapshots: ExplorerSnapshotRepository,
        url_cache: UrlSourceCache | None = None,
        draft_cache: ExplorerDraftCache | None = None,
        draft_cache_namespace: str = "explorer-draft-v1",
        minimum_synthesis_coverage: float = 0.8,
        source_extraction_timeout_seconds: float = 90,
        source_synthesis_timeout_seconds: float = 60,
        fallback_drafts: ExplorerDraftGenerator | None = None,
        tag_catalog: TagCatalog | None = None,
        insight_catalog: InsightCatalog | None = None,
    ) -> None:
        self.drafts = drafts
        self.url_extractor = url_extractor
        self.image_extractor = image_extractor
        self.snapshots = snapshots
        self.url_cache = url_cache
        self.draft_cache = draft_cache
        self.draft_cache_namespace = draft_cache_namespace
        self.minimum_synthesis_coverage = minimum_synthesis_coverage
        self.source_extraction_timeout_seconds = source_extraction_timeout_seconds
        self.source_synthesis_timeout_seconds = source_synthesis_timeout_seconds
        self.fallback_drafts = fallback_drafts or drafts
        self.tag_catalog = tag_catalog
        self.insight_catalog = insight_catalog

    def prepare(self, payload: ExplorerInput | dict) -> dict:
        if not isinstance(payload, ExplorerInput):
            payload = ExplorerInput.model_validate(payload)
        prompt = payload.raw_prompt
        embedded_urls = [
            url.rstrip(".,;!?)") for url in self._URL.findall(prompt or "")
        ]
        if embedded_urls:
            payload = payload.model_copy(
                update={"urls": list(dict.fromkeys([*payload.urls, *embedded_urls]))}
            )
        day_match = self._DAY.search(prompt or "")
        return {
            "intake_id": str(uuid4()),
            "payload": payload,
            "prompt_days": int(day_match.group(1)) if day_match else None,
            "prompt_start_date": prompt_start_date(prompt),
        }

    async def prompt_draft(self, prompt: str) -> ExplorerDraft:
        try:
            return await run_with_one_retry(lambda: self.drafts.from_prompt(prompt))
        except Exception:
            # Prompt-only requests can use deterministic extraction when the
            # optional semantic provider is unavailable.
            if self.fallback_drafts is self.drafts:
                raise
            logger.warning("Explorer prompt provider unavailable; using fallback draft")
            return await self.fallback_drafts.from_prompt(prompt)

    async def extract_sources(
        self, payload: ExplorerInput
    ) -> list[SourceExtractionResult]:
        jobs = []
        for index, url in enumerate(payload.urls):
            jobs.append(
                safe_source(
                    kind="url",
                    index=index,
                    reference=url,
                    operation=lambda url=url, index=index: self._extract_url(
                        payload, url=url, source_index=index
                    ),
                    timeout_seconds=self.source_extraction_timeout_seconds,
                )
            )
        offset = len(payload.urls)
        for local_index, image in enumerate(payload.images):
            index = offset + local_index
            jobs.append(
                safe_source(
                    kind="image",
                    index=index,
                    reference=image.file_name,
                    operation=lambda image=image, index=index: (
                        self.image_extractor.extract(
                            image,
                            source_index=index,
                            raw_prompt=payload.raw_prompt,
                            force_refresh=payload.force_refresh,
                        )
                    ),
                    timeout_seconds=self.source_extraction_timeout_seconds,
                )
            )
        return list(await asyncio.gather(*jobs))

    async def _extract_url(
        self,
        payload: ExplorerInput,
        *,
        url: str,
        source_index: int,
    ) -> SourceExtractionResult:
        if self.url_cache is not None and not payload.force_refresh:
            try:
                cached = await self.url_cache.get(url, source_index=source_index)
            except Exception:
                logger.warning("Explorer URL cache lookup failed", exc_info=True)
            else:
                if cached is not None:
                    logger.info(
                        "Explorer URL cache hit for source index %d", source_index
                    )
                    return cached

        logger.info(
            "Explorer URL cache %s for source index %d",
            "bypassed" if payload.force_refresh else "miss",
            source_index,
        )
        result = await self.url_extractor.extract(
            url,
            source_index=source_index,
            raw_prompt=payload.raw_prompt,
        )
        if self.url_cache is not None:
            try:
                await self.url_cache.save(url, result)
            except Exception:
                logger.warning("Explorer URL cache write failed", exc_info=True)
        return result

    @staticmethod
    def coverage(results: list[SourceExtractionResult]) -> BatchCoverage:
        usable = sum(result.status in {"succeeded", "partial"} for result in results)
        if usable == 0:
            return "fatal"
        return "usable" if usable == len(results) else "partial"

    def evaluate_coverage(
        self, results: list[SourceExtractionResult]
    ) -> tuple[BatchCoverage, AgentError | None]:
        coverage = self.coverage(results)
        if coverage != "fatal":
            return coverage, None
        source_errors = [result.error for result in results if result.error]
        if len(source_errors) == 1:
            return coverage, source_errors[0]
        return coverage, AgentError(
            code="SOURCE_EXTRACTION_FAILED",
            message="Không nguồn URL/ảnh nào trích xuất thành công sau một lần thử lại.",
        )

    async def source_draft(
        self, payload: ExplorerInput, results: list[SourceExtractionResult]
    ) -> ExplorerDraft:
        usable = [item for item in results if item.status in {"succeeded", "partial"}]
        cache_key = explorer_draft_cache_key(
            payload,
            usable,
            namespace=self.draft_cache_namespace,
        )
        if self.draft_cache is not None and not payload.force_refresh:
            try:
                cached = await self.draft_cache.get(cache_key)
            except Exception:
                logger.warning("Explorer draft cache lookup failed", exc_info=True)
            else:
                if cached is not None:
                    logger.info("Explorer draft cache hit")
                    return cached
        timed_out = False
        try:
            draft = await asyncio.wait_for(
                self._source_and_prompt_draft(payload, usable),
                timeout=self.source_synthesis_timeout_seconds,
            )
        except TimeoutError:
            timed_out = True
            mark_synthesis_timeout(usable)
            draft = await self.fallback_drafts.from_sources(
                raw_prompt=payload.raw_prompt, sources=usable
            )
        if self.draft_cache is not None and not timed_out:
            try:
                await self.draft_cache.save(cache_key, draft)
            except Exception:
                logger.warning("Explorer draft cache write failed", exc_info=True)
        return draft

    async def _source_and_prompt_draft(self, payload, usable):
        source_job = run_with_one_retry(
            lambda: self.drafts.from_sources(
                raw_prompt=payload.raw_prompt, sources=usable
            )
        )
        if not payload.raw_prompt:
            source_draft = await source_job
            if self.fallback_drafts is self.drafts:
                return source_draft
            structured_draft = await self.fallback_drafts.from_sources(
                raw_prompt=None, sources=usable
            )
            return self._merge_structured_places(source_draft, structured_draft)
        source_draft, prompt_draft = await asyncio.gather(
            source_job,
            run_with_one_retry(
                lambda: self.drafts.from_prompt(payload.raw_prompt or "")
            ),
        )
        if self.fallback_drafts is self.drafts:
            return self._merge_prompt_draft(source_draft, prompt_draft)
        structured_draft = await self.fallback_drafts.from_sources(
            raw_prompt=None, sources=usable
        )
        source_draft = self._merge_structured_places(source_draft, structured_draft)
        return self._merge_prompt_draft(source_draft, prompt_draft)

    @staticmethod
    def _merge_structured_places(
        source_draft: ExplorerDraft, structured_draft: ExplorerDraft
    ) -> ExplorerDraft:
        return source_draft.model_copy(
            update={"places": [*source_draft.places, *structured_draft.places]}
        )

    def normalize(self, draft: ExplorerDraft, raw_prompt: str | None) -> ExplorerDraft:
        places = deduplicate_places(
            [
                place.model_copy(
                    update={"name": " ".join(place.name.strip(" ,.;:-").split())}
                )
                for place in draft.places
                if place.name.strip(" ,.;:-")
            ]
        )
        items, preferences = normalize_intake_items(
            draft.input_items, draft.short_preferences, raw_prompt, normalize=self._key
        )
        avoids = list(dict.fromkeys(draft.short_avoids))
        special_notes = list(
            dict.fromkeys(note.strip() for note in draft.special_notes if note.strip())
        )
        if self.tag_catalog is not None:
            preferences = self.tag_catalog.resolve(preferences)
            avoids = self.tag_catalog.resolve(avoids)
        return draft.model_copy(
            update={
                "places": places,
                "input_items": items,
                "short_preferences": preferences,
                "short_avoids": avoids,
                "special_notes": special_notes,
            }
        )

    @staticmethod
    def _merge_prompt_draft(
        source_draft: ExplorerDraft, prompt_draft: ExplorerDraft
    ) -> ExplorerDraft:
        prompt_budget = prompt_draft.budget
        return source_draft.model_copy(
            update={
                "input_adm": prompt_draft.input_adm or source_draft.input_adm,
                "adm_candidates": [
                    *source_draft.adm_candidates,
                    *prompt_draft.adm_candidates,
                ],
                "places": [*source_draft.places, *prompt_draft.places],
                "input_items": [*source_draft.input_items, *prompt_draft.input_items],
                "budget": (
                    prompt_budget
                    if prompt_budget.source == "raw_prompt"
                    else source_draft.budget
                ),
                "people": prompt_draft.people,
                "short_preferences": [
                    *source_draft.short_preferences,
                    *prompt_draft.short_preferences,
                ],
                "short_avoids": [
                    *source_draft.short_avoids,
                    *prompt_draft.short_avoids,
                ],
                "special_notes": [
                    *source_draft.special_notes,
                    *prompt_draft.special_notes,
                ],
            }
        )

    def reconcile_adm(self, draft: ExplorerDraft) -> tuple[str | None, bool]:
        return reconcile_adm_candidates(
            draft,
            normalize_key=lambda value: self._key(value).replace(" ", ""),
        )

    def finalize(
        self,
        *,
        intake_id: str,
        draft: ExplorerDraft,
        input_adm: str | None,
        adm_conflict: bool,
        prompt_days: int | None,
        coverage: BatchCoverage | None,
        source_results: list[SourceExtractionResult] | None = None,
        prompt_start_date: date | None = None,
    ) -> ExplorerOutput:
        warnings = source_warnings(coverage, source_results)
        timezone = timezone_for_destination(input_adm)
        start_date = prompt_start_date or tomorrow()
        completeness = build_completeness(
            source_results,
            len(draft.places),
            self.minimum_synthesis_coverage,
        )
        budget = draft.budget
        if budget.source == "default":
            budget = ExplorerBudget(level="low", source="default")
        budget = normalize_budget_per_person(budget, draft.people)
        if input_adm and self.insight_catalog is not None:
            try:
                preferences, avoids = self.insight_catalog.enrich(
                    budget_level=budget.level,
                    children=draft.people.children,
                    infants=draft.people.infants,
                    preferences=draft.short_preferences,
                    avoids=draft.short_avoids,
                    seed=f"{intake_id}:{input_adm}:{budget.level}",
                )
                draft = draft.model_copy(
                    update={
                        "short_preferences": preferences,
                        "short_avoids": avoids,
                    }
                )
            except (OSError, ValueError):
                logger.warning("Explorer user-insight catalog is unavailable", exc_info=True)
                warnings.append(
                    "Không thể áp dụng nhóm sở thích mặc định từ insight-user.yml."
                )
        if not input_adm:
            question = (
                "Các nguồn có địa điểm hành chính mâu thuẫn. Bạn muốn đi đâu?"
                if adm_conflict
                else "Bạn muốn đi tỉnh hoặc thành phố nào?"
            )
            return ExplorerOutput(
                status="clarification",
                intakeId=intake_id,
                input_ADM=None,
                places=draft.places or None,
                inputItems=draft.input_items or None,
                urlNotes=draft.url_notes or None,
                days=prompt_days or 3,
                startDate=start_date,
                timezone=timezone,
                budget=budget,
                people=draft.people,
                shortPreferences=draft.short_preferences,
                shortAvoids=draft.short_avoids,
                specialNotes=draft.special_notes,
                clarificationQuestion=question,
                warnings=warnings,
                completeness=completeness,
            )
        status = "ready"
        if completeness and not completeness.complete:
            status = "partial"
        return ExplorerOutput(
            status=status,
            intakeId=intake_id,
            input_ADM=input_adm,
            places=draft.places or None,
            inputItems=draft.input_items or None,
            urlNotes=draft.url_notes or None,
            days=prompt_days or 3,
            startDate=start_date,
            timezone=timezone,
            budget=budget,
            people=draft.people,
            shortPreferences=draft.short_preferences,
            shortAvoids=draft.short_avoids,
            specialNotes=draft.special_notes,
            warnings=warnings,
            completeness=completeness,
        )

    def failure(self, intake_id: str, error: AgentError) -> ExplorerOutput:
        return ExplorerOutput(status="error", intakeId=intake_id, error=error)

    async def persist(self, output: ExplorerOutput, kind: str) -> None:
        payload = output.model_dump(mode="json", by_alias=True, exclude_none=True)
        await run_with_one_retry(
            lambda: self.snapshots.save(output.intake_id, kind, payload)
        )

    async def persist_or_failure(
        self, output: ExplorerOutput, kind: str
    ) -> ExplorerOutput | None:
        try:
            await self.persist(output, kind)
        except Exception:  # noqa: BLE001 - persistence adapters define no common error
            return self.failure(
                output.intake_id,
                AgentError(
                    code="SNAPSHOT_PERSISTENCE_FAILED",
                    message="Không thể lưu snapshot Explorer sau một lần thử lại.",
                ),
            )
        return None

    @staticmethod
    def _key(value: str) -> str:
        value = unicodedata.normalize("NFD", value.casefold())
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        return " ".join(value.replace("đ", "d").split())
