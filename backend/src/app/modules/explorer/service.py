import asyncio
import logging
import re
import unicodedata
from uuid import uuid4

from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerCompleteness,
    ExplorerInput,
    ExplorerOutput,
    SourceCompleteness,
)
from app.modules.explorer.draft_key import explorer_draft_cache_key
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import BatchCoverage, ExplorerDraft, SourceExtractionResult
from app.modules.explorer.ports import (
    ExplorerDraftCache,
    ExplorerDraftGenerator,
    ExplorerSnapshotRepository,
    ImageSourceExtractor,
    UrlSourceCache,
    UrlSourceExtractor,
)
from app.modules.explorer.retry import run_with_one_retry
from app.modules.explorer.source_warnings import source_warnings
from app.modules.explorer.tools import normalize_budget_per_person
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
    ) -> None:
        self.drafts = drafts
        self.url_extractor = url_extractor
        self.image_extractor = image_extractor
        self.snapshots = snapshots
        self.url_cache = url_cache
        self.draft_cache = draft_cache
        self.draft_cache_namespace = draft_cache_namespace
        self.minimum_synthesis_coverage = minimum_synthesis_coverage

    def prepare(self, payload: ExplorerInput | dict) -> dict:
        if not isinstance(payload, ExplorerInput):
            payload = ExplorerInput.model_validate(payload)
        prompt = payload.raw_prompt
        embedded_urls = [url.rstrip(".,;!?)") for url in self._URL.findall(prompt or "")]
        if embedded_urls:
            payload = payload.model_copy(
                update={"urls": list(dict.fromkeys([*payload.urls, *embedded_urls]))}
            )
        day_match = self._DAY.search(prompt or "")
        return {
            "intake_id": str(uuid4()),
            "payload": payload,
            "prompt_days": int(day_match.group(1)) if day_match else None,
        }

    async def prompt_draft(self, prompt: str) -> ExplorerDraft:
        return await run_with_one_retry(lambda: self.drafts.from_prompt(prompt))

    async def extract_sources(self, payload: ExplorerInput) -> list[SourceExtractionResult]:
        jobs = []
        for index, url in enumerate(payload.urls):
            jobs.append(self._safe_source(
                "url", index, url,
                lambda url=url, index=index: self._extract_url(
                    payload, url=url, source_index=index
                ),
            ))
        offset = len(payload.urls)
        for local_index, image in enumerate(payload.images):
            index = offset + local_index
            jobs.append(self._safe_source(
                "image", index, image.file_name,
                lambda image=image, index=index: self.image_extractor.extract(
                    image, source_index=index, raw_prompt=payload.raw_prompt
                ),
            ))
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
        result = result.model_copy(update={
            "cache_status": "bypassed" if payload.force_refresh else "miss"
        })
        if self.url_cache is not None:
            try:
                await self.url_cache.save(url, result)
            except Exception:
                logger.warning("Explorer URL cache write failed", exc_info=True)
        return result

    async def _safe_source(self, kind, index, reference, operation):
        try:
            return await run_with_one_retry(operation)
        except ExplorerOperationError as exc:
            return SourceExtractionResult(
                sourceIndex=index,
                sourceKind=kind,
                sourceRef=reference,
                status="failed_retryable" if exc.retryable else "failed_permanent",
                error=AgentError(code=exc.code, message=str(exc), retryable=exc.retryable),
            )
        except Exception:
            return SourceExtractionResult(
                sourceIndex=index,
                sourceKind=kind,
                sourceRef=reference,
                status="failed_permanent",
                error=AgentError(
                    code="SOURCE_EXTRACTION_FAILED",
                    message="Không thể trích xuất nguồn đầu vào.",
                ),
            )

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
        source_job = run_with_one_retry(
            lambda: self.drafts.from_sources(
                raw_prompt=payload.raw_prompt, sources=usable
            )
        )
        if not payload.raw_prompt:
            draft = await source_job
        else:
            source_draft, prompt_draft = await asyncio.gather(
                source_job,
                run_with_one_retry(
                    lambda: self.drafts.from_prompt(payload.raw_prompt or "")
                ),
            )
            draft = self._merge_prompt_draft(source_draft, prompt_draft)
        if self.draft_cache is not None:
            try:
                await self.draft_cache.save(cache_key, draft)
            except Exception:
                logger.warning("Explorer draft cache write failed", exc_info=True)
        return draft

    def normalize(self, draft: ExplorerDraft, raw_prompt: str | None) -> ExplorerDraft:
        places = []
        by_name = {}
        for place in draft.places:
            name = " ".join(place.name.strip(" ,.;:-").split())
            if not name:
                continue
            key = self._key(name)
            if key in by_name:
                current = by_name[key]
                current.source_places.extend(place.source_places)
                if not current.address_hint:
                    current.address_hint = place.address_hint
                current.confidence = max(current.confidence, place.confidence)
            else:
                normalized = place.model_copy(update={"name": name})
                by_name[key] = normalized
                places.append(normalized)
        # inputItems are allowed only when their evidence is present in raw prompt.
        prompt_key = self._key(raw_prompt or "")
        items = []
        item_keys = set()
        for item in draft.input_items:
            key = (self._key(item.name), item.action, self._key(item.related_place_name or ""))
            if self._key(item.evidence) not in prompt_key or key in item_keys:
                continue
            item_keys.add(key)
            items.append(item)
        return draft.model_copy(update={
            "places": places,
            "input_items": items,
            "short_preferences": list(dict.fromkeys(draft.short_preferences)),
            "short_avoids": list(dict.fromkeys(draft.short_avoids)),
        })

    @staticmethod
    def _merge_prompt_draft(
        source_draft: ExplorerDraft, prompt_draft: ExplorerDraft
    ) -> ExplorerDraft:
        prompt_budget = prompt_draft.budget
        return source_draft.model_copy(update={
            "input_adm": prompt_draft.input_adm or source_draft.input_adm,
            "adm_candidates": [
                *source_draft.adm_candidates, *prompt_draft.adm_candidates
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
                *source_draft.short_preferences, *prompt_draft.short_preferences
            ],
            "short_avoids": [
                *source_draft.short_avoids, *prompt_draft.short_avoids
            ],
        })

    def reconcile_adm(self, draft: ExplorerDraft) -> tuple[str | None, bool]:
        candidates = [item for item in draft.adm_candidates if item.confidence >= 0.7]
        if not candidates and draft.input_adm:
            return draft.input_adm.strip(), False
        groups: dict[str, list] = {}
        for candidate in candidates:
            groups.setdefault(self._adm_key(candidate.value), []).append(candidate)
        if len(groups) > 1:
            strong = [key for key, values in groups.items() if max(v.confidence for v in values) >= 0.9]
            if len(strong) > 1:
                return None, True
        if not groups:
            return None, False
        best = max(groups.values(), key=lambda values: (max(v.confidence for v in values), len(values)))
        return max(best, key=lambda item: item.confidence).value.strip(), False

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
    ) -> ExplorerOutput:
        warnings = source_warnings(coverage, source_results)
        completeness = self._completeness(source_results, len(draft.places))
        budget = draft.budget
        if budget.source == "default":
            budget = ExplorerBudget(level="low", source="default")
        budget = normalize_budget_per_person(budget, draft.people)
        if not input_adm:
            question = (
                "Các nguồn có địa điểm hành chính mâu thuẫn. Bạn muốn đi đâu?"
                if adm_conflict else "Bạn muốn đi tỉnh hoặc thành phố nào?"
            )
            return ExplorerOutput(
                status="clarification", intakeId=intake_id, input_ADM=None,
                places=draft.places or None, inputItems=draft.input_items or None,
                urlNotes=draft.url_notes or None, days=prompt_days or 3,
                budget=budget, people=draft.people,
                shortPreferences=draft.short_preferences, shortAvoids=draft.short_avoids,
                clarificationQuestion=question, warnings=warnings,
                completeness=completeness,
            )
        status = "ready"
        if completeness and not completeness.complete:
            status = "partial"
        return ExplorerOutput(
            status=status, intakeId=intake_id, input_ADM=input_adm,
            places=draft.places or None, inputItems=draft.input_items or None,
            urlNotes=draft.url_notes or None, days=prompt_days or 3,
            budget=budget, people=draft.people,
            shortPreferences=draft.short_preferences, shortAvoids=draft.short_avoids,
            warnings=warnings,
            completeness=completeness,
        )

    def _completeness(
        self, results: list[SourceExtractionResult] | None, deduplicated: int
    ) -> ExplorerCompleteness | None:
        if not results:
            return None
        discarded: dict[str, int] = {}
        sources = []
        complete = True
        for result in results:
            for key, count in result.discarded_mentions.items():
                discarded[key] = discarded.get(key, 0) + count
            synthesis = result.synthesis_coverage_ratio
            complete = complete and result.status == "succeeded" and (
                synthesis is None or synthesis >= self.minimum_synthesis_coverage
            )
            sources.append(SourceCompleteness(
                sourceIndex=result.source_index,
                sourceRef=result.source_ref,
                coverageStatus=result.coverage_status,
                coverageRatio=result.coverage_ratio,
                rawMentionCount=result.raw_mention_count,
                filteredMentionCount=result.filtered_mention_count,
                deduplicatedPlaceCount=result.deduplicated_place_count,
                sourceChunkCount=result.source_chunk_count,
                processedSourceChunkCount=result.processed_source_chunk_count,
                synthesisCoverageRatio=synthesis,
                discarded=result.discarded_mentions,
            ))
        return ExplorerCompleteness(
            sources=sources,
            rawMentionCount=sum(item.raw_mention_count for item in results),
            filteredMentionCount=sum(item.filtered_mention_count for item in results),
            deduplicatedPlaceCount=deduplicated,
            discarded=discarded,
            complete=complete,
        )

    def failure(self, intake_id: str, error: AgentError) -> ExplorerOutput:
        return ExplorerOutput(status="error", intakeId=intake_id, error=error)

    async def persist(self, output: ExplorerOutput, kind: str) -> None:
        payload = output.model_dump(mode="json", by_alias=True, exclude_none=True)
        await run_with_one_retry(lambda: self.snapshots.save(output.intake_id, kind, payload))

    async def persist_or_failure(
        self, output: ExplorerOutput, kind: str
    ) -> ExplorerOutput | None:
        try:
            await self.persist(output, kind)
        except Exception:
            return self.failure(
                output.intake_id,
                AgentError(
                    code="SNAPSHOT_PERSISTENCE_FAILED",
                    message="Không thể lưu snapshot Explorer sau một lần thử lại.",
                ),
            )
        return None

    @staticmethod
    def error_from_exception(exc: Exception, fallback_code: str) -> AgentError:
        if isinstance(exc, ExplorerOperationError):
            return AgentError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
            )
        return AgentError(
            code=fallback_code,
            message="Không thể tạo dữ liệu Explorer.",
        )

    @staticmethod
    def _key(value: str) -> str:
        value = unicodedata.normalize("NFD", value.casefold())
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        return " ".join(value.replace("đ", "d").split())

    @classmethod
    def _adm_key(cls, value: str) -> str:
        return cls._key(value).replace(" ", "")
