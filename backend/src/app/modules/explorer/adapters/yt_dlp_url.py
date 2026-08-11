import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.modules.explorer.contract import ExplorerPlace, PlaceSource, SourceNote
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import AdmEvidence, ExplorerDraft, SourceExtractionResult
from app.modules.explorer.ports import ExplorerDraftGenerator, UrlMetadataClient


_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}


class PythonYtDlpClient:
    """Blocking yt-dlp Python API isolated behind an async module port."""

    def __init__(self, *, timeout_seconds: float = 30, cookie_file: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_file = cookie_file

    async def extract(self, url: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._extract_sync, url)

    def _extract_sync(self, url: str) -> dict[str, Any]:
        import yt_dlp

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": self.timeout_seconds,
            # Explorer owns the single retry policy; avoid nested yt-dlp retries.
            "retries": 0,
            "extractor_retries": 0,
            "fragment_retries": 0,
            "ignoreconfig": True,
        }
        if self.cookie_file:
            options["cookiefile"] = self.cookie_file
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
            return downloader.sanitize_info(info)


class YtDlpTikTokUrlSourceExtractor:
    def __init__(
        self,
        client: UrlMetadataClient,
        drafts: ExplorerDraftGenerator,
    ) -> None:
        self.client = client
        self.drafts = drafts

    async def extract(
        self,
        url: str,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult:
        self._validate_tiktok_url(url)
        try:
            metadata = await self.client.extract(url)
        except ExplorerOperationError:
            raise
        except Exception as exc:
            raise ExplorerOperationError(
                "URL_DOWNLOAD_FAILED",
                "Không thể đọc metadata/caption từ URL TikTok.",
                retryable=True,
            ) from exc

        evidence_type = "caption" if metadata.get("description") else "url_metadata"
        evidence = self._evidence_text(metadata)
        if not evidence:
            raise ExplorerOperationError(
                "URL_EVIDENCE_EMPTY",
                "TikTok không cung cấp caption hoặc metadata có thể sử dụng.",
            )
        observed_at = datetime.now(UTC)
        draft = await self._metadata_draft(metadata)
        places = [
            self._url_place(place, url, evidence_type, observed_at)
            for place in draft.places
        ]
        notes = [
            SourceNote(
                summary=self._summary(metadata, evidence),
                evidenceType=evidence_type,
                sourceUrl=url,
                observedAt=observed_at,
            )
        ]
        notes.extend(
            SourceNote(
                summary=item.evidence,
                placeName=item.related_place_name,
                evidenceType=evidence_type,
                sourceUrl=url,
                observedAt=observed_at,
            )
            for item in draft.input_items
        )
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="url",
            sourceRef=url,
            status="succeeded",
            admCandidates=[
                AdmEvidence(
                    value=candidate.value,
                    evidence=candidate.evidence,
                    sourceType=evidence_type,
                    sourceUrl=url,
                    confidence=candidate.confidence,
                )
                for candidate in draft.adm_candidates
            ],
            places=places,
            notes=notes,
            extractedPlaceCount=len(places),
        )

    @staticmethod
    def _validate_tiktok_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme not in {"http", "https"} or host not in _TIKTOK_HOSTS:
            raise ExplorerOperationError(
                "UNSUPPORTED_URL",
                "URL downloader hiện chỉ hỗ trợ các host TikTok công khai.",
            )

    @staticmethod
    def _evidence_text(metadata: dict[str, Any]) -> str:
        values = []
        for field in ("title", "description", "location"):
            value = metadata.get(field)
            if isinstance(value, str) and value.strip() and value.strip() not in values:
                values.append(value.strip())
        tags = metadata.get("tags")
        if isinstance(tags, list):
            clean_tags = [str(tag).strip() for tag in tags[:30] if str(tag).strip()]
            if clean_tags:
                values.append(" ".join(clean_tags))
        return ". ".join(value.rstrip(". ") for value in values)[:60_000]

    async def _metadata_draft(self, metadata: dict[str, Any]) -> ExplorerDraft:
        combined = ExplorerDraft()
        for field in ("title", "description", "location"):
            value = metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            draft = await self.drafts.from_prompt(value.strip())
            combined.adm_candidates.extend(draft.adm_candidates)
            combined.places.extend(draft.places)
            combined.input_items.extend(draft.input_items)
            combined.short_preferences.extend(draft.short_preferences)
            combined.short_avoids.extend(draft.short_avoids)
        return combined

    @staticmethod
    def _summary(metadata: dict[str, Any], evidence: str) -> str:
        description = metadata.get("description")
        value = description if isinstance(description, str) else evidence
        return " ".join(value.split())[:500]

    @staticmethod
    def _url_place(
        place: ExplorerPlace,
        url: str,
        evidence_type: str,
        observed_at: datetime,
    ) -> ExplorerPlace:
        sources = [
            PlaceSource(
                origin="url",
                evidenceType=evidence_type,
                sourceUrl=url,
                evidence=source.evidence,
                sourceTimeHint=source.source_time_hint,
                addressHint=source.address_hint,
                observedAt=observed_at,
            )
            for source in place.source_places
        ]
        return place.model_copy(update={"source_places": sources})
