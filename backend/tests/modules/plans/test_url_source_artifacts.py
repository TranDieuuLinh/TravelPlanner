from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.plans.explorer.model import (
    ExplorerIntake,
    UrlExtractionCacheEntry,
    UrlSourceArtifact,
)
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
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
        metadata=UrlMetadata(
            originalUrl=url,
            canonicalUrl=url,
            platform="tiktok",
        ),
        artifacts=MediaArtifacts(),
        speechToText=SpeechToTextResult(
            text=speech_text,
            status="ok",
            source=speech_source,
            language="en",
            durationSeconds=0.1,
            observations=[
                {
                    "order": 1,
                    "placeName": "Hoan Kiem Lake",
                    "evidence": speech_text,
                    "confidence": 0.9,
                }
            ],
        ),
        frameVision=FrameVisionResult(
            text=ocr_text,
            places=["Hoan Kiem Lake"],
            observations=[
                {
                    "order": 1,
                    "placeName": "Hoan Kiem Lake",
                    "evidence": ocr_text,
                }
            ],
            status="ok",
            durationSeconds=0.1,
        ),
        extractedContext=ExtractedContext(),
        timings={},
    )


def test_stt_and_ocr_are_saved_as_retrievable_url_artifacts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UrlExtractionCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-artifacts-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[_result()],
        )

        artifacts = repository.load_url_source_artifacts(
            "https://www.tiktok.com/@creator/video/123?utm_campaign=again"
        )
        assert [artifact.artifact_type for artifact in artifacts] == ["ocr", "stt"]
        assert artifacts[0].content_text == "HOAN KIEM LAKE"
        assert artifacts[0].metadata_json["places"] == ["Hoan Kiem Lake"]
        assert artifacts[1].content_text == "First visit Hoan Kiem Lake."
        assert artifacts[1].metadata_json["observations"][0]["placeName"] == (
            "Hoan Kiem Lake"
        )

        stt_only = repository.load_url_source_artifacts(
            "https://www.tiktok.com/@creator/video/123",
            artifact_types={"stt"},
        )
        assert len(stt_only) == 1
        assert stt_only[0].source == "gemini_audio"

    engine.dispose()


def test_force_refresh_updates_artifacts_instead_of_duplicating_them() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UrlExtractionCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-artifacts-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[_result()],
        )
        repository.save(
            intake_id="intake-artifacts-2",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[
                _result(
                    speech_text="Updated spoken note.",
                    ocr_text="UPDATED SIGN",
                )
            ],
        )

        artifacts = list(session.scalars(select(UrlSourceArtifact)).all())
        assert len(artifacts) == 2
        by_type = {artifact.artifact_type: artifact for artifact in artifacts}
        assert by_type["stt"].content_text == "Updated spoken note."
        assert by_type["ocr"].content_text == "UPDATED SIGN"

    engine.dispose()


def test_youtube_speech_is_saved_as_caption_for_the_shared_retrieval_path() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UrlExtractionCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )
    result = _result(
        url="https://www.youtube.com/watch?v=abc123&utm_source=test",
        speech_source="youtube_captions",
        ocr_text="",
    ).model_copy(
        update={
            "platform": "youtube",
            "frame_vision": FrameVisionResult(),
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-caption-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[result],
        )

        artifacts = repository.load_url_source_artifacts(
            "https://youtu.be/abc123?feature=shared"
        )
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "caption"
        assert artifacts[0].source == "youtube_captions"

    engine.dispose()


def test_web_page_saves_only_structured_evidence_not_the_full_article() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UrlExtractionCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )
    result = _result(
        url="https://example.com/article?id=42&utm_source=feed",
        speech_source="web_page_text",
        speech_text="Full article text that must not be persisted.",
        ocr_text="",
    ).model_copy(
        update={
            "platform": "web_page",
            "frame_vision": FrameVisionResult(),
        },
        deep=True,
    )
    result.speech_to_text.observations[0].evidence = "First visit Hoan Kiem Lake."

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-webpage-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[result],
        )

        artifacts = repository.load_url_source_artifacts(
            "https://example.com/article?id=42&utm_campaign=again"
        )
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "webpage"
        assert artifacts[0].content_text == "First visit Hoan Kiem Lake."

    engine.dispose()


def test_partial_frame_ocr_keeps_successful_text_for_retrieval() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UrlExtractionCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )
    result = _result().model_copy(deep=True)
    result.frame_vision.status = "partial"

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-partial-ocr",
            user_id=None,
            destination="Hà Nội",
            resolutions=[],
            url_results=[result],
        )

        artifacts = repository.load_url_source_artifacts(
            "https://www.tiktok.com/@creator/video/123",
            artifact_types={"ocr"},
        )
        assert len(artifacts) == 1
        assert artifacts[0].content_text == "HOAN KIEM LAKE"

    engine.dispose()
