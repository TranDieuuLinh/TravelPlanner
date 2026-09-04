import asyncio

from app.modules.explorer.adapters.url_sources import YtDlpSocialSourceExtractor
from app.modules.explorer.models import MediaAnalysisResult, SourceArtifact
from app.modules.explorer.ports import DownloadedMedia
from app.modules.explorer.primary_coverage import PrimaryEvidenceCoverage


def _coverage(sufficient: bool) -> PrimaryEvidenceCoverage:
    return PrimaryEvidenceCoverage(
        sufficient=sufficient,
        transcript_timeline_ratio=None,
        meaningful_character_count=120,
        destination_found=sufficient,
        named_place_count=2 if sufficient else 0,
        travel_detail_count=2 if sufficient else 0,
        description_useful=sufficient,
        confidence=0.95,
        reasons=(
            "primary_evidence_sufficient"
            if sufficient
            else "insufficient_travel_evidence",
        ),
    )


class Metadata:
    async def extract(self, url: str):
        return {
            "title": "Hà Nội",
            "description": "Hồ Gươm, Văn Miếu, mở cửa 8 giờ, vé 30.000 đồng",
        }


class Evaluator:
    def __init__(self, sufficient: bool) -> None:
        self.sufficient = sufficient

    async def evaluate(self, artifacts, **kwargs):
        return _coverage(self.sufficient)


class Downloader:
    def __init__(self) -> None:
        self.calls = 0

    async def download(self, url: str, target_dir: str):
        self.calls += 1
        return DownloadedMedia(
            f"{target_dir}/video.mp4",
            {"description": "Hà Nội video"},
        )


class Analyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, media_path: str, work_dir: str, source_url: str):
        self.calls += 1
        return MediaAnalysisResult(artifacts=[
            SourceArtifact(artifactType="stt", text="Hồ Gươm")
        ])


def test_sufficient_metadata_skips_media_download() -> None:
    downloader = Downloader()
    analyzer = Analyzer()
    extractor = YtDlpSocialSourceExtractor(
        downloader,
        analyzer,
        platform="Instagram",
        metadata_client=Metadata(),
        coverage_evaluator=Evaluator(True),
    )

    result = asyncio.run(extractor.extract(
        "https://instagram.com/reel/abc",
        source_index=0,
        raw_prompt=None,
    ))

    assert downloader.calls == 0
    assert analyzer.calls == 0
    assert [artifact.artifact_type for artifact in result.artifacts] == [
        "url_metadata",
        "caption",
    ]


def test_insufficient_metadata_falls_back_to_media_analysis() -> None:
    downloader = Downloader()
    analyzer = Analyzer()
    extractor = YtDlpSocialSourceExtractor(
        downloader,
        analyzer,
        platform="Instagram",
        metadata_client=Metadata(),
        coverage_evaluator=Evaluator(False),
    )

    result = asyncio.run(extractor.extract(
        "https://instagram.com/reel/abc",
        source_index=0,
        raw_prompt=None,
    ))

    assert downloader.calls == 1
    assert analyzer.calls == 1
    assert any(artifact.artifact_type == "stt" for artifact in result.artifacts)
