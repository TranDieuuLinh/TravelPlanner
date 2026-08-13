import asyncio
import json

from app.modules.explorer.adapters.gemini import GeminiExplorerDraftGenerator
from app.modules.explorer.models import ExplorerDraft, SourceArtifact, SourceExtractionResult
from app.modules.explorer.source_chunking import prioritize_timestamp_chunk
from app.shared.llm import LlmAllKeysUnavailable


class ActivityNoteClient:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.user_prompt = user_prompt
        self.system_prompt = kwargs["system_prompt"]
        return json.dumps({
            "mentions": [],
            "destinations": [],
            "notes": [{
                "summary": "Explore cafés, shops, and the night market.",
                "place_name": "Old Quarter",
                "artifact_index": 0,
            }]
        })


class PlaceNameClient:
    def __init__(self) -> None:
        self.system_prompt = ""

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.system_prompt = kwargs["system_prompt"]
        return json.dumps({
            "places": [{
                "name": "Lăng Chủ tịch Hồ Chí Minh",
                "confidence": 0.9,
                "sourcePlaces": [{
                    "origin": "input",
                    "evidenceType": "raw_prompt",
                    "evidence": "ghé lăng bác",
                }],
            }]
        })


class ChunkedSourceClient:
    def __init__(self) -> None:
        self.extract_calls = 0

    async def generate(self, user_prompt: str, **kwargs) -> str:
        if "consolidate already extracted" in kwargs["system_prompt"]:
            return json.dumps({"groups": [
                {"canonical_name": "Hồ Gươm", "member_indexes": [0], "keep": True},
                {"canonical_name": "Văn Miếu", "member_indexes": [1], "keep": True},
            ]})
        self.extract_calls += 1
        name = "Hồ Gươm" if self.extract_calls == 1 else "Văn Miếu"
        return json.dumps({"mentions": [{
            "name": name,
            "mention": name,
            "classification": "PLACE",
            "artifact_index": 0,
            "evidence": name,
            "confidence": 0.9,
        }], "destinations": [], "notes": []})


class CoolingThenSuccessfulClient:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.calls == 1:
            raise LlmAllKeysUnavailable(0)
        return json.dumps({"mentions": [{
            "name": "Hồ Gươm",
            "mention": "Hồ Gươm",
            "classification": "PLACE",
            "artifact_index": 0,
            "evidence": "Hồ Gươm",
        }], "destinations": [], "notes": []})


class RejectsLargeChunkClient:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.calls += 1
        if len(user_prompt) > 5_000:
            from app.shared.llm import LlmResponseError

            raise LlmResponseError("too large")
        name = "Hồ Gươm" if "a" * 100 in user_prompt else "Văn Miếu"
        return json.dumps({"mentions": [{
            "name": name,
            "mention": name,
            "classification": "PLACE",
            "artifact_index": 0,
            "evidence": name,
        }], "destinations": [], "notes": []})


class SelectiveRetryClient:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def generate(self, user_prompt: str, **kwargs) -> str:
        marker = "retry" if "retry" in user_prompt else "good"
        self.calls[marker] = self.calls.get(marker, 0) + 1
        if marker == "retry" and self.calls[marker] == 1:
            raise LlmAllKeysUnavailable(0)
        return json.dumps({
            "mentions": [{
                "name": marker,
                "mention": marker,
                "classification": "PLACE",
                "artifact_index": 0,
                "evidence": marker,
            }],
            "destinations": [],
            "notes": [],
        })


class ConcurrencyClient:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return json.dumps({"mentions": [], "destinations": [], "notes": []})


def test_prompt_requests_semantic_place_name_normalization_in_name_only() -> None:
    client = PlaceNameClient()
    generator = GeminiExplorerDraftGenerator(client)  # type: ignore[arg-type]

    draft = asyncio.run(generator.from_prompt("Tôi muốn ghé lăng bác"))

    assert draft.places[0].name == "Lăng Chủ tịch Hồ Chí Minh"
    assert "place-name expert" in client.system_prompt
    assert "name normalization, not verification" in client.system_prompt
    assert "Return the normalized value only in places[].name" in client.system_prompt
    assert set(draft.places[0].model_dump(by_alias=True)) == {
        "name", "addressHint", "confidence", "sourcePlaces"
    }


def test_source_prompt_keeps_supported_activities_as_url_notes() -> None:
    client = ActivityNoteClient()
    generator = GeminiExplorerDraftGenerator(client)  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/reel",
        status="succeeded",
        artifacts=[SourceArtifact(
            artifactType="frame_ocr",
            text=(
                "Explore the Old Quarter: there are many cute cafés, shops "
                "and a night market"
            ),
            sourceUrl="https://example.com/reel",
        )],
    )

    draft = asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert draft.url_notes[0].place_name == "Old Quarter"
    assert "night market" in draft.url_notes[0].summary
    assert "distinctive-activity" in client.system_prompt
    assert '"extractNotes": true' in client.user_prompt


