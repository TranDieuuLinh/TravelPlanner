from scripts.enrich_knowledge_graph_aliases_google import (
    GoogleCandidate,
    exact_google_result,
    google_data_id,
    has_vietnamese_diacritic,
)


def _candidate() -> GoogleCandidate:
    return GoogleCandidate(
        entity_id="travel_place_ChIJ-example",
        entity_type="TravelPlace",
        canonical_name="Hanoi Opera House",
        place_id="ChIJ-example",
        source_link=(
            "https://www.google.com/maps/place/Hanoi+Opera+House/"
            "data=!4m7!3m6!1s0x3135abebf87e0011:0x647af200da508d2b"
        ),
        expected_data_id="0x3135abebf87e0011:0x647af200da508d2b",
        review_count=100,
    )


def test_extracts_stable_google_data_id() -> None:
    assert google_data_id(_candidate().source_link) == (
        "0x3135abebf87e0011:0x647af200da508d2b"
    )


def test_accepts_only_exact_google_identity() -> None:
    expected = {
        "title": "Nhà hát Lớn Hà Nội",
        "data_id": "0x3135abebf87e0011:0x647af200da508d2b",
    }
    mismatch = {
        "title": "Một nhà hát khác",
        "data_id": "0x111:0x222",
    }
    assert exact_google_result(_candidate(), [mismatch, expected]) == expected
    assert exact_google_result(_candidate(), [mismatch]) is None


def test_detects_vietnamese_diacritics() -> None:
    assert has_vietnamese_diacritic("Nhà hát Lớn Hà Nội")
    assert has_vietnamese_diacritic("Đền Quán Thánh")
    assert not has_vietnamese_diacritic("Hanoi Opera House")
