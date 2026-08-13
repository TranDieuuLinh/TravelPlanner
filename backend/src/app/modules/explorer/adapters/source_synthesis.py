import asyncio
import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.modules.explorer.contract import ExplorerPlace, PlaceSource, SourceNote
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import AdmEvidence, ExplorerDraft
from app.shared.llm import (
    LlmAllKeysUnavailable,
    LlmClient,
    LlmConfigurationError,
    LlmError,
    LlmQuotaError,
    LlmRefusalError,
    LlmResponseError,
    LlmServerError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnauthorizedError,
)


MentionKind = Literal[
    "PLACE", "DESTINATION", "ADDRESS", "ACTIVITY",
    "REGION_OUTSIDE_SCOPE", "GENERIC_MENTION",
]


class PlaceMention(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mention: str = Field(min_length=1, max_length=500)
    classification: MentionKind
    artifact_index: int = Field(ge=0)
    evidence: str = Field(min_length=1, max_length=500)
    time_hint: str | None = Field(default=None, max_length=80)
    address_hint: str | None = Field(default=None, max_length=300)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PlaceMentionBatch(BaseModel):
    mentions: list[PlaceMention] = Field(default_factory=list)


class NoteItem(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    place_name: str | None = Field(default=None, max_length=200)
    artifact_index: int = Field(ge=0)


class NoteBatch(BaseModel):
    notes: list[NoteItem] = Field(default_factory=list)


class AdmItem(BaseModel):
    value: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=500)
    artifact_index: int = Field(ge=0)
    confidence: float = Field(default=0.5, ge=0, le=1)


class AdmBatch(BaseModel):
    destinations: list[AdmItem] = Field(default_factory=list)


PLACE_PROMPT = """Extract named place mentions only. Classify every mention as PLACE,
DESTINATION, ADDRESS, ACTIVITY, REGION_OUTSIDE_SCOPE, or GENERIC_MENTION. PLACE means a
specific visitable physical place compatible with targetADM. A restaurant brand without
enough branch information may remain PLACE with address_hint. Do not invent venues.
Return artifact_index so provenance can be reconstructed."""

NOTE_PROMPT = """Extract only useful source-backed travel notes: access, timing, price,
closure, caution, signature item, or distinctive activity. Do not extract trip budget,
people, preferences, destinations, or generic praise. Return artifact_index."""

ADM_PROMPT = """Extract only the intended trip province/city destination. Historical
places mentioned in narration and comparisons are not destinations. Return no result
when the source does not establish trip destination. Return artifact_index."""


def _schema(value):
    if isinstance(value, dict):
        return {key: _schema(item) for key, item in value.items() if key != "default"}
    if isinstance(value, list):
        return [_schema(item) for item in value]
    return value


class GeminiSourceChunkExtractor:
    def __init__(
        self, client: LlmClient, *, max_output_tokens: int = 8_000,
        extract_notes: bool = True,
    ) -> None:
        self.client = client
        self.max_output_tokens = max_output_tokens
        self.extract_notes = extract_notes

    async def extract(self, *, raw_prompt: str | None, source, artifacts: list) -> ExplorerDraft:
        payload = json.dumps({
            "targetADMFromRawPrompt": raw_prompt,
            "sourceKind": source.source_kind,
            "sourceRef": source.source_ref,
            "artifacts": [
                {"index": index, **artifact.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )}
                for index, artifact in enumerate(artifacts)
            ],
        }, ensure_ascii=False)
        jobs = [
            self._call(payload, PLACE_PROMPT, PlaceMentionBatch),
            self._call(payload, ADM_PROMPT, AdmBatch),
        ]
        if self.extract_notes:
            jobs.append(self._call(payload, NOTE_PROMPT, NoteBatch))
        results = await asyncio.gather(*jobs)
        places, adm = results[:2]
        notes = results[2] if self.extract_notes else NoteBatch()
        source.raw_mention_count += len(places.mentions)
        kept = sum(item.classification == "PLACE" for item in places.mentions)
        source.filtered_mention_count += kept
        for item in places.mentions:
            if item.classification != "PLACE":
                key = item.classification.casefold()
                source.discarded_mentions[key] = source.discarded_mentions.get(key, 0) + 1
        return ExplorerDraft(
            inputAdm=adm.destinations[0].value if adm.destinations else None,
            admCandidates=[self._adm(item, artifacts, source) for item in adm.destinations],
            places=[
                self._place(item, artifacts, source)
                for item in places.mentions
                if item.classification == "PLACE"
            ],
            urlNotes=[self._note(item, artifacts, source) for item in notes.notes],
        )

    async def _call(self, payload: str, prompt: str, model_type):
        try:
            raw = await self.client.generate(
                payload,
                system_prompt=prompt,
                temperature=0,
                max_output_tokens=self.max_output_tokens,
                response_json_schema=_schema(model_type.model_json_schema()),
            )
            return model_type.model_validate(json.loads(raw))
        except LlmAllKeysUnavailable as exc:
            raise ExplorerOperationError(
                "SOURCE_KEYS_COOLING_DOWN", "Gemini source keys đang cooldown.",
                retryable=True, retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except (LlmQuotaError, LlmServerError) as exc:
            raise ExplorerOperationError(
                "SOURCE_PROVIDER_RATE_LIMITED", "Gemini source đang bị giới hạn.",
                retryable=True, retry_after_seconds=60,
            ) from exc
        except (LlmTimeoutError, LlmTransportError) as exc:
            raise ExplorerOperationError(
                "SOURCE_PROVIDER_UNAVAILABLE", "Gemini source tạm không khả dụng.",
                retryable=True,
            ) from exc
        except (LlmConfigurationError, LlmRefusalError, LlmUnauthorizedError) as exc:
            raise ExplorerOperationError("SOURCE_EXTRACTION_REJECTED", str(exc)) from exc
        except (LlmResponseError, LlmError, json.JSONDecodeError, ValidationError) as exc:
            raise ExplorerOperationError(
                "SOURCE_EXTRACTION_INVALID", "Structured source extraction không hợp lệ.",
                retryable=True,
            ) from exc

    @staticmethod
    def _artifact(index: int, artifacts: list):
        return artifacts[index] if 0 <= index < len(artifacts) else artifacts[0]

    @classmethod
    def _place(cls, item: PlaceMention, artifacts: list, source) -> ExplorerPlace:
        artifact = cls._artifact(item.artifact_index, artifacts)
        return ExplorerPlace(
            name=item.name,
            addressHint=item.address_hint,
            confidence=item.confidence,
            sourcePlaces=[PlaceSource(
                origin="url" if source.source_kind == "url" else "input",
                evidenceType=artifact.artifact_type,
                sourceUrl=source.source_ref if source.source_kind == "url" else None,
                evidence=item.evidence,
                sourceTimeHint=item.time_hint or artifact.source_time_hint,
                addressHint=item.address_hint,
                observedAt=artifact.observed_at,
                platform=source.platform,
                extractorVersion=source.extractor_version,
                modelVersion=source.model_version,
                cacheStatus=source.cache_status,
            )],
        )

    @classmethod
    def _note(cls, item: NoteItem, artifacts: list, source) -> SourceNote:
        artifact = cls._artifact(item.artifact_index, artifacts)
        return SourceNote(
            summary=item.summary,
            placeName=item.place_name,
            evidenceType=artifact.artifact_type,
            sourceUrl=source.source_ref if source.source_kind == "url" else None,
            observedAt=artifact.observed_at,
        )

    @classmethod
    def _adm(cls, item: AdmItem, artifacts: list, source) -> AdmEvidence:
        artifact = cls._artifact(item.artifact_index, artifacts)
        return AdmEvidence(
            value=item.value,
            evidence=item.evidence,
            sourceType=artifact.artifact_type,
            sourceUrl=source.source_ref if source.source_kind == "url" else None,
            confidence=item.confidence,
        )
