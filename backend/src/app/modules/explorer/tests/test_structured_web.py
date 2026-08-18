from app.modules.explorer.adapters.structured_web import (
    places_from_numbered_web_headings,
)
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult


def _source(text: str) -> SourceExtractionResult:
    return SourceExtractionResult(
        sourceIndex=2,
        sourceKind="url",
        sourceRef="https://example.com/hanoi-guide",
        status="succeeded",
        platform="web",
        cacheStatus="bypassed",
        artifacts=[
            SourceArtifact(
                artifactType="web_text",
                text=text,
                sourceUrl="https://example.com/hanoi-guide",
                observedAt="2026-08-18T10:00:00+07:00",
            )
        ],
    )


def test_extracts_only_numbered_level_two_headings_with_provenance() -> None:
    source = _source(
        """# Guide
## **1.** **Hồ Hoàn Kiếm** - **Biểu Tượng Thủ Đô**
Body prose mentioning a shop must not become a place.
## **2. Phố Cổ Hà Nội**
## Hotels
### **1. Example Hotel**
## Food
### **1. Phở Hà Nội**
"""
    )

    places = places_from_numbered_web_headings(source)

    assert [place.name for place in places] == ["Hồ Hoàn Kiếm", "Phố Cổ Hà Nội"]
    provenance = places[0].source_places[0]
    assert provenance.source_url == source.source_ref
    assert provenance.evidence_type == "web_text"
    assert provenance.cache_status == "bypassed"
    assert provenance.extractor_version == "structured-web-heading-v1"


def test_removes_generic_activity_copy_without_place_name_dictionary() -> None:
    source = _source(
        """## **3. Check-In Nhà Hát Lớn Hà Nội**
## **8. Tìm Hiểu Văn Hóa Tại Bảo Tàng Dân Tộc Học Việt Nam**
## **13. Trải Nghiệm Làm Gốm Tại Làng Nghề Bát Tràng**
"""
    )

    places = places_from_numbered_web_headings(source)

    assert [place.name for place in places] == [
        "Nhà Hát Lớn Hà Nội",
        "Bảo Tàng Dân Tộc Học Việt Nam",
        "Làng Nghề Bát Tràng",
    ]


def test_ignores_transcript_even_if_it_contains_heading_like_text() -> None:
    source = _source("## 1. Valid web place")
    source.artifacts[0].artifact_type = "transcript"

    assert places_from_numbered_web_headings(source) == []
