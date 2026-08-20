import asyncio

from app.modules.explorer.adapters.primary_coverage import (
    GeminiPrimaryEvidenceEvaluator,
)
from app.modules.explorer.models import SourceArtifact
from app.modules.explorer.primary_coverage import (
    PrimaryEvidenceCoveragePolicy,
    PrimaryEvidenceFacts,
)


def _artifacts(*, transcript: str | None = None, description: str | None = None):
    values = []
    if transcript:
        values.append(SourceArtifact(artifactType="transcript", text=transcript))
    if description:
        values.append(SourceArtifact(artifactType="caption", text=description))
    return values


def test_complete_semantic_transcript_is_sufficient() -> None:
    policy = PrimaryEvidenceCoveragePolicy()
    coverage = policy.evaluate(
        _artifacts(transcript="Hồ Gươm và Văn Miếu. " * 20),
        PrimaryEvidenceFacts(
            destination_found=True,
            named_place_count=2,
            travel_detail_count=1,
            description_useful=True,
            confidence=0.95,
        ),
        transcript_timeline_ratio=0.9,
    )

    assert coverage.sufficient is True
    assert coverage.reasons == ("primary_evidence_sufficient",)


def test_generic_description_is_not_sufficient() -> None:
    policy = PrimaryEvidenceCoveragePolicy()
    coverage = policy.evaluate(
        _artifacts(description="Top địa điểm không thể bỏ lỡ #viral"),
        PrimaryEvidenceFacts(
            destination_found=False,
            named_place_count=0,
            travel_detail_count=0,
            description_useful=False,
            confidence=0.98,
        ),
    )

    assert coverage.sufficient is False
    assert "missing_destination_or_place" in coverage.reasons


def test_exhaustive_request_forces_media_fallback() -> None:
    policy = PrimaryEvidenceCoveragePolicy()
    coverage = policy.evaluate(
        _artifacts(description="Hồ Gươm, Văn Miếu, mở cửa lúc 8 giờ, vé 30.000 đồng"),
        PrimaryEvidenceFacts(
            destination_found=True,
            named_place_count=2,
            travel_detail_count=2,
            description_useful=True,
            confidence=0.95,
        ),
        raw_prompt="Lấy đầy đủ mọi địa điểm trong video",
    )

    assert coverage.sufficient is False
    assert "exhaustive_request" in coverage.reasons


def test_gemini_evaluator_applies_local_thresholds() -> None:
    class Client:
        async def generate(self, *args, **kwargs):
            return (
                '{"destination_found":true,"named_place_count":2,'
                '"travel_detail_count":2,"description_useful":true,'
                '"confidence":0.9}'
            )

    evaluator = GeminiPrimaryEvidenceEvaluator(Client())  # type: ignore[arg-type]
    coverage = asyncio.run(evaluator.evaluate(
        _artifacts(description="Hồ Gươm, Văn Miếu, mở cửa 8 giờ, vé 30.000 đồng")
    ))

    assert coverage.sufficient is True
    assert coverage.named_place_count == 2
