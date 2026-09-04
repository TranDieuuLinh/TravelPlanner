from app.modules.explorer.contract import ExplorerPlace, PlaceSource
from app.modules.explorer.place_dedupe import deduplicate_places


def test_deduplicates_normalized_names_and_preserves_sources() -> None:
    places = [
        ExplorerPlace(
            name="Văn Miếu - Quốc Tử Giám",
            confidence=0.7,
            sourcePlaces=[
                PlaceSource(
                    origin="input",
                    evidenceType="raw_prompt",
                    evidence="Thêm Văn Miếu",
                )
            ],
        ),
        ExplorerPlace(
            name="van mieu quoc tu giam",
            addressHint="Hà Nội",
            confidence=0.95,
            sourcePlaces=[
                PlaceSource(
                    origin="url",
                    evidenceType="transcript",
                    sourceUrl="https://example.com/hanoi",
                    evidence="Văn miếu đầu tiên của Việt Nam",
                )
            ],
        ),
    ]

    result = deduplicate_places(places)

    assert len(result) == 1
    assert result[0].name == "Văn Miếu - Quốc Tử Giám"
    assert result[0].address_hint == "Hà Nội"
    assert result[0].confidence == 0.95
    assert [source.origin for source in result[0].source_places] == ["input", "url"]


def test_duplicate_source_evidence_is_merged_once() -> None:
    source_a = PlaceSource(
        origin="input",
        evidenceType="raw_prompt",
        evidence="Thêm Văn Miếu",
    )
    source_b = source_a.model_copy(update={"evidence": "Muốn ghé Văn Miếu"})

    result = deduplicate_places(
        [
            ExplorerPlace(name="Văn Miếu", sourcePlaces=[source_a]),
            ExplorerPlace(name="văn miếu", sourcePlaces=[source_b]),
        ]
    )

    assert len(result) == 1
    assert len(result[0].source_places) == 1
    assert result[0].source_places[0].evidence == (
        "Thêm Văn Miếu\nMuốn ghé Văn Miếu"
    )
