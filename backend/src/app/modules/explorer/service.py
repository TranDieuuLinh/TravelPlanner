import asyncio
import re
import unicodedata
from uuid import uuid4

from app.modules.explorer.contract import ExplorerBudget, ExplorerInput, ExplorerOutput
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import BatchCoverage, ExplorerDraft, SourceExtractionResult
from app.modules.explorer.ports import (
    ExplorerDraftGenerator,
    ExplorerSnapshotRepository,
    ImageSourceExtractor,
    UrlSourceExtractor,
)
from app.modules.explorer.retry import run_with_one_retry
from app.shared.contracts.agent import AgentError


class ExplorerService:
    _DAY = re.compile(r"\b(\d{1,2})\s*(?:ngày|days?)\b", re.IGNORECASE)
    _URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)

    def __init__(
        self,
        drafts: ExplorerDraftGenerator,
        url_extractor: UrlSourceExtractor,
        image_extractor: ImageSourceExtractor,
        snapshots: ExplorerSnapshotRepository,
    ) -> None:
        self.drafts = drafts
        self.url_extractor = url_extractor
        self.image_extractor = image_extractor
        self.snapshots = snapshots

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
                lambda url=url, index=index: self.url_extractor.extract(
                    url, source_index=index, raw_prompt=payload.raw_prompt
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

    async def source_draft(
        self, payload: ExplorerInput, results: list[SourceExtractionResult]
    ) -> ExplorerDraft:
        usable = [item for item in results if item.status in {"succeeded", "partial"}]
        return await run_with_one_retry(
            lambda: self.drafts.from_sources(raw_prompt=payload.raw_prompt, sources=usable)
        )

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
        items = [item for item in draft.input_items if self._key(item.evidence) in prompt_key]
        return draft.model_copy(update={
            "places": places,
            "input_items": items,
            "short_preferences": list(dict.fromkeys(draft.short_preferences)),
            "short_avoids": list(dict.fromkeys(draft.short_avoids)),
        })

    def reconcile_adm(self, draft: ExplorerDraft) -> tuple[str | None, bool]:
        candidates = [item for item in draft.adm_candidates if item.confidence >= 0.7]
        if not candidates and draft.input_adm:
            return draft.input_adm.strip(), False
        groups: dict[str, list] = {}
        for candidate in candidates:
            groups.setdefault(self._key(candidate.value), []).append(candidate)
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
    ) -> ExplorerOutput:
        warnings = []
        if coverage == "partial":
            warnings.append("Một số nguồn không trích xuất được; kết quả dùng các nguồn còn lại.")
        budget = draft.budget
        if budget.source == "default":
            budget = ExplorerBudget(level="low", source="default")
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
            )
        return ExplorerOutput(
            status="ready", intakeId=intake_id, input_ADM=input_adm,
            places=draft.places or None, inputItems=draft.input_items or None,
            urlNotes=draft.url_notes or None, days=prompt_days or 3,
            budget=budget, people=draft.people,
            shortPreferences=draft.short_preferences, shortAvoids=draft.short_avoids,
            warnings=warnings,
        )

    def failure(self, intake_id: str, error: AgentError) -> ExplorerOutput:
        return ExplorerOutput(status="error", intakeId=intake_id, error=error)

    async def persist(self, output: ExplorerOutput, kind: str) -> None:
        payload = output.model_dump(mode="json", by_alias=True, exclude_none=True)
        await run_with_one_retry(lambda: self.snapshots.save(output.intake_id, kind, payload))

    @staticmethod
    def _key(value: str) -> str:
        value = unicodedata.normalize("NFD", value.casefold())
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        return " ".join(value.replace("đ", "d").split())
