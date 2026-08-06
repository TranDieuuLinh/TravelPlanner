from scripts.quarantine_invalid_knowledge_graph_places import invalid_reasons


def test_invalid_reasons_reports_all_catalog_failures() -> None:
    assert invalid_reasons(
        name="***",
        place_type="nan",
        latitude="0",
        longitude="0",
    ) == [
        "invalid_canonical_name",
        "invalid_place_type",
        "invalid_coordinates",
    ]


def test_invalid_reasons_accepts_a_valid_non_latin_place() -> None:
    assert invalid_reasons(
        name="福恩寺",
        place_type="Buddhist temple",
        latitude="21.03",
        longitude="105.84",
    ) == []