def test_long_source_is_extracted_per_chunk_then_consolidated() -> None:
    client = ChunkedSourceClient()
    generator = GeminiExplorerDraftGenerator(
        client, source_chunk_characters=25, source_max_concurrency=2
    )  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0, sourceKind="url", sourceRef="https://example.com/guide",
        status="succeeded",
        artifacts=[SourceArtifact(
            artifactType="web_text",
            text="Hồ Gươm là trung tâm.\nVăn Miếu là di tích.",
            sourceUrl="https://example.com/guide",
        )],
    )

    draft = asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert client.extract_calls == 2
    assert [place.name for place in draft.places] == ["Hồ Gươm", "Văn Miếu"]
    assert source.extracted_place_count == 2
    assert all(
        place.source_places[0].source_url == "https://example.com/guide"
        for place in draft.places
    )


def test_url_source_repairs_invented_provenance() -> None:
    draft = ExplorerDraft(
        places=[{
            "name": "Hồ Gươm",
            "sourcePlaces": [{
                "origin": "input",
                "evidenceType": "transcript",
                "sourceUrl": "https://invented.invalid",
                "evidence": "Hồ Gươm",
            }],
        }]
    )
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://youtube.com/watch?v=real",
        status="succeeded",
    )

    GeminiExplorerDraftGenerator._repair_provenance(draft, source)

    evidence = draft.places[0].source_places[0]
    assert evidence.origin == "url"
    assert evidence.source_url == source.source_ref


def test_single_long_line_is_split_without_losing_text() -> None:
    generator = GeminiExplorerDraftGenerator(
        ChunkedSourceClient(), source_chunk_characters=10
    )  # type: ignore[arg-type]
    original = "abcdefghijklmnopqrstuvwxyz"
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/guide",
        status="succeeded",
        artifacts=[SourceArtifact(
            artifactType="web_text",
            text=original,
            sourceUrl="https://example.com/guide",
        )],
    )

    chunks = generator._source_chunks(source)

    assert "".join(artifact.text for chunk in chunks for artifact in chunk) == original


def test_url_timestamp_prioritizes_nearest_chunk_without_dropping_others() -> None:
    chunks = [
        [SourceArtifact(artifactType="transcript", text="start", sourceTimeHint="00:00:00")],
        [SourceArtifact(artifactType="transcript", text="target", sourceTimeHint="01:07:30")],
        [SourceArtifact(artifactType="transcript", text="end", sourceTimeHint="01:30:00")],
    ]

    ordered = prioritize_timestamp_chunk(
        chunks, "https://www.youtube.com/watch?v=x&t=4055s"
    )

    assert ordered[0][0].text == "target"
    assert {chunk[0].text for chunk in ordered} == {"start", "target", "end"}


def test_source_chunk_waits_for_key_cooldown_then_retries() -> None:
    client = CoolingThenSuccessfulClient()
    generator = GeminiExplorerDraftGenerator(client)  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com",
        status="succeeded",
        artifacts=[SourceArtifact(artifactType="transcript", text="Hồ Gươm")],
    )

    draft = asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert client.calls == 2
    assert draft.places[0].name == "Hồ Gươm"
    assert source.synthesis_coverage_ratio == 1


def test_failed_large_chunk_can_be_split_without_losing_text() -> None:
    original = "a" * 1500 + "\n" + "b" * 1500
    chunk = [SourceArtifact(artifactType="transcript", text=original)]

    split = GeminiExplorerDraftGenerator._split_failed_chunk(chunk)

    assert len(split) == 2
    assert "".join(part[0].text for part in split) == original


def test_repeated_large_chunk_failure_falls_back_to_smaller_chunks() -> None:
    client = RejectsLargeChunkClient()
    generator = GeminiExplorerDraftGenerator(
        client, source_chunk_characters=10_000
    )  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com",
        status="succeeded",
        artifacts=[SourceArtifact(
            artifactType="transcript", text="a" * 3_000 + "\n" + "b" * 3_000
        )],
    )

    draft = asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert {place.name for place in draft.places} == {"Hồ Gươm", "Văn Miếu"}
    assert source.synthesis_coverage_ratio == 1


def test_successful_chunk_is_not_repeated_when_another_chunk_retries() -> None:
    client = SelectiveRetryClient()
    generator = GeminiExplorerDraftGenerator(
        client,
        source_chunk_characters=5,
        source_max_concurrency=2,
        dedupe_provider="rules",
    )  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com",
        status="succeeded",
        artifacts=[
            SourceArtifact(artifactType="transcript", text="good"),
            SourceArtifact(artifactType="transcript", text="retry"),
        ],
    )

    asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert client.calls == {"good": 1, "retry": 2}
    assert source.processed_source_chunk_count == 2


def test_synthesis_limiter_counts_actual_generate_calls() -> None:
    client = ConcurrencyClient()
    generator = GeminiExplorerDraftGenerator(
        client,
        source_chunk_characters=5,
        source_max_concurrency=10,
        synthesis_max_concurrency=2,
        dedupe_provider="rules",
    )  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com",
        status="succeeded",
        artifacts=[
            SourceArtifact(artifactType="transcript", text=f"part{index}")
            for index in range(6)
        ],
    )

    asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert client.peak == 2
