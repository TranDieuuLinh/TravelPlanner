from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.modules.plans.explorer.model import SourceDocument
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)
from app.modules.plans.explorer.tools.url_reels.transcript_cache import (
    CachedYouTubeTranscript,
    SqlAlchemyYouTubeTranscriptCache,
)


def _result(
    *,
    url: str = "https://www.tiktok.com/@creator/video/123?utm_source=test",
    speech_source: str = "gemini_audio",
    speech_text: str = "First visit Hoan Kiem Lake.",
    ocr_text: str = "HOAN KIEM LAKE",
) -> UrlReelExtractionResult:
    return UrlReelExtractionResult(
        url=url,
        platform="tiktok",
        metadata=UrlMetadata(originalUrl=url, canonicalUrl=url, platform="tiktok"),
        artifacts=MediaArtifacts(),
        speechToText=SpeechToTextResult(
            text=speech_text, status="ok", source=speech_source, language="en",
            durationSeconds=0.1,
            observations=[{
                "order": 1, "placeName": "Hoan Kiem Lake",
                "evidence": speech_text, "confidence": 0.9,
            }],
        ),
        frameVision=FrameVisionResult(
            text=ocr_text, places=["Hoan Kiem Lake"],
            observations=[{
                "order": 1, "placeName": "Hoan Kiem Lake", "evidence": ocr_text,
            }],
            status="ok", durationSeconds=0.1,
        ),
        extractedContext=ExtractedContext(), timings={},
    )


def test_stt_ocr_and_extraction_cache_share_one_source_document() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-artifacts", user_id=None, destination="Hà Nội",
            resolutions=[], url_results=[_result()],
        )
        rows = list(session.scalars(select(SourceDocument)))
        assert len(rows) == 1
        assert set(rows[0].artifacts_json) == {"stt", "ocr"}
        assert rows[0].extracted_context_json["_cacheVersion"] == 6

        artifacts = repository.load_url_source_artifacts(
            "https://www.tiktok.com/@creator/video/123?utm_campaign=again"
        )
        by_type = {artifact.artifact_type: artifact for artifact in artifacts}
        assert set(by_type) == {"ocr", "stt"}
        assert by_type["ocr"].content_text == "HOAN KIEM LAKE"
        assert by_type["stt"].metadata_json["observations"][0]["placeName"] == (
            "Hoan Kiem Lake"
        )
        assert repository.load_cached_url_result(
            "https://www.tiktok.com/@creator/video/123"
        ) is not None


def test_refresh_updates_document_artifacts_without_duplicate_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-1", user_id=None, destination="Hà Nội",
            resolutions=[], url_results=[_result()],
        )
        repository.save(
            intake_id="intake-2", user_id=None, destination="Hà Nội",
            resolutions=[], url_results=[_result(
                speech_text="Updated spoken note.", ocr_text="UPDATED SIGN"
            )],
        )
        documents = list(session.scalars(select(SourceDocument)))
        assert len(documents) == 1
        assert documents[0].artifacts_json["stt"]["en"]["text"] == (
            "Updated spoken note."
        )
        assert documents[0].artifacts_json["ocr"]["_"]["text"] == "UPDATED SIGN"


def test_source_documents_are_deduped_and_prefetched_in_one_query() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    source_selects: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_source_select(_conn, _cursor, statement, _params, _context, _many):
        normalized = statement.casefold()
        if normalized.lstrip().startswith("select") and "source_documents" in normalized:
            source_selects.append(statement)

    first = _result()
    duplicate = _result(
        url="https://www.tiktok.com/@creator/video/123?utm_campaign=duplicate",
        speech_text="Updated duplicate source.",
    )
    second = _result(url="https://www.tiktok.com/@creator/video/456")
    with Session(engine) as session:
        ExplorerPersistenceRepository(session).save(
            intake_id="intake-prefetch",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[first, duplicate, second],
        )
        documents = list(session.scalars(select(SourceDocument)))

    assert len(documents) == 2
    assert len(source_selects) == 2  # one prefetch plus this test's final SELECT
    by_url = {document.canonical_url: document for document in documents}
    assert by_url[
        "https://www.tiktok.com/@creator/video/123"
    ].artifacts_json["stt"]["en"]["text"] == "Updated duplicate source."


def test_delete_url_cache_removes_shared_document_but_keeps_import_history() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-delete-cache", user_id=None, destination="Hà Nội",
            resolutions=[], url_results=[_result()],
        )
        assert repository.delete_url_cache(
            "https://www.tiktok.com/@creator/video/123?utm_source=retry"
        ) is True
        assert repository.load_cached_url_result(
            "https://www.tiktok.com/@creator/video/123"
        ) is None
        assert session.get(SourceDocument, "missing") is None


def test_web_page_retains_structured_evidence_not_full_article() -> None:
    result = _result(
        url="https://example.com/article?id=42&utm_source=feed",
        speech_source="web_page_text",
        speech_text="Full article text that must not be persisted.",
        ocr_text="",
    ).model_copy(update={"platform": "web_page", "frame_vision": FrameVisionResult()}, deep=True)
    result.speech_to_text.observations[0].evidence = "First visit Hoan Kiem Lake."
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-web", user_id=None, destination="Hà Nội",
            resolutions=[], url_results=[result],
        )
        artifacts = repository.load_url_source_artifacts(
            "https://example.com/article?id=42&utm_campaign=again"
        )
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "webpage"
        assert artifacts[0].content_text == "First visit Hoan Kiem Lake."


def test_youtube_caption_cache_is_stored_inside_source_document() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    cache = SqlAlchemyYouTubeTranscriptCache(factory)
    from datetime import datetime, timezone

    fetched_at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    cache.save(CachedYouTubeTranscript(
        video_id="abc123", language="vi", text="Đi Hồ Hoàn Kiếm.",
        source="youtube_captions", is_generated=False, fetched_at=fetched_at,
    ))
    restored = cache.get("abc123", languages=["vi"])
    assert restored is not None
    assert restored.text == "Đi Hồ Hoàn Kiếm."
    with Session(engine) as session:
        document = session.scalar(select(SourceDocument))
        assert document is not None
        assert document.artifacts_json["caption"]["vi"]["text"] == (
            "Đi Hồ Hoàn Kiếm."
        )
