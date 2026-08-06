from scripts.backfill_knowledge_graph_categories import classify_candidate


def test_classifies_only_missing_or_other_categories() -> None:
    assert (
        classify_candidate(
            {"place_type": "Brewpub", "place_category": "other"},
            "place",
        )
        == "nightlife"
    )
    assert classify_candidate({"place_category": "Gym"}, "place") == "wellness"
    assert classify_candidate({"place_type": "Farm", "place_category": "other"}, "place") is None
    assert classify_candidate({"place_type": "Brewpub", "place_category": "food"}, "place") is None
